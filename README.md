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

The included `render.yaml` creates the web service and PostgreSQL database in the same Singapore region, generates the secure session secret, runs Alembic migrations before every server start, and checks the live database through `/health`. Create or sync a Render Blueprint from this repository.

Database schema changes must be added as Alembic revisions. Existing v0.36 databases are adopted by the initial migration without removing current users.

The Coach Workspace application form stores drafts and submitted applications in PostgreSQL. Each signed-in user has one updateable application record, including readiness selections, consent attestation, and an optional credential file up to 5 MB.
