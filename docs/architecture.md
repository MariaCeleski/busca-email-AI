# Architecture Overview

## System Design

The AI Email Agent is a multi-agent system that automatically classifies, summarizes, and drafts replies to incoming emails using LangGraph orchestration and Google Gemini LLMs.

## Project Structure

```
ai-email-agent/
│
├── backend/                          # Python server (FastAPI + LangGraph + Celery)
│   ├── src/
│   │   ├── __init__.py
│   │   ├── config.py                 # Pydantic BaseSettings (36 env vars)
│   │   │
│   │   ├── agents/                   # IA Agents (LangGraph nodes)
│   │   │   ├── __init__.py
│   │   │   ├── classifier.py         # ClassifierAgent — classifica e-mails (Gemini)
│   │   │   ├── summarizer.py         # SummarizerAgent — resume e extrai action items
│   │   │   ├── response.py           # ResponseAgent — gera rascunhos com contexto histórico
│   │   │   └── orchestrator.py       # AgentOrchestrator — LangGraph StateGraph workflow
│   │   │
│   │   ├── api/                      # FastAPI Layer
│   │   │   ├── __init__.py
│   │   │   ├── app.py                # FastAPI app factory
│   │   │   ├── routers/
│   │   │   │   ├── emails.py         # GET/POST /api/v1/emails
│   │   │   │   ├── auth.py           # OAuth flows /api/v1/auth
│   │   │   │   └── websocket.py      # WS /api/v1/ws (real-time updates)
│   │   │   └── middleware/
│   │   │       ├── auth.py           # API key / OAuth token validation
│   │   │       └── logging.py        # Access logging middleware
│   │   │
│   │   ├── models/                   # Data Models
│   │   │   ├── __init__.py           # Re-exports all models
│   │   │   ├── enums.py              # EmailCategory, PriorityLevel, DraftStatus, etc.
│   │   │   ├── email.py              # RawEmail, AttachmentMetadata
│   │   │   ├── classification.py     # ClassificationResult
│   │   │   ├── summary.py            # SummaryResult
│   │   │   ├── draft.py              # DraftReply, ReplyAction
│   │   │   ├── workflow.py           # WorkflowState
│   │   │   ├── vector_store.py       # EmailMetadata, SearchResult, MetadataFilter
│   │   │   ├── auth.py               # TokenPair, ConnectedAccount
│   │   │   ├── api.py                # PaginatedResponse, ErrorResponse, FieldError
│   │   │   ├── schemas.py            # Backward-compat re-exports
│   │   │   ├── database.py           # SQLAlchemy Base, engine, session factory
│   │   │   ├── orm.py                # SQLAlchemy ORM models (6 tabelas)
│   │   │   └── repositories.py       # CRUD repository pattern
│   │   │
│   │   ├── providers/                # Email Provider Integrations
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # EmailProviderClient (ABC)
│   │   │   ├── gmail.py              # GmailClient (Google API)
│   │   │   ├── microsoft.py          # MicrosoftGraphClient
│   │   │   └── oauth.py              # OAuthManager (token lifecycle)
│   │   │
│   │   ├── security/                 # Security Layer
│   │   │   ├── __init__.py
│   │   │   ├── encryption.py         # TokenEncryptionService (AES-256-GCM)
│   │   │   └── access_logger.py      # AccessLogger (audit trail, no body content)
│   │   │
│   │   ├── services/                 # Domain Services
│   │   │   ├── __init__.py
│   │   │   ├── email_monitor.py      # EmailMonitor (polling + webhook)
│   │   │   └── vector_store.py       # VectorStoreService (ChromaDB)
│   │   │
│   │   └── tasks/                    # Celery Background Tasks
│   │       ├── __init__.py
│   │       ├── celery_app.py         # Celery configuration
│   │       ├── process_email.py      # process_email_task
│   │       └── poll_emails.py        # poll_emails_task (periodic)
│   │
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py               # Shared fixtures (test_settings, etc.)
│   │   ├── unit/                     # Testes unitários (45 passando)
│   │   │   ├── test_config.py
│   │   │   ├── test_models.py
│   │   │   └── test_models_orm.py
│   │   ├── property/                 # Property-based tests (Hypothesis)
│   │   │   ├── test_classification_properties.py
│   │   │   ├── test_routing_properties.py
│   │   │   ├── test_summary_properties.py
│   │   │   ├── test_vector_store_properties.py
│   │   │   ├── test_api_properties.py
│   │   │   ├── test_orchestration_properties.py
│   │   │   └── test_security_properties.py
│   │   ├── integration/              # Integration tests (DB real, mocked LLM)
│   │   │   ├── test_email_provider.py
│   │   │   ├── test_pipeline_e2e.py
│   │   │   └── test_websocket.py
│   │   └── performance/              # Performance/latency tests
│   │       ├── test_vector_search_latency.py
│   │       └── test_concurrent_workflows.py
│   │
│   ├── alembic/                      # Database Migrations
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   │
│   ├── alembic.ini
│   ├── pyproject.toml                # Dependencies + build config
│   └── .env.example                  # Template de variáveis de ambiente
│
├── frontend/                         # React Dashboard (TypeScript + Vite)
│   ├── src/
│   │   ├── main.tsx                  # Entry point
│   │   ├── App.tsx                   # Root component + routing
│   │   ├── components/               # UI components reutilizáveis
│   │   │   ├── EmailList.tsx
│   │   │   ├── EmailDetail.tsx
│   │   │   ├── DraftReplyEditor.tsx
│   │   │   └── FilterBar.tsx
│   │   ├── pages/                    # Pages/views
│   │   │   ├── Dashboard.tsx
│   │   │   ├── ManualReview.tsx
│   │   │   └── Settings.tsx
│   │   ├── hooks/                    # Custom React hooks
│   │   │   ├── useEmails.ts
│   │   │   └── useWebSocket.ts
│   │   ├── services/                 # Integrations
│   │   │   ├── api.ts               # HTTP client (axios/fetch → FastAPI)
│   │   │   └── websocket.ts         # WebSocket client (real-time updates)
│   │   └── types/                    # TypeScript interfaces
│   │       └── email.ts             # Mirrors backend Pydantic models
│   ├── public/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── data/                             # Data Layer Documentation
│   ├── schemas/
│   │   └── schema.sql               # SQL de referência (6 tabelas)
│   └── README.md                     # Explicação da camada de dados
│
├── docs/                             # Documentação do Projeto
│   └── architecture.md              # ← ESTE ARQUIVO
│
├── .kiro/                            # Spec files (requirements, design, tasks)
│   └── specs/
│       └── ai-email-agent-system/
│           ├── .config.kiro
│           ├── requirements.md
│           ├── design.md
│           └── tasks.md
│
├── docker-compose.yml                # Infraestrutura local
├── .gitignore                        # Python + Node ignores
└── README.md                         # Visão geral + quick start
```

