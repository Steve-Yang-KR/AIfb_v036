# SSOT Global AI Football Platform

FastAPI/Jinja implementation of the Player and Coach experience with database-backed authentication.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

SQLite is used locally. Set `DATABASE_URL` to a PostgreSQL connection string for production.

## Render

The included `render.yaml` creates the web service, PostgreSQL database, secure session secret, and health check. Create a new Render Blueprint from this repository.
