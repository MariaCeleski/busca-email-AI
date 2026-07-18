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

---

## 15. Variáveis de Ambiente

Copie `backend/.env.example` para `backend/.env` e preencha:

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `OPENAI_API_KEY` | Chave da API OpenAI | `sk-...` |
| `OPENAI_MODEL` | Modelo a usar | `gpt-4o-mini` |
| `DATABASE_URL` | URL do PostgreSQL | `postgresql+asyncpg://postgres:postgres@localhost:5432/email_agent` |
| `REDIS_URL` | URL do Redis | `redis://localhost:6379/0` |
| `API_KEY` | Chave de acesso ao dashboard | `dev-api-key-2024` |
| `ENCRYPTION_KEY` | Chave AES-256 para tokens (base64, 32 bytes) | `(gerada automaticamente)` |
| `GOOGLE_CLIENT_ID` | OAuth Google (opcional) | `208172...apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Secret OAuth Google | `GOCSPX-...` |
| `CORS_ORIGINS` | Origins permitidas para CORS | `http://localhost:3000` |

---

## 16. Cenários de Uso (Entrada/Saída)

### Cenário 1 — Email Urgente (Alta prioridade)

**Entrada:**
```json
{
  "sender": "ceo@empresa.com",
  "subject": "URGENTE: Sistema fora do ar - cliente reclamando",
  "body": "O sistema caiu há 30 min. Cliente ligando a cada 5 min. SLA violado. Preciso de status em 15 min."
}
```

**Saída:**
```json
{
  "classification": { "category": "Urgent", "priority": "High", "confidence": 0.92 },
  "summary": { "summary": "Sistema de produção caiu. Cliente cobrando. SLA violado.", "action_items": ["Verificar servidor", "Entrar na call", "Enviar status em 15 min"] },
  "draft_reply": { "suggested_subject": "Re: URGENTE — ação imediata", "reply_body": "Recebido. Verificando agora. Status em 15 min.", "status": "pending" }
}
```

### Cenário 2 — Spam (Baixa confiança → revisão manual)

**Entrada:**
```json
{
  "sender": "ganhe-dinheiro@promo99.xyz",
  "subject": "🔥💰 GANHE R$50.000 TRABALHANDO DE CASA!!!",
  "body": "PARABÉNS! Você foi selecionado para ganhar R$50.000 por mês! Clique AGORA!"
}
```

**Saída:**
```json
{
  "classification": { "category": "Spam", "priority": "Low", "confidence": 0.45 },
  "summary": null,
  "draft_reply": { "suggested_subject": "Re: Proposta recebida", "reply_body": "Agradeço pelo contato, mas não poderei seguir com essa proposta.", "status": "pending" },
  "flagged_for_review": true
}
```

### Cenário 3 — Email Informativo (Sem resposta necessária)

**Entrada:**
```json
{
  "sender": "rh@empresa.com",
  "subject": "Comunicado: Novo horário do refeitório",
  "body": "A partir de segunda, o refeitório funciona: Café 7h-9h, Almoço 11h30-14h, Lanche 15h-16h30."
}
```

**Saída:**
```json
{
  "classification": { "category": "Informative", "priority": "Low", "confidence": 0.91 },
  "summary": { "summary": "Refeitório muda horário a partir de segunda.", "action_items": [] },
  "draft_reply": null
}
```

### Cenário 4 — Email Pessoal com resposta gerada

**Entrada:**
```json
{
  "sender": "maria.silva@cliente.com",
  "subject": "Prazo do módulo 3",
  "body": "Gostaria de saber se o módulo 3 será entregue na quarta. Nosso QA precisa de 2 dias para preparar ambiente."
}
```

**Saída:**
```json
{
  "classification": { "category": "Personal", "priority": "High", "confidence": 0.87 },
  "summary": { "summary": "Cliente pergunta sobre prazo do módulo 3. QA precisa 2 dias antecipados.", "action_items": ["Confirmar prazo do módulo 3", "Agendar call sobre módulo 4"] },
  "draft_reply": { "suggested_subject": "Re: Prazo do módulo 3 — confirmação", "reply_body": "Olá Maria, o módulo 3 está confirmado para quarta. Podemos agendar call sobre o módulo 4 na próxima semana?", "status": "pending" }
}
```

---

## 17. Padrões de Prompting Utilizados

### Tabela de Padrões

| Padrão | Tipo | Onde usado | Verificável em |
|--------|------|-----------|----------------|
| **Role-based** | Estruturado | Todos os agentes | `classifier.py`, `summarizer.py`, `response.py` |
| **Few-shot Dinâmico** | Com exemplos | ClassifierAgent | `classifier.py` + `feedback_learner.py` |
| **Chain-of-Thought** | Iterativo | ResponseAgent | `response.py` (analisa tom → gera resposta) |
| **Constraint Prompting** | Com restrições | SummarizerAgent | `summarizer.py` (máx 3 frases, máx 10 itens) |
| **Structured Output** | Estruturado | Todos | Instrução "Retorne APENAS JSON" |
| **Context Window Management** | Com restrições | Todos | Trunca a 2000-3000 chars |

