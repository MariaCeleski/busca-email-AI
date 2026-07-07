# Data Layer

This directory contains database-related documentation and schema references for the AI Email Agent system.

## Structure

```
data/
├── schemas/
│   └── schema.sql    # Reference SQL schema (documentation purposes)
└── README.md
```

## Database

The application uses **PostgreSQL** (via asyncpg) as its primary data store:

- **Users** — Application users who connect their email accounts
- **Connected Accounts** — OAuth-connected Gmail/Microsoft accounts with encrypted tokens
- **Processed Emails** — Emails that have been classified, summarized, and optionally drafted a reply
- **Draft Replies** — AI-generated reply drafts awaiting user approval
- **Access Logs** — API access audit trail
- **Workflow Executions** — Tracking for the multi-agent processing pipeline

## Migrations

Database migrations are managed by [Alembic](https://alembic.sqlalchemy.org/) and live in `backend/alembic/versions/`.

To run migrations:

```bash
cd backend
alembic upgrade head
```

## Vector Store

Email embeddings are stored in [ChromaDB](https://www.trychroma.com/) for semantic similarity search. ChromaDB runs as a separate service (see root `docker-compose.yml`).
