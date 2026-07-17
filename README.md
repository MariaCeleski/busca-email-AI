# AI Email Agent — Sistema Multi-Agente de Gestão de E-mails

Sistema inteligente que automatiza a triagem, classificação, resumo e geração de respostas para e-mails usando agentes de IA orquestrados com **LangGraph**.

---

## 1. Problema

Profissionais recebem dezenas de e-mails diariamente e gastam tempo significativo classificando prioridades, lendo mensagens longas e redigindo respostas. Esse processo é repetitivo, propenso a erros e consome horas produtivas.

## 2. Objetivo do Agente

Construir um agente de IA que automatiza o processamento de e-mails em 3 etapas:

1. **Classificar** — determinar categoria (Urgente, Pessoal, Informativo, Spam, Promocional, Transacional) e prioridade (Alta, Média, Baixa)
2. **Resumir** — gerar resumo conciso (máx. 3 frases) + extrair itens de ação
3. **Responder** — gerar rascunho de resposta com tom contextualizado

O sistema inclui um fluxo de **revisão humana** (human-in-the-loop) onde o usuário aprova, edita ou rejeita respostas geradas.

## 3. Por que é um Agente?

Este sistema é um agente porque:
- Possui **objetivo autônomo** (processar e-mails sem intervenção constante)
- Toma **decisões condicionais** (se urgente → resumir + responder; se spam → apenas classificar)
- Usa **ferramentas externas** (Gmail API, ChromaDB, OpenAI)
- Mantém **estado e memória** (workflow state, feedback histórico)
- **Aprende** com feedback do usuário (few-shot prompting dinâmico)

---

## 4. Fluxo LangGraph (StateGraph)

```
┌─────────────────────────────────────────────────────────┐
│                  EmailWorkflowState                     │
│  (email, classification, summary, draft_reply, stage)   │
└─────────────────────────────────────────────────────────┘

         ┌──────────┐
         │  ENTRY   │
         └────┬─────┘
              │
              ▼
     ┌────────────────┐
     │   CLASSIFY     │  ← ClassifierAgent (OpenAI)
     │  (categoria,   │
     │  prioridade,   │
     │  confiança)    │
     └───────┬────────┘
             │
     ┌───────┴───────────────────────┐
     │     ROUTING CONDICIONAL       │
     ├───────────┬───────────────────┤
     │           │                   │
     ▼           ▼                   ▼
┌─────────┐ ┌────────── ┐  ┌──────────────────┐
│SUMMARIZE│ │GENERATE   │  │  MANUAL_REVIEW   │
│(se corpo│ │RESPONSE   │  │ (confiança < 0.6)│
│>200 pal)│ │(se urgente│  └──────────────────┘
└────┬────┘ │ou pessoal)│
     │      └─────┬─────┘
     │            │
     └─────┬──────┘
           ▼
  ┌─────────────────┐
  │ PUBLISH_RESULTS │  → Salva no banco
  └────────┬────────┘
           ▼
        ┌─────┐
        │ END │
        └─────┘
```

**Implementação:** `backend/src/agents/orchestrator.py` — usa `langgraph.graph.StateGraph` com nós, edges condicionais e estado tipado (`EmailWorkflowState`).

---

## 5. Ferramentas Integradas

| Ferramenta | Função no Agente |
|------------|-----------------|
| **OpenAI API** (gpt-4o-mini) | Classificação, sumarização e geração de respostas |
| **Gmail API** | Leitura de e-mails reais da caixa de entrada |
| **ChromaDB** | Busca semântica de e-mails similares para contextualizar o tom da resposta |
| **PostgreSQL** | Persistência de e-mails processados, rascunhos e feedback |
| **Redis + Celery** | Processamento assíncrono em background |

---

## 6. Contexto e Memória

- **Estado LangGraph** (`EmailWorkflowState`): armazena resultados intermediários de cada etapa
- **Few-shot dinâmico** (`FeedbackLearner`): consulta aprovações/rejeições anteriores do usuário e injeta como exemplos no prompt do Classificador
- **ChromaDB**: busca semântica do histórico para matching de tom na geração de respostas
- **PostgreSQL**: persiste todo o estado para consulta posterior

---

## 7. Segurança e Validação

- `.env` no `.gitignore` — credenciais nunca versionadas
- `.env.example` com nomes das variáveis (sem valores)
- Tokens OAuth encriptados com AES-256 (`TokenEncryptionService`)
- Validação de entrada com Pydantic (max_length, tipos, ranges)
- Timeout por agente (Classificador: 10s, Sumarizador: 8s, Resposta: 15s)
- Confiança limitada ao range [0.0, 1.0]
- Middleware de autenticação por API Key

---

## 8. Como Executar

### Pré-requisitos
- Docker e Docker Compose
- Python 3.9+
- Node.js 18+
- Chave de API da OpenAI