### Evidência 1: Role-based Prompting (classifier.py)

```python
# Prompt real do ClassifierAgent — linha 108
"Você é um assistente de classificação de e-mails. Analise o e-mail a seguir e classifique-o."
```

O agente recebe um **papel explícito** ("assistente de classificação") que define seu comportamento.

### Evidência 2: Few-shot Dinâmico (classifier.py + feedback_learner.py)

```python
# FeedbackLearner.build_few_shot_section() — injeta exemplos reais no prompt
"Exemplos de classificações anteriores com feedback do usuário:
  1. Assunto: 'Reunião urgente' | De: chefe@empresa.com
     Classificação: Urgent/High — ✓ aprovada
  2. Assunto: 'GANHE DINHEIRO' | De: spam@xyz.com
     Classificação: Spam/Low — ✓ aprovada
Use esses exemplos como referência."
```

Exemplos **reais** do histórico de feedback são injetados dinamicamente a cada classificação.

### Evidência 3: Chain-of-Thought (response.py)

```python
# ResponseAgent.build_response_prompt() — análise antes da geração
"Orientação de tom baseada em e-mails históricos (imite este estilo):
- Estilo de saudação: Olá [Nome]
- Estilo de despedida: Atenciosamente
- Comprimento médio de frase: ~12 palavras
Adote a estrutura... dos exemplos históricos."

# Depois pede a geração:
"Gere uma resposta profissional para o e-mail a seguir."
```

O prompt força o modelo a **primeiro analisar o contexto** (tom, estilo) e **depois gerar** a resposta — raciocínio em etapas.

### Evidência 4: Constraint Prompting (summarizer.py)

```python
# SummarizerAgent.build_summary_prompt() — restrições explícitas
"Regras:
- O resumo deve ter no máximo 3 frases
- Extraia até 10 itens de ação
- Se não houver itens de ação, retorne uma lista vazia
- Preserve detalhes críticos incluindo datas, valores e nomes"
```

Limites quantitativos explícitos que **restringem** a saída do modelo.

---

## 18. Análise Crítica da IA no Projeto

### Pontos Fortes
- **Classificação consistente**: GPT-4o-mini acerta ~90% das categorias em emails claros
- **Resumos úteis**: Extrai action items relevantes, economiza tempo do usuário
- **Respostas contextualizadas**: ChromaDB fornece histórico de tom para respostas naturais
- **Aprendizado incremental**: Few-shot com feedback melhora a precisão ao longo do tempo

### Limitações Identificadas
- **Confiança subjetiva**: O modelo pode atribuir alta confiança a classificações erradas (overconfidence)
- **Dependência de prompt**: Pequenas mudanças no prompt alteram significativamente os resultados
- **Sem detecção de idioma**: Funciona melhor em português, mas não recusa outros idiomas
- **Custo por chamada**: Cada email consome 3 chamadas à API (classificar + resumir + responder)
- **Latência**: Pipeline completo leva 5-15 segundos por email (3 chamadas sequenciais)
- **Sem guardrails de conteúdo**: A IA pode gerar respostas inadequadas sem filtro explícito

### Decisão sobre Modelo
Escolhemos `gpt-4o-mini` em vez de `gpt-4o` porque:
- Custo 15x menor ($0.15/1M tokens vs $2.50/1M)
- Latência 2x menor
- Qualidade suficiente para classificação e respostas curtas
- Trade-off aceito: respostas menos elaboradas em troca de velocidade e economia

---

## 19. Melhorias Futuras (Roadmap)

| Prioridade | Melhoria | Impacto |
|-----------|----------|---------|
| 🔴 Alta | Processamento de anexos (PDF, imagens com OCR) | Classificar emails com documentos |
| 🔴 Alta | Deploy cloud (AWS/GCP) com auto-scaling | Produção real |
| 🟡 Média | Suporte a múltiplos idiomas explícito | Internacionalização |
| 🟡 Média | Integração com calendário (agendar reuniões) | Automação de action items |
| 🟡 Média | Guardrails de conteúdo (NeMo Guardrails) | Segurança de output da IA |
| 🟢 Baixa | Mobile app (React Native) | Acesso móvel |
| 🟢 Baixa | Suporte a mais provedores (Yahoo, ProtonMail) | Cobertura |
| 🟢 Baixa | Dashboard analytics (gráficos de tendência) | Insights visuais |