## Tech Stack

| Camada | Tecnologia | Propósito |
|--------|-----------|-----------|
| Backend | Python 3.9+ | Linguagem principal |
| API | FastAPI | REST endpoints + WebSocket |
| Agentes | LangGraph | Orquestração stateful com grafos cíclicos |
| LLM | Google Gemini (2.0-flash) | Classificação, resumo, geração de respostas |
| Embeddings | Gemini Embedding 001 | Vetores 3072-dimensionais para busca semântica |
| Vector Store | ChromaDB | Busca por similaridade de cosseno |
| Database | PostgreSQL | Dados estruturados (users, emails, drafts) |
| Queue | Celery + Redis | Processamento assíncrono de e-mails |
| Frontend | React + TypeScript + Vite | Dashboard human-in-the-loop |
| Security | AES-256-GCM + TLS | Criptografia de tokens OAuth |

## Components

### Backend (Python FastAPI + LangGraph)

- **Agents** — ClassifierAgent, SummarizerAgent, ResponseAgent, AgentOrchestrator
- **API** — FastAPI REST endpoints + WebSocket para atualizações em tempo real
- **Models** — Pydantic schemas (validação), SQLAlchemy ORM (persistência), enums
- **Providers** — Gmail API, Microsoft Graph API, OAuth 2.0 manager
- **Security** — AES-256 token encryption, access audit logging (sem body content)
- **Services** — VectorStoreService (ChromaDB), EmailMonitor (polling/webhook)
- **Tasks** — Celery background jobs para processamento assíncrono

