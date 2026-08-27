# Guia de Replicação de Arquitetura — AI Agent System

> Documento de referência para reutilizar a stack, padrões e decisões de arquitetura deste projeto em outros contextos.  
> Baseado no AI Email Agent System — Módulo 2 IA para DEVs.

---

## Índice

1. [Visão Geral da Arquitetura](#1-visão-geral-da-arquitetura)
2. [Stack Tecnológica Completa](#2-stack-tecnológica-completa)
3. [Estrutura de Diretórios Recomendada](#3-estrutura-de-diretórios-recomendada)
4. [Backend — Python + FastAPI](#4-backend--python--fastapi)
5. [Agentes de IA com LangGraph](#5-agentes-de-ia-com-langgraph)
6. [Banco de Dados](#6-banco-de-dados)
7. [Processamento Assíncrono](#7-processamento-assíncrono)
8. [Frontend — React + TypeScript](#8-frontend--react--typescript)
9. [Segurança](#9-segurança)
10. [Testes](#10-testes)
11. [Integração Low-Code / No-Code](#11-integração-low-code--no-code)
12. [DevOps e CI/CD](#12-devops-e-cicd)
13. [Variáveis de Ambiente](#13-variáveis-de-ambiente)
14. [Dependências com Versões Exatas](#14-dependências-com-versões-exatas)
15. [Padrões de Commit e Versionamento](#15-padrões-de-commit-e-versionamento)
16. [Checklist para Novo Projeto](#16-checklist-para-novo-projeto)

---

## 1. Visão Geral da Arquitetura

Este projeto usa uma arquitetura **multi-agente assíncrona** com separação clara entre camadas:

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                             │
│           React + TypeScript + Vite  (:3001)                │
│         Dashboard · Review · Settings · WebSocket           │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP + WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                      BACKEND API                            │
│              FastAPI + Python 3.11  (:8000)                 │
│     Routers · Middleware · Pydantic · OAuth · Webhooks      │
└──────┬───────────────────┬───────────────────┬──────────────┘
       │                   │                   │
┌──────▼──────┐   ┌────────▼────────┐  ┌──────▼──────────────┐
│  LangGraph  │   │   Celery Worker │  │   Integrações       │
│   Agentes   │   │   + Redis Queue │  │   Gmail · OAuth     │
│  Classifier │   │   Background    │  │   Zapier · Webhooks │
│  Summarizer │   │   Jobs          │  └─────────────────────┘
│  Responder  │   └────────┬────────┘
└──────┬──────┘            │
       │            ┌──────▼──────────────────────────────────┐
       │            │           DADOS                          │
       └───────────►│  PostgreSQL · ChromaDB · Redis           │
                    │  Persistência · Vetores · Filas          │
                    └──────────────────────────────────────────┘
```

### Princípios-chave desta arquitetura

- **Separação de responsabilidades**: cada agente tem uma única função
- **Estado imutável por execução**: LangGraph mantém estado isolado por workflow
- **Falha tolerante**: timeouts + retry + fallback em cada agente
- **Human-in-the-loop**: ações destrutivas requerem aprovação humana
- **Observabilidade**: logs estruturados + WebSocket real-time + auditoria

---

## 2. Stack Tecnológica Completa

| Camada | Tecnologia | Versão | Propósito |
|--------|-----------|--------|-----------|
| **Linguagem** | Python | 3.11+ | Backend e agentes |
| **API Framework** | FastAPI | 0.115.6 | REST endpoints + WebSocket |
| **Servidor ASGI** | Uvicorn | 0.34.0 | Servidor de produção |
| **Orquestração de Agentes** | LangGraph | 0.2.60 | Grafo de estados para agentes |
| **LLM Principal** | OpenAI GPT-4o-mini | via API | Classificação, resumo, geração |
| **LLM Alternativo** | Google Gemini 2.0-flash | via API | Embeddings e alternativa |
| **Vector Store** | ChromaDB | 0.5.23 | Busca semântica por similaridade |
| **Banco Relacional** | PostgreSQL | 16+ | Dados estruturados persistentes |
| **ORM** | SQLAlchemy (async) | 2.0.36 | Mapeamento objeto-relacional |
| **Migrações** | Alembic | 1.14.0 | Controle de versão do schema |
| **Driver PostgreSQL** | asyncpg | 0.30.0 | Driver assíncrono nativo |
| **Fila de Tarefas** | Celery | 5.4.0 | Processamento background |
| **Message Broker** | Redis | 5.2.1 | Broker do Celery + cache |
| **Validação** | Pydantic v2 | 2.10.3 | Schemas e validação de dados |
| **Config** | pydantic-settings | 2.7.0 | Variáveis de ambiente tipadas |
| **HTTP Client** | httpx | 0.28.1 | Chamadas HTTP assíncronas |
| **Autenticação** | python-jose | 3.3.0 | JWT tokens |
| **Criptografia** | cryptography | 44.0.0 | AES-256-GCM para tokens OAuth |
| **WebSocket** | websockets | 14.1 | Comunicação real-time |
| **Frontend** | React | 18.3.1 | Interface do usuário |
| **Linguagem Frontend** | TypeScript | 5.6.3 | Tipagem estática no frontend |
| **Build Tool** | Vite | 6.0.3 | Bundler e dev server |
| **Routing Frontend** | React Router DOM | 6.22.0 | Navegação SPA |
| **Data Fetching** | TanStack Query | 5.101.2 | Cache e sincronização de dados |
| **Infraestrutura** | Docker + Compose | latest | Ambiente local e produção |
| **CI/CD** | GitHub Actions | — | Pipeline automatizado |
| **Low-Code** | Zapier | — | Automação sem código |
| **Notificações** | Slack (via Zapier) | — | ChatOps e alertas |

---

## 3. Estrutura de Diretórios Recomendada

```
meu-projeto/
├── backend/
│   ├── src/
│   │   ├── __init__.py
│   │   ├── config.py                 # Pydantic BaseSettings
│   │   ├── agents/                   # Agentes LangGraph
│   │   │   ├── __init__.py
│   │   │   ├── agent_a.py            # Agente especializado
│   │   │   ├── agent_b.py            # Agente especializado
│   │   │   └── orchestrator.py       # StateGraph principal
│   │   ├── api/
│   │   │   ├── app.py                # FastAPI factory
│   │   │   ├── routers/              # Endpoints por domínio
│   │   │   │   ├── items.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── webhooks.py       # Endpoints para Zapier/Make
│   │   │   │   └── websocket.py
│   │   │   └── middleware/
│   │   │       ├── auth.py
│   │   │       ├── logging.py
│   │   │       └── validation.py
│   │   ├── models/
│   │   │   ├── api.py                # Pydantic request/response
│   │   │   ├── database.py           # SQLAlchemy Base + engine
│   │   │   ├── orm.py                # Tabelas ORM
│   │   │   └── repositories.py       # CRUD pattern
│   │   ├── services/                 # Lógica de domínio
│   │   ├── security/
│   │   │   ├── encryption.py         # AES-256-GCM
│   │   │   └── access_logger.py
│   │   └── tasks/                    # Celery tasks
│   │       ├── celery_app.py
│   │       └── process_item.py
│   ├── tests/
│   │   ├── unit/
│   │   ├── property/                 # Hypothesis
│   │   ├── integration/
│   │   └── conftest.py
│   ├── alembic/
│   │   └── versions/
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── .env
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/
│   │   │   ├── api.ts
│   │   │   └── websocket.ts
│   │   └── types/
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── docs/
│   ├── architecture.md
│   ├── prompts.md                    # OBRIGATÓRIO para avaliação
│   └── setup-guide.md
├── .github/
│   └── workflows/
│       └── ci.yml
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## 4. Backend — Python + FastAPI

### Instalação do ambiente

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows

pip install -e ".[dev]"
```

### Factory pattern do FastAPI (`src/api/app.py`)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers import items, auth, webhooks, websocket
from src.config import get_settings

def create_app() -> FastAPI:
    settings = get_settings()
    
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(items.router)
    app.include_router(auth.router)
    app.include_router(webhooks.router)
    app.include_router(websocket.router)
    
    return app

app = create_app()
```

### Configuração tipada (`src/config.py`)

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "Meu Agente"
    app_version: str = "0.1.0"
    debug: bool = False
    
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str
    
    cors_origins: list[str] = ["http://localhost:3001"]
    
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    
    chromadb_host: str = "localhost"
    chromadb_port: int = 8001
    
    enable_webhooks: bool = True
    zapier_webhook_url: str = ""
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

### Middleware de autenticação (`src/api/middleware/auth.py`)

```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader
from src.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    settings = get_settings()
    if api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key
```

---

## 5. Agentes de IA com LangGraph

### Conceito do StateGraph

O LangGraph organiza os agentes como **nós de um grafo** com estado compartilhado. Cada nó recebe o estado atual, processa e retorna um estado atualizado.

```
Estado Inicial → [Nó A] → Decisão de Rota → [Nó B] ou [Nó C] → [Publicar Resultado]
```

### Definição do estado

```python
from typing import TypedDict, Optional, Literal

class WorkflowState(TypedDict):
    # Entrada
    input_id: str
    raw_content: str
    
    # Resultados dos agentes
    classification: Optional[str]
    confidence: Optional[float]
    summary: Optional[str]
    draft_reply: Optional[str]
    
    # Controle de fluxo
    retry_count: int
    errors: list[str]
    requires_human_review: bool
    
    # Metadados
    processing_time_ms: Optional[float]
    model_used: str
```

### Orchestrator com LangGraph (`src/agents/orchestrator.py`)

```python
import asyncio
from langgraph.graph import StateGraph, END
from src.agents.agent_a import AgentA
from src.agents.agent_b import AgentB
from src.models.workflow import WorkflowState

class AgentOrchestrator:
    def __init__(self):
        self._agent_a = AgentA()
        self._agent_b = AgentB()
        self._graph = self._build_graph()
    
    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        
        # Adiciona nós
        graph.add_node("agent_a", self._run_agent_a)
        graph.add_node("agent_b", self._run_agent_b)
        graph.add_node("manual_review", self._route_to_manual_review)
        graph.add_node("publish", self._publish_results)
        
        # Define ponto de entrada
        graph.set_entry_point("agent_a")
        
        # Roteamento condicional após agent_a
        graph.add_conditional_edges(
            "agent_a",
            self._route_after_a,
            {
                "agent_b": "agent_b",
                "manual_review": "manual_review",
            }
        )
        
        graph.add_edge("agent_b", "publish")
        graph.add_edge("manual_review", "publish")
        graph.add_edge("publish", END)
        
        return graph.compile()
    
    def _route_after_a(self, state: WorkflowState) -> str:
        if state.get("confidence", 0) < 0.6:
            return "manual_review"
        return "agent_b"
    
    async def _run_agent_a(self, state: WorkflowState) -> WorkflowState:
        try:
            result = await asyncio.wait_for(
                self._agent_a.process(state["raw_content"]),
                timeout=10.0
            )
            return {**state, **result}
        except asyncio.TimeoutError:
            return {**state, "errors": state["errors"] + ["agent_a timeout"]}
    
    async def process(self, content: str, item_id: str) -> WorkflowState:
        initial_state = WorkflowState(
            input_id=item_id,
            raw_content=content,
            classification=None,
            confidence=None,
            summary=None,
            draft_reply=None,
            retry_count=0,
            errors=[],
            requires_human_review=False,
            processing_time_ms=None,
            model_used="gpt-4o-mini",
        )
        
        # IMPORTANTE: usar ainvoke() e não invoke()
        result = await self._graph.ainvoke(initial_state)
        return result
```

### Agente especializado (`src/agents/agent_a.py`)

```python
from openai import AsyncOpenAI
from src.config import get_settings

class AgentA:
    """Agente de classificação/análise inicial."""
    
    SYSTEM_PROMPT = """Você é um especialista em análise de [domínio].
    
Classifique a entrada em uma das categorias: [cat1, cat2, cat3].
Retorne um JSON com:
- category: string
- confidence: float (0.0 a 1.0)
- reasoning: string (breve justificativa)

Responda APENAS com JSON válido."""
    
    def __init__(self):
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
    
    async def process(self, content: str) -> dict:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        return {
            "classification": result["category"],
            "confidence": result["confidence"],
        }
```

---

## 6. Banco de Dados

### PostgreSQL com SQLAlchemy assíncrono

#### Configuração da engine (`src/models/database.py`)

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from src.config import get_settings

class Base(DeclarativeBase):
    pass

def create_engine_and_session():
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=10,
        max_overflow=20,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory

engine, AsyncSessionLocal = create_engine_and_session()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

#### Modelos ORM (`src/models/orm.py`)

```python
from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.database import Base

class ProcessedItem(Base):
    __tablename__ = "processed_items"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    raw_content: Mapped[str] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Float)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)   # sempre timezone-aware
    )
```

> **Atenção**: use sempre `datetime.now(timezone.utc)` — nunca `datetime.utcnow()`. O segundo cria objetos naive que causam conflitos com PostgreSQL timezone-aware.

#### Migrations com Alembic

```bash
# Inicializar
alembic init alembic

# Criar migration
alembic revision --autogenerate -m "initial_schema"

# Aplicar
alembic upgrade head

# Reverter
alembic downgrade -1
```

#### Schema SQL de referência

```sql
-- Tabela principal de itens processados
CREATE TABLE processed_items (
    id          VARCHAR(36)   PRIMARY KEY,
    raw_content TEXT          NOT NULL,
    classification VARCHAR(50) NOT NULL,
    confidence  FLOAT         NOT NULL,
    summary     TEXT,
    requires_review BOOLEAN   DEFAULT FALSE,
    created_at  TIMESTAMPTZ   DEFAULT NOW()
);

-- Tabela de feedback para aprendizado
CREATE TABLE feedback (
    id          SERIAL        PRIMARY KEY,
    item_id     VARCHAR(36)   REFERENCES processed_items(id),
    action      VARCHAR(20)   NOT NULL,   -- 'approved', 'rejected', 'edited'
    corrected_value TEXT,
    created_at  TIMESTAMPTZ   DEFAULT NOW()
);

-- Logs de auditoria (sem conteúdo sensível)
CREATE TABLE access_logs (
    id          SERIAL        PRIMARY KEY,
    endpoint    VARCHAR(200)  NOT NULL,
    method      VARCHAR(10)   NOT NULL,
    status_code INTEGER       NOT NULL,
    user_id     VARCHAR(36),
    ip_address  VARCHAR(45),
    created_at  TIMESTAMPTZ   DEFAULT NOW()
);
```

### ChromaDB (busca semântica)

```python
import chromadb
from chromadb.config import Settings

client = chromadb.HttpClient(
    host="localhost",
    port=8001,
    settings=Settings(anonymized_telemetry=False)
)

collection = client.get_or_create_collection(
    name="item_embeddings",
    metadata={"hnsw:space": "cosine"}
)

# Inserir embedding
collection.add(
    documents=["conteúdo do item"],
    metadatas=[{"category": "exemplo", "item_id": "123"}],
    ids=["item_123"]
)

# Buscar similares
results = collection.query(
    query_texts=["texto de consulta"],
    n_results=5
)
```

---

## 7. Processamento Assíncrono

### Celery + Redis (`src/tasks/celery_app.py`)

```python
from celery import Celery
from src.config import get_settings

settings = get_settings()

celery_app = Celery(
    "worker",
    broker=settings.redis_url,
    backend=settings.redis_url.replace("/0", "/1"),
    include=["src.tasks.process_item"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
    worker_max_tasks_per_child=100,
    task_soft_time_limit=25,
    task_time_limit=30,
)
```

### Task de processamento (`src/tasks/process_item.py`)

```python
import asyncio
from src.tasks.celery_app import celery_app
from src.agents.orchestrator import AgentOrchestrator

@celery_app.task(bind=True, max_retries=3)
def process_item_task(self, item_id: str, content: str):
    try:
        orchestrator = AgentOrchestrator()
        result = asyncio.run(orchestrator.process(content, item_id))
        return {"status": "completed", "item_id": item_id}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
```

### Executar o worker

```bash
celery -A src.tasks.celery_app:celery_app worker \
  --loglevel=info \
  --concurrency=10
```

---

## 8. Frontend — React + TypeScript

### Inicialização do projeto

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install react-router-dom @tanstack/react-query
```

### Configuração do Vite (`vite.config.ts`)

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

### Serviço de API (`src/services/api.ts`)

```typescript
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const API_KEY = import.meta.env.VITE_API_KEY || 'dev-api-key-2024'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
      ...options?.headers,
    },
    ...options,
  })
  
  if (!res.ok) throw new Error(`API Error: ${res.status}`)
  return res.json()
}

export const api = {
  getItems: () => request<Item[]>('/api/v1/items'),
  getItem: (id: string) => request<Item>(`/api/v1/items/${id}`),
  approveItem: (id: string) => request<void>(`/api/v1/items/${id}/approve`, { method: 'POST' }),
  rejectItem: (id: string) => request<void>(`/api/v1/items/${id}/reject`, { method: 'POST' }),
}
```

### WebSocket para tempo real (`src/services/websocket.ts`)

```typescript
export function createWebSocket(onMessage: (data: unknown) => void): WebSocket {
  const ws = new WebSocket(`ws://localhost:8000/api/v1/ws`)
  
  ws.onopen = () => console.log('WebSocket conectado')
  ws.onmessage = (event) => onMessage(JSON.parse(event.data))
  ws.onerror = (error) => console.error('WebSocket error:', error)
  ws.onclose = () => setTimeout(() => createWebSocket(onMessage), 3000)
  
  return ws
}
```

### Hook customizado com TanStack Query (`src/hooks/useItems.ts`)

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'

export function useItems() {
  return useQuery({
    queryKey: ['items'],
    queryFn: api.getItems,
    refetchInterval: 30_000,
  })
}

export function useApproveItem() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: (id: string) => api.approveItem(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['items'] }),
  })
}
```

---

## 9. Segurança

### Nunca versionado no Git

```gitignore
# .gitignore obrigatório
.env
*.pem
*.key
__pycache__/
.venv/
node_modules/
*.pyc
.DS_Store
```

### Criptografia de tokens OAuth (AES-256-GCM)

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64, os

class TokenEncryptionService:
    def __init__(self, key_b64: str):
        self._key = base64.b64decode(key_b64)
    
    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        cipher = AESGCM(self._key)
        ciphertext = cipher.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ciphertext).decode()
    
    def decrypt(self, encrypted: str) -> str:
        data = base64.b64decode(encrypted)
        nonce, ciphertext = data[:12], data[12:]
        cipher = AESGCM(self._key)
        return cipher.decrypt(nonce, ciphertext, None).decode()

# Gerar chave:
# python -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

### Guardrails para respostas de IA

```python
BLOCKED_TERMS = ["senha", "password", "cpf", "cartão", "confidencial"]

def validate_ai_response(response: str) -> str:
    """Garante que a IA não vaze dados sensíveis."""
    lower = response.lower()
    for term in BLOCKED_TERMS:
        if term in lower:
            raise ValueError(f"Resposta da IA contém termo bloqueado: {term}")
    return response
```

### Proteção contra prompt injection

```python
MAX_INPUT_LENGTH = 10_000
INJECTION_PATTERNS = ["ignore previous", "system:", "###", "<|im_start|>"]

def sanitize_input(text: str) -> str:
    if len(text) > MAX_INPUT_LENGTH:
        raise ValueError("Input excede tamanho máximo")
    for pattern in INJECTION_PATTERNS:
        if pattern.lower() in text.lower():
            raise ValueError("Padrão suspeito detectado no input")
    return text.strip()
```

---

## 10. Testes

### Configuração (`pyproject.toml`)

```toml
[project.optional-dependencies]
dev = [
    "hypothesis==6.119.3",
    "pytest==8.3.4",
    "pytest-asyncio==0.24.0",
    "pytest-cov==6.0.0",
    "httpx==0.28.1",
    "aiosqlite==0.20.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "property: property-based tests",
    "integration: integration tests",
]
```

### Teste unitário

```python
import pytest
from src.agents.agent_a import AgentA

@pytest.mark.asyncio
async def test_agent_a_classification():
    agent = AgentA()
    # mock do OpenAI client para testes unitários
    result = await agent.process("conteúdo de teste urgente")
    assert "classification" in result
    assert 0.0 <= result["confidence"] <= 1.0
```

### Teste property-based com Hypothesis

```python
from hypothesis import given, strategies as st
from src.models.api import ProcessItemRequest

@given(
    content=st.text(min_size=1, max_size=5000),
    item_id=st.uuids().map(str),
)
def test_request_always_valid(content, item_id):
    """Qualquer combinação de content + id deve criar request válido."""
    req = ProcessItemRequest(content=content, item_id=item_id)
    assert req.content == content.strip() or len(content.strip()) > 0
```

### Comandos de teste

```bash
# Unitários (CI — sem dependências externas)
pytest tests/unit/ -v

# Property-based
pytest tests/property/ -v --hypothesis-seed=0

# Integração (requer Docker rodando)
pytest tests/integration/ -v -m integration

# Cobertura completa
pytest --cov=src --cov-report=html --cov-fail-under=80

# CI (apenas unit para pipeline rápido)
pytest tests/unit/ --tb=short -q
```

---

## 11. Integração Low-Code / No-Code

### Por que usar Zapier

O Zapier atende o requisito de automação low-code/no-code sem precisar de infraestrutura adicional (sem ngrok, sem servidor público). Basta o backend enviar um POST para a URL do webhook do Zapier.

### Fluxo de integração

```
Backend Python → POST webhook → Zapier → Slack / Email / Sheets / etc.
```

### Endpoint de webhook no backend

```python
# src/api/routers/webhooks.py
from fastapi import APIRouter
import httpx
from src.config import get_settings

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

@router.post("/notify")
async def notify_external(payload: dict):
    """Repassa evento para Zapier."""
    settings = get_settings()
    if not settings.zapier_webhook_url:
        return {"skipped": True}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            settings.zapier_webhook_url,
            json=payload,
            timeout=5.0,
        )
    return {"status": response.status_code}
```

### Trigger automático no orquestrador

```python
# No final do pipeline, após processar:
async def _trigger_webhook(self, event_type: str, data: dict):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                self._settings.zapier_webhook_url,
                json={
                    "event_type": event_type,
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                timeout=5.0,
            )
    except Exception:
        pass  # nunca deixar webhook falhar o pipeline principal
```

### Configurar o Zap no Zapier

1. Criar conta em zapier.com
2. Criar novo Zap → **Trigger: Webhooks by Zapier → Catch Hook**
3. Copiar a URL gerada (ex: `https://hooks.zapier.com/hooks/catch/XXXXX/YYYYY/`)
4. Colocar no `.env`: `ZAPIER_WEBHOOK_URL=https://hooks.zapier.com/...`
5. **Action**: Slack → Send Channel Message
6. Testar com curl:

```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/SEU_ID/SEU_TOKEN/" \
  -H "Content-Type: application/json" \
  -d '{"event_type": "test", "message": "Pipeline funcionando!"}'
```

Retorno esperado: `{"status":"success"}`

---

## 12. DevOps e CI/CD

### Docker Compose (`docker-compose.yml`)

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: myapp
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  chromadb:
    image: chromadb/chroma:latest
    ports:
      - "8001:8000"
    volumes:
      - chroma_data:/chroma/chroma

volumes:
  postgres_data:
  chroma_data:
```

### GitHub Actions CI (`.github/workflows/ci.yml`)

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -e ".[dev]"
      
      - name: Run unit tests
        run: |
          cd backend
          pytest tests/unit/ -v --tb=short
      
      - name: Run property tests
        run: |
          cd backend
          pytest tests/property/ -v --hypothesis-seed=0
      
      - name: Check coverage
        run: |
          cd backend
          pytest tests/unit/ --cov=src --cov-fail-under=70 -q

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install flake8
      - run: flake8 backend/src --max-line-length=120 --exclude=.venv
```

---

## 13. Variáveis de Ambiente

Arquivo `.env.example` (commitar este, nunca o `.env`):

```dotenv
# =============================================================================
# Configuração do Projeto — copie para .env e preencha os valores
# =============================================================================

# Aplicação
APP_NAME="Meu Agente IA"
APP_VERSION="0.1.0"
DEBUG=false

# API
API_HOST=0.0.0.0
API_PORT=8000
API_KEY=coloque-uma-chave-segura-aqui

# CORS (frontend URLs)
CORS_ORIGINS=["http://localhost:3001"]

# Banco de Dados PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/myapp

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI
# Obtenha em: https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# ChromaDB
CHROMADB_HOST=localhost
CHROMADB_PORT=8001
CHROMADB_COLLECTION_NAME=item_embeddings

# Segurança
# Gere com: python -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
ENCRYPTION_KEY=

# JWT
JWT_SECRET_KEY=coloque-segredo-jwt-aqui
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Webhooks (Low-Code)
ENABLE_WEBHOOKS=true
ZAPIER_WEBHOOK_URL=https://hooks.zapier.com/hooks/catch/SEU_ID/SEU_TOKEN/

# Timeouts dos Agentes
AGENT_TIMEOUT_SECONDS=10
MAX_AGENT_RETRIES=3
```

---

## 14. Dependências com Versões Exatas

### Backend (`backend/pyproject.toml`)

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "meu-agente"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    # API
    "fastapi==0.115.6",
    "uvicorn[standard]==0.34.0",
    # Agentes IA
    "langgraph==0.2.60",
    "openai==1.58.1",
    "google-generativeai==0.8.3",        # opcional, se usar Gemini
    # Vector Store
    "chromadb==0.5.23",
    # Processamento assíncrono
    "celery[redis]==5.4.0",
    "redis==5.2.1",
    # Banco de dados
    "sqlalchemy[asyncio]==2.0.36",
    "alembic==1.14.0",
    "asyncpg==0.30.0",
    # Validação e config
    "pydantic==2.10.3",
    "pydantic-settings==2.7.0",
    # HTTP e WebSocket
    "httpx==0.28.1",
    "websockets==14.1",
    # Segurança
    "python-jose[cryptography]==3.3.0",
    "cryptography==44.0.0",
]

[project.optional-dependencies]
dev = [
    "hypothesis==6.119.3",
    "pytest==8.3.4",
    "pytest-asyncio==0.24.0",
    "pytest-cov==6.0.0",
    "httpx==0.28.1",
    "aiosqlite==0.20.0",
    "flake8==7.1.1",
]
```

### Frontend (`frontend/package.json`)

```json
{
  "name": "meu-agente-frontend",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "lint": "eslint . --ext ts,tsx"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.22.0",
    "@tanstack/react-query": "^5.101.2"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "^5.6.3",
    "vite": "^6.0.3"
  }
}
```

---

## 15. Padrões de Commit e Versionamento

### Convenção de commits semânticos

```
<tipo>(<escopo>): <descrição curta>

feat:     nova funcionalidade
fix:      correção de bug
docs:     mudança na documentação
refactor: refatoração sem mudança de comportamento
test:     adição ou correção de testes
style:    formatação, espaçamento (sem mudança de lógica)
chore:    tarefas de manutenção (deps, config)
ci:       mudanças no pipeline de CI/CD
```

**Exemplos:**
```
feat(agents): adiciona agente de classificação com OpenAI
fix(auth): corrige timezone naive/aware no PostgreSQL
docs(readme): adiciona exemplos de entrada e saída
test(property): adiciona testes Hypothesis para classificação
refactor(orchestrator): separa lógica de routing em função pura
ci: executa apenas unit tests no CI para evitar falhas de integração
```

### Estratégia de branches

```
main            ← produção, sempre estável
develop         ← integração contínua
feature/nome    ← novas funcionalidades (feature/agents, feature/api-layer)
bugfix/nome     ← correções (bugfix/timezone, bugfix-oauth)
```

### Tags de release

```bash
git tag -a v1.0.0 -m "Release inicial com pipeline completo"
git push origin v1.0.0
```

---

## 16. Checklist para Novo Projeto

Use esta lista ao iniciar um projeto com esta stack:

### Configuração inicial
- [ ] Criar repositório GitHub com `.gitignore` configurado
- [ ] Criar estrutura de diretórios conforme seção 3
- [ ] Configurar `pyproject.toml` com dependências exatas
- [ ] Criar `frontend/package.json` com dependências exatas
- [ ] Criar `.env.example` (nunca commitar `.env`)
- [ ] Gerar `ENCRYPTION_KEY` com Python

### Backend
- [ ] Implementar `src/config.py` com `pydantic-settings`
- [ ] Criar factory do FastAPI em `src/api/app.py`
- [ ] Configurar middleware de autenticação por API key
- [ ] Definir `WorkflowState` TypedDict para o LangGraph
- [ ] Implementar pelo menos 2 agentes especializados
- [ ] Montar o `StateGraph` no orchestrator com `ainvoke()`
- [ ] Configurar timeouts em todos os agentes
- [ ] Criar modelos ORM com `mapped_column`
- [ ] Configurar migrations Alembic
- [ ] Usar `datetime.now(timezone.utc)` em todos os campos de data

### Segurança
- [ ] Tokens OAuth criptografados (AES-256-GCM)
- [ ] Guardrails para respostas da IA
- [ ] Sanitização de inputs (anti-injection)
- [ ] Logs de auditoria sem conteúdo sensível
- [ ] `.env` no `.gitignore`

### Testes
- [ ] Testes unitários para cada agente
- [ ] Testes property-based com Hypothesis para propriedades críticas
- [ ] Testes de integração para endpoints principais
- [ ] CI configurado para rodar `tests/unit/` no push

### Frontend
- [ ] Proxy configurado no Vite para `/api` e `/ws`
- [ ] TanStack Query para gerenciamento de estado server
- [ ] WebSocket com reconexão automática
- [ ] TypeScript interfaces espelhando os modelos Pydantic

### Low-Code
- [ ] Criar conta no Zapier
- [ ] Configurar Zap: Webhook → Slack (ou outro destino)
- [ ] Adicionar `ZAPIER_WEBHOOK_URL` no `.env`
- [ ] Endpoint `POST /api/v1/webhooks/notify` no backend
- [ ] Trigger automático no final do pipeline
- [ ] Testar com `curl` antes da demonstração

### DevOps
- [ ] `docker-compose.yml` com PostgreSQL, Redis e ChromaDB
- [ ] GitHub Actions CI com lint + testes
- [ ] Branches `main` e `develop` configuradas
- [ ] Tags de release aplicadas (`v0.1.0`, `v1.0.0`)

---

## Comandos de Start Rápido

```bash
# 1. Infraestrutura (Docker)
docker compose up -d

# 2. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env    # preencher API keys
alembic upgrade head
uvicorn src.api.app:app --reload --port 8000

# 3. Worker Celery (terminal separado)
cd backend && source .venv/bin/activate
celery -A src.tasks.celery_app:celery_app worker --loglevel=info

# 4. Frontend
cd frontend
npm install
npm run dev              # http://localhost:3001

# 5. Testar webhook Zapier
curl -X POST "$ZAPIER_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"event_type": "test", "message": "Sistema funcionando!"}'
```

---

> Documento gerado com base no AI Email Agent System.  
> Stack validada em produção com 511 testes passando e pipeline CI/CD funcional.
