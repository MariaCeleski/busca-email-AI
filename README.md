# AI Email Agent

Multi-agent email management system powered by LangGraph and Google Gemini. Automatically classifies, summarizes, and drafts replies to incoming emails with a human-in-the-loop approval workflow.

## Project Structure

```
ai-email-agent/
├── backend/          # Python FastAPI + LangGraph server
├── frontend/         # React + TypeScript dashboard
├── data/             # Database schemas and documentation
├── docs/             # Architecture and project documentation
├── .kiro/            # Spec files
└── docker-compose.yml
```

## Quick Start

### 1. Start infrastructure services

```bash
docker compose up -d
```

This starts PostgreSQL, Redis, and ChromaDB.

### 2. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn src.api:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The dashboard will be available at http://localhost:3000.

## Development

### Running tests (backend)

```bash
cd backend
pytest
```

### Running with coverage

```bash
cd backend
pytest --cov=src --cov-report=html
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system design.

## Tech Stack

- **Backend**: Python 3.9+, FastAPI, LangGraph, SQLAlchemy (async), Celery
- **AI/ML**: Google Gemini (classification, summarization, response generation), ChromaDB (embeddings)
- **Frontend**: React 18, TypeScript, Vite, React Router
- **Infrastructure**: PostgreSQL, Redis, ChromaDB, Docker Compose

## Implementation Status

| Component | Status | Tests |
|-----------|--------|-------|
| Project Structure & Config | ✅ Done | 4 tests |
| Pydantic Data Models & Enums | ✅ Done | 41 tests |
| PostgreSQL Schema & ORM | ✅ Done | 29 tests (require PostgreSQL) |
| AES-256 Token Encryption | ✅ Done | 12 tests |
| Access Logging Service | ✅ Done | 11 tests |
| Property Tests (Security) | ✅ Done | 2 property tests |
| OAuth 2.0 Manager | ✅ Done | — |
| Gmail API Client | ✅ Done | 9 tests |
| Microsoft Graph Client | ✅ Done | 10 tests |
| Email Monitor | ✅ Done | 13 unit + 2 property tests |
| Classifier Agent (Gemini) | ✅ Done | 17 tests |
| Summarizer Agent (Gemini) | ✅ Done | 18 tests |
| Vector Store (ChromaDB) | ✅ Done | 14 tests |
| Response Agent (Gemini) | ✅ Done | 15 tests |
| Agent Orchestrator (LangGraph) | ✅ Done | 15 tests |
| Celery Background Tasks | ✅ Done | — |
| FastAPI Endpoints | ✅ Done | 15 tests |
| React Dashboard | ✅ Done | TypeScript + Vite build passing |

**Backend: 198 tests passing** | **Frontend: TypeScript compiles, Vite builds successfully**