### Frontend (React + TypeScript + Vite)

- Dashboard paginado com filtros (categoria, prioridade, data)
- Visualização de e-mails classificados com resumos
- Editor de draft replies com aprovar/editar/rejeitar
- Seção separada para revisão manual (baixa confiança)
- Gestão de contas conectadas (OAuth)
- Atualizações em tempo real via WebSocket

### Data Layer

- **PostgreSQL** — 6 tabelas: users, connected_accounts, processed_emails, draft_replies, access_logs, workflow_executions
- **ChromaDB** — Embeddings de e-mails para busca semântica (até 100k documentos)
- **Redis** — Celery broker + result backend (até 10 workflows concorrentes)

## Agent Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                          │
│                                                                 │
│  Email → [Classifier] → Route Decision                          │
│                              │                                  │
│               ┌──────────────┼──────────────┐                   │
│               ▼              ▼              ▼                   │
│         [Summarizer]   [Response Agent]  [Manual Review]        │
│               │              │              │                   │
│               └──────────────┼──────────────┘                   │
│                              ▼                                  │
│                     [Publish Results] → Dashboard                │
└─────────────────────────────────────────────────────────────────┘
```

### Routing Logic

| Categoria | Prioridade | Destino |
|-----------|-----------|---------|
| Urgent, Personal | High, Medium | Response Agent |
| Informative, Promotional, Transactional, Spam | Any | Summarizer Agent |
| Any | Low | Summarizer Agent |
| Any (confidence < 0.6) | Any | Manual Review |

### Timeouts e Retry

- Classifier: 10s timeout
- Summarizer: 8s timeout (fallback: primeiras 3 frases)
- Response: 15s timeout (descarta draft parcial)
- Hard timeout por agente: 30s
- Max retries: 3 por agente
- Workflows concorrentes: até 10 (estado isolado)

## API Endpoints

```
GET    /api/v1/emails              # Lista paginada (default 20, max 100)
GET    /api/v1/emails/{id}         # Resultado completo de processamento
GET    /api/v1/emails/review       # E-mails para revisão manual
POST   /api/v1/emails/{id}/reply/approve  # Aprovar e enviar draft
POST   /api/v1/emails/{id}/reply/reject   # Rejeitar draft
POST   /api/v1/emails/fetch        # Trigger manual de fetch
GET    /api/v1/auth/{provider}/connect    # Iniciar OAuth
GET    /api/v1/auth/{provider}/callback   # Callback OAuth
WS     /api/v1/ws                  # Atualizações real-time
```

## Security

- OAuth 2.0 tokens criptografados em repouso (AES-256-GCM)
- Toda comunicação via TLS
- API protegida por API key ou OAuth token
- Access logs sem conteúdo de e-mail (retenção mínima 90 dias)
- Dados do usuário deletados em 24h após desconexão
- Conteúdo bruto de e-mail não persistido além de embeddings

## Running Locally

```bash
# 1. Infraestrutura
docker compose up -d

# 2. Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # configurar API keys
alembic upgrade head
uvicorn src.api:app --reload --port 8000

# 3. Frontend
cd frontend
npm install
npm run dev  # http://localhost:3000

# 4. Celery Worker (em outro terminal)
cd backend
source .venv/bin/activate
celery -A src.tasks.celery_app worker --loglevel=info --concurrency=10
```

## Testing

```bash
cd backend

# Unit tests (rápidos, sem dependências externas)
pytest tests/unit/ -v

# Property-based tests (Hypothesis, 100+ exemplos por propriedade)
pytest tests/property/ -m property

# Integration tests (requer Docker: PostgreSQL + ChromaDB)
pytest tests/integration/ -m integration

# Todos os testes com coverage
pytest --cov=src --cov-report=html
```
