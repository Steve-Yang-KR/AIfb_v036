import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Generator

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pwdlib import PasswordHash
from sqlalchemy import Boolean, DateTime, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from starlette.middleware.sessions import SessionMiddleware


def database_url() -> str:
    value = os.getenv("DATABASE_URL", "sqlite:///./ssot.db")
    # Normalize hosted PostgreSQL URLs to the installed Psycopg 3 driver.
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


engine_options = {"pool_pre_ping": True}
if database_url().startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(database_url(), **engine_options)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
passwords = PasswordHash.recommended()
templates = Jinja2Templates(directory="templates")

app = FastAPI(title="SSOT Global AI Football Platform", version="0.36.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", secrets.token_urlsafe(32)),
    session_cookie="ssot_session",
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=os.getenv("ENVIRONMENT", "development") == "production",
)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def validate_csrf(request: Request, submitted: str) -> None:
    expected = request.session.get("csrf_token", "")
    if not expected or not secrets.compare_digest(expected, submitted):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid form token")


def current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def page_context(request: Request, db: Session, **extra: object) -> dict[str, object]:
    return {"request": request, "current_user": current_user(request, db), "csrf_token": csrf_token(request), **extra}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(request, "home.html", page_context(request, db))


@app.get("/coach-workspace", response_class=HTMLResponse)
def coach_workspace(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(request, "coach_workspace.html", page_context(request, db))


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    if current_user(request, db):
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "auth.html", page_context(request, db, mode="signup", error=None))


@app.post("/signup", response_class=HTMLResponse)
def signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    csrf: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    validate_csrf(request, csrf)
    name, email = name.strip(), normalize_email(email)
    error = None
    if len(name) < 2:
        error = "Please enter your full name."
    elif "@" not in email or len(email) > 320:
        error = "Please enter a valid email address."
    elif len(password) < 8:
        error = "Password must contain at least 8 characters."
    elif role not in {"player", "coach"}:
        error = "Choose Player or Coach."
    elif db.scalar(select(User).where(User.email == email)):
        error = "An account with this email already exists."
    if error:
        return templates.TemplateResponse(request, "auth.html", page_context(request, db, mode="signup", error=error), status_code=400)

    user = User(name=name, email=email, role=role, password_hash=passwords.hash(password))
    db.add(user)
    db.commit()
    request.session.clear()
    request.session["user_id"] = user.id
    csrf_token(request)
    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    if current_user(request, db):
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "auth.html", page_context(request, db, mode="login", error=None))


@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    validate_csrf(request, csrf)
    email = normalize_email(email)
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_active or not passwords.verify(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "auth.html",
            page_context(request, db, mode="login", error="Email or password is incorrect."),
            status_code=400,
        )
    request.session.clear()
    request.session["user_id"] = user.id
    csrf_token(request)
    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/logout")
def logout(request: Request, csrf: str = Form(...)) -> RedirectResponse:
    validate_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "dashboard.html", page_context(request, db, user=user))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
