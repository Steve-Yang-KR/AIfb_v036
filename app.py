import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Generator

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pwdlib import PasswordHash
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, create_engine, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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


class CoachApplication(Base):
    __tablename__ = "coach_applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(320))
    country: Mapped[str] = mapped_column(String(120), default="")
    home_address: Mapped[str] = mapped_column(String(500), default="")
    native_language: Mapped[str] = mapped_column(String(120), default="")
    coaching_languages: Mapped[str] = mapped_column(String(300), default="")
    qualification: Mapped[str] = mapped_column(String(300), default="")
    years_coaching: Mapped[int] = mapped_column(Integer, default=0)
    coaching_context: Mapped[str] = mapped_column(Text, default="")
    development_example: Mapped[str] = mapped_column(Text, default="")
    triadic_mindset: Mapped[str] = mapped_column(Text, default="")
    readiness: Mapped[str] = mapped_column(Text, default="")
    pilot_availability: Mapped[str] = mapped_column(String(80), default="")
    primary_region: Mapped[str] = mapped_column(String(80), default="")
    evidence_links: Mapped[str] = mapped_column(Text, default="")
    consent_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    credential_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    credential_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credential_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


DATABASE_URL = database_url()
if os.getenv("ENVIRONMENT") == "production" and DATABASE_URL.startswith("sqlite"):
    raise RuntimeError("DATABASE_URL must point to PostgreSQL in production")

engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
else:
    engine_options.update(
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "5")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "300")),
        connect_args={"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "10"))},
    )
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
passwords = PasswordHash.recommended()
templates = Jinja2Templates(directory="templates")

SESSION_SECRET = os.getenv("SESSION_SECRET")
if os.getenv("ENVIRONMENT") == "production" and not SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET is required in production")

app = FastAPI(title="SSOT Global AI Football Platform", version="0.36.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET or secrets.token_urlsafe(32),
    session_cookie="ssot_session",
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=os.getenv("ENVIRONMENT", "development") == "production",
)


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
    user = db.get(User, user_id)
    if not user or not user.is_active:
        request.session.clear()
        return None
    return user


def page_context(request: Request, db: Session, **extra: object) -> dict[str, object]:
    return {"request": request, "current_user": current_user(request, db), "csrf_token": csrf_token(request), **extra}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(request, "home.html", page_context(request, db))


@app.get("/coach-workspace", response_class=HTMLResponse)
def coach_workspace(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    user = current_user(request, db)
    application = db.scalar(select(CoachApplication).where(CoachApplication.user_id == user.id)) if user else None
    return templates.TemplateResponse(
        request,
        "coach_workspace.html",
        page_context(request, db, application=application, saved=request.query_params.get("saved")),
    )


@app.post("/coach-applications")
async def save_coach_application(
    request: Request,
    csrf: str = Form(...),
    action: str = Form(...),
    full_name: str = Form(...),
    email: str = Form(...),
    country: str = Form(""),
    home_address: str = Form(""),
    native_language: str = Form(""),
    coaching_languages: str = Form(""),
    qualification: str = Form(""),
    years_coaching: int = Form(0),
    coaching_context: str = Form(""),
    development_example: str = Form(""),
    triadic_mindset: str = Form(""),
    readiness: list[str] = Form(default=[]),
    pilot_availability: str = Form(""),
    primary_region: str = Form(""),
    evidence_links: str = Form(""),
    consent_ready: bool = Form(False),
    credential: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    validate_csrf(request, csrf)
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login?next=/coach-workspace%23application", status_code=status.HTTP_303_SEE_OTHER)
    if action not in {"draft", "submitted"}:
        raise HTTPException(status_code=400, detail="Invalid application action")
    full_name, email = full_name.strip(), normalize_email(email)
    if len(full_name) < 2 or "@" not in email or not 0 <= years_coaching <= 80:
        raise HTTPException(status_code=400, detail="Please check the required application fields")

    application = db.scalar(select(CoachApplication).where(CoachApplication.user_id == user.id))
    if not application:
        application = CoachApplication(user_id=user.id, full_name=full_name, email=email)
        db.add(application)

    values = {
        "full_name": full_name[:120], "email": email[:320], "country": country.strip()[:120],
        "home_address": home_address.strip()[:500], "native_language": native_language.strip()[:120],
        "coaching_languages": coaching_languages.strip()[:300], "qualification": qualification.strip()[:300],
        "years_coaching": years_coaching, "coaching_context": coaching_context.strip()[:5000],
        "development_example": development_example.strip()[:10000], "triadic_mindset": triadic_mindset.strip()[:10000],
        "readiness": "\n".join(dict.fromkeys(item.strip()[:200] for item in readiness if item.strip())),
        "pilot_availability": pilot_availability.strip()[:80], "primary_region": primary_region.strip()[:80],
        "evidence_links": evidence_links.strip()[:5000], "consent_ready": consent_ready,
        "status": action, "updated_at": datetime.now(timezone.utc),
    }
    for key, value in values.items():
        setattr(application, key, value)

    uploaded = credential if getattr(credential, "filename", "") else None
    if uploaded:
        content = await uploaded.read(5 * 1024 * 1024 + 1)
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Credential file must be 5 MB or smaller")
        allowed = {"application/pdf", "image/jpeg", "image/png"}
        if uploaded.content_type not in allowed:
            raise HTTPException(status_code=415, detail="Credential must be a PDF, JPG or PNG file")
        application.credential_filename = uploaded.filename[:255]
        application.credential_content_type = uploaded.content_type[:120]
        application.credential_size = len(content)
        application.credential_data = content

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Application could not be saved") from exc
    return RedirectResponse(
        f"/coach-workspace?saved={action}#application",
        status_code=status.HTTP_303_SEE_OTHER,
    )


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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            request,
            "auth.html",
            page_context(request, db, mode="signup", error="An account with this email already exists."),
            status_code=409,
        )
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
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc
    return {"status": "ok", "database": "connected"}