### Passos

```bash
# 1. Clonar o repositório
git clone https://github.com/MariaCeleski/busca-email-AI.git
cd busca-email-AI

# 2. Subir infraestrutura (PostgreSQL, Redis, ChromaDB)
docker compose up -d

# 3. Configurar backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Editar .env com sua OPENAI_API_KEY
alembic upgrade head

# 4. Iniciar backend
.venv/bin/python -m uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port 8000

# 5. Iniciar frontend (outro terminal)
cd frontend
npm install
npm run dev
```

Acesse: http://localhost:3000 — Login com API Key: `dev-api-key-2024`

---

## 9. Exemplo de Entrada e Saída

### Entrada (e-mail recebido)

```json
{
  "sender": "ceo@empresa.com",
  "subject": "URGENTE: Sistema fora do ar - cliente reclamando",
  "body": "O sistema de produção caiu há 30 minutos e o cliente principal está ligando a cada 5 minutos. Preciso de alguém do time de infraestrutura verificando AGORA..."
}
```

### Saída (processamento do agente)

```json
{
  "classification": {
    "category": "Urgent",
    "priority": "High",
    "confidence": 0.92
  },
  "summary": {
    "summary": "Sistema de produção caiu há 30 min. Cliente principal cobrando. SLA de 99.9% sendo violado. Precisa de status report em 15 min.",
    "action_items": [
      "Verificar servidor principal imediatamente",
      "Entrar na call de emergência",
      "Enviar status report em 15 minutos"
    ]
  },
  "draft_reply": {
    "suggested_subject": "Re: URGENTE: Sistema fora do ar - ação imediata",
    "reply_body": "Recebido. Estou verificando o servidor agora. Envio status em 15 minutos. Já entrei na call de emergência.",
    "status": "pending"
  }
}
```

---

## 10. Decisões Principais

| Decisão | Justificativa |
|---------|---------------|
| LangGraph para orquestração | Controle fino do fluxo com routing condicional e estado tipado |
| OpenAI (gpt-4o-mini) | Bom custo-benefício, respostas rápidas, suporte a JSON |
| Human-in-the-loop | E-mails são sensíveis — o humano deve validar antes do envio |
| Few-shot com feedback | Melhoria contínua sem re-treinar modelo |
| ChromaDB para busca semântica | Contexto histórico para gerar respostas com tom adequado |
| Celery + Redis | Processamento assíncrono para não bloquear a API |

---

## 11. Limitações

- Não processa anexos (PDF, imagens)
- Suporte apenas a Gmail e Outlook (não Yahoo, ProtonMail)
- Requer chave OpenAI com créditos ativos
- Sem deploy cloud (execução local via Docker)
- Few-shot limitado aos últimos 5 exemplos de feedback
- Sem suporte a múltiplos idiomas explícito (funciona melhor em português)

---

## 12. Estrutura do Projeto

```
├── backend/
│   ├── src/
│   │   ├── agents/           # Agentes IA (classifier, summarizer, response, orchestrator)
│   │   ├── api/              # FastAPI (routers, middleware)
│   │   ├── models/           # Pydantic models, ORM, enums
│   │   ├── providers/        # Gmail e Microsoft Graph clients
│   │   ├── security/         # Encriptação AES-256
│   │   ├── services/         # Feedback learner, vector store
│   │   └── tasks/            # Celery tasks (poll_emails)
│   ├── tests/                # 511 testes (pytest)
│   ├── alembic/              # Migrations PostgreSQL
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/       # EmailList, ReviewSection, StatsCards, etc.
│   │   ├── pages/            # Dashboard, EmailDetail, ManualReview, Feedback, Settings
│   │   ├── services/         # API client, WebSocket
│   │   └── styles/           # CSS global
│   └── package.json
├── docs/
│   ├── historico-prompts.md  # Registro de prompts utilizados
│   ├── architecture.md       # Arquitetura do sistema
│   ├── regras-desenvolvimento.md
│   ├── apresentacao-sala-de-aula.md
│   └── requisitos.md
└── docker-compose.yml
```

---

## 13. Documentação Adicional

- [Histórico de Prompts](docs/historico-prompts.md)
- [Arquitetura](docs/architecture.md)
- [Regras de Desenvolvimento](docs/regras-desenvolvimento.md)
- [Apresentação](docs/apresentacao-sala-de-aula.md)
- [Setup Guide](docs/setup-guide.md)

---

## 14. Tech Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.9+, FastAPI, LangGraph, SQLAlchemy (async) |
| IA | OpenAI GPT-4o-mini, ChromaDB (embeddings) |
| Frontend | React 18, TypeScript, Vite |
| Infraestrutura | PostgreSQL 16, Redis 7, Docker Compose |
| Testes | pytest (511 testes), TypeScript compiler |
| CI/CD | GitHub Actions |
