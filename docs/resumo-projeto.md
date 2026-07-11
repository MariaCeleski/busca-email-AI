# AI Email Agent System — Resumo Detalhado do Projeto

## O que é

O **AI Email Agent System** é um sistema inteligente de gerenciamento de e-mails que utiliza múltiplos agentes de Inteligência Artificial coordenados para automatizar o processamento de mensagens recebidas. Ele monitora caixas de entrada (Gmail e Outlook), classifica automaticamente cada e-mail por categoria e urgência, gera resumos de mensagens longas, e cria rascunhos de resposta contextualmente relevantes — tudo isso antes de apresentar os resultados em um dashboard para aprovação humana.

O conceito central é o **human-in-the-loop**: a IA faz o trabalho pesado de análise e redação, mas o ser humano mantém o controle final sobre o que é enviado.

---

## Como Funciona (Pipeline Completo)

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐     ┌──────────────┐     ┌───────────┐
│ Gmail/      │────▶│ Email        │────▶│ Classifier     │────▶│ Summarizer/  │────▶│ Dashboard │
│ Outlook     │     │ Monitor      │     │ Agent          │     │ Response     │     │ (React)   │
│             │     │ (polling/    │     │ (Gemini LLM)   │     │ Agent        │     │           │
│             │     │  webhook)    │     │                │     │              │     │ Approve/  │
│             │     │              │     │ Categoriza     │     │ Resumir ou   │     │ Edit/     │
│             │     │ Dedup +      │     │ + Prioriza     │     │ Gerar Reply  │     │ Reject    │
└─────────────┘     │ Fila Celery  │     │ + Confiança    │     │              │     └───────────┘
                    └──────────────┘     └────────────────┘     └──────────────┘
```

### Etapa 1: Monitoramento
- O **Email Monitor** verifica a caixa de entrada a cada 60 segundos (configurável) ou recebe webhooks em tempo real
- Cada e-mail novo é deduplicado (evita processamento duplicado) e colocado em uma fila de tarefas assíncronas (Celery + Redis)

### Etapa 2: Classificação
- O **Classifier Agent** analisa o assunto e corpo do e-mail usando Google Gemini
- Atribui: **categoria** (Urgente, Informativo, Promocional, Spam, Transacional, Pessoal), **prioridade** (Alta, Média, Baixa) e **confiança** (0.0 a 1.0)
- E-mails com confiança < 0.6 são automaticamente sinalizados para revisão manual

### Etapa 3: Roteamento Inteligente
O **Orchestrador** (LangGraph StateGraph) decide o próximo passo:
- **Urgente/Pessoal + Alta/Média prioridade** → Response Agent (gera rascunho de resposta)
- **Informativo/Promocional/Spam/Transacional** → Summarizer Agent (gera resumo)
- **Urgente + corpo > 200 palavras** → Dual path: resumo E resposta
- **Confiança < 0.6** → Revisão manual (humano decide)

### Etapa 4: Sumarização
- O **Summarizer Agent** condensa e-mails longos em no máximo 3 frases
- Extrai até 10 itens de ação (tarefas mencionadas no e-mail)
- Se o LLM falhar: retorna as primeiras 3 sentenças como fallback

### Etapa 5: Geração de Resposta
- O **Response Agent** busca os 5 e-mails históricos mais similares via busca semântica (ChromaDB)
- Analisa o tom dos e-mails anteriores (estilo de saudação, despedida, comprimento de frase)
- Gera um rascunho que imita o estilo de comunicação do usuário
- Se não houver histórico relevante: usa tom profissional neutro

### Etapa 6: Dashboard (Human-in-the-Loop)
- O humano visualiza classificação, resumo e rascunho de resposta
- Pode **Aprovar** (envia imediatamente), **Editar** (modifica e envia), ou **Rejeitar** (marca para resposta manual)
- Notificações em tempo real via WebSocket

---

## Funcionalidades Principais

| Funcionalidade | Descrição |
|----------------|-----------|
| **Classificação automática** | Categoriza e prioriza cada e-mail com IA |
| **Sumarização inteligente** | Resume e-mails longos em 3 frases + itens de ação |
| **Geração de resposta contextual** | Cria rascunhos que imitam o tom do usuário |
| **Busca semântica** | Encontra e-mails similares por significado, não apenas palavras-chave |
| **Dashboard em tempo real** | Interface web com atualizações instantâneas via WebSocket |
| **Human-in-the-loop** | Humano aprova/edita/rejeita antes do envio |
| **Multi-provedor** | Gmail e Microsoft Outlook/Graph API |
| **Retry inteligente** | 3 tentativas por agente, circuit breaker para APIs externas |
| **Segurança** | Tokens OAuth criptografados AES-256, autenticação JWT |
| **Processamento concorrente** | Até 10 e-mails simultâneos via Celery workers |
| **Deduplicação** | Nunca processa o mesmo e-mail duas vezes |
| **Exclusão de dados** | Desconexão de conta apaga todos os dados em 24h |

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| **Backend** | Python 3.9+, FastAPI, Uvicorn |
| **Orquestração de Agentes** | LangGraph (StateGraph com routing condicional) |
| **LLM** | Google Gemini 2.0 Flash (classificação, sumarização, geração) |
| **Embeddings** | Gemini Embedding 001 (3072 dimensões) |
| **Busca Vetorial** | ChromaDB (similaridade por cosseno) |
| **Banco de Dados** | PostgreSQL 16 + SQLAlchemy + Alembic |
| **Fila de Tarefas** | Celery + Redis |
| **Frontend** | React 18, TypeScript, Vite, TanStack Query |
| **Tempo Real** | WebSocket (FastAPI nativo) |
| **Segurança** | AES-256-GCM, JWT (python-jose), OAuth 2.0 |
| **Infraestrutura** | Docker Compose (PostgreSQL, Redis, ChromaDB) |
| **CI/CD** | GitHub Actions (pytest + TypeScript build) |

---

## Onde Pode Ser Aplicado

### 1. Profissionais com Alto Volume de E-mail
- **Executivos, gerentes, advogados, médicos** que recebem dezenas/centenas de e-mails por dia
- O sistema prioriza o que é urgente e pré-redige respostas, economizando horas de trabalho
- **Estimativa de economia:** 1-2 horas/dia para quem recebe 100+ e-mails

### 2. Atendimento ao Cliente / Suporte
- Triagem automática de tickets recebidos por e-mail
- Classificação por tipo (reclamação, dúvida, elogio, solicitação)
- Rascunhos de resposta baseados em respostas históricas da empresa
- **Reduz tempo de primeira resposta de horas para minutos**

### 3. Equipes de Vendas (Sales)
- Identificação automática de leads quentes (e-mails "Urgente" + "Pessoal")
- Geração de follow-ups contextualizados
- Resumo de threads longos de negociação
- Integração com CRM (extensível via MCP)

### 4. Departamentos Jurídicos
- Classificação de comunicações por tipo (contrato, litígio, compliance, informativo)
- Resumo de e-mails extensos de processos judiciais
- Priorização de prazos mencionados no corpo do e-mail
- **Os itens de ação extraídos podem alimentar sistemas de gestão de prazos**

### 5. Equipes de TI / DevOps
- Triagem de alertas de monitoramento recebidos por e-mail
- Classificação automática de severidade (P1, P2, P3)
- Resumo de logs/relatórios de incidentes
- Rascunhos de comunicação para stakeholders durante incidentes

### 6. Assistentes Virtuais / Secretárias
- Automação parcial de tarefas de triagem e resposta
- O dashboard funciona como "central de comandos" para gestão de e-mails de múltiplas contas
- Liberação de tempo para tarefas de maior valor

### 7. Pesquisadores / Acadêmicos
- Resumo automático de e-mails de editoras, revistas, conferências
- Priorização de convites para revisão de artigos
- Manutenção de contexto em threads longas de colaboração

### 8. Empresas (Nível Organizacional)
- Deploy como serviço interno para toda a empresa
- Governança: logs de acesso sem conteúdo de e-mail (compliance LGPD/GDPR)
- Deleção completa de dados quando funcionário desconecta conta
- Multi-tenant: cada usuário tem dados isolados

---

## Diferenciais Técnicos

| Diferencial | Por quê importa |
|-------------|----------------|
| **Multi-agente com LangGraph** | Cada agente é especialista; o orquestrador decide quem atua |
| **Busca semântica por significado** | Encontra contexto histórico mesmo sem palavras iguais |
| **Tone matching** | Respostas geradas soam como o próprio usuário escreveu |
| **Circuit breaker** | Sistema degrada graciosamente quando APIs externas falham |
| **Dual path routing** | E-mails urgentes longos recebem TANTO resumo quanto resposta |
| **Zero trust on send** | Nenhuma resposta é enviada sem aprovação humana explícita |
| **Privacy by design** | Tokens criptografados, logs sem conteúdo, deleção completa em 24h |

---

## Métricas do Projeto

| Métrica | Valor |
|---------|-------|
| Testes automatizados | 511 (unit + integration + property) |
| Endpoints REST | 9 + 1 WebSocket |
| Agentes de IA | 3 (Classifier, Summarizer, Response) |
| Tabelas no banco | 6 (users, accounts, emails, drafts, logs, workflows) |
| Páginas no frontend | 6 (Dashboard, Detail, Review, Settings, Auth, OAuth) |
| Componentes React | 8 |
| Documentação | 5 documentos + spec completa |
| Linhas de código estimadas | ~12.000 (backend + frontend + testes) |

---

## Limitações Conhecidas

1. **Requer chave de API LLM** — Gemini ou OpenAI (custo por uso)
2. **OAuth requer aprovação Google/Microsoft** — Apps em produção precisam verificação
3. **Não processa anexos** — Extrai apenas metadados (nome, tamanho, tipo)
4. **Latência do LLM** — Classificação ~2-5s, resposta ~5-15s por e-mail
5. **Sem suporte a idioma específico** — O LLM responde no idioma do e-mail recebido (comportamento default do Gemini)

---

## Evolução Futura (Roadmap)

- [ ] Processamento de anexos (PDF, imagens com OCR)
- [ ] Suporte a múltiplos idiomas explícito
- [ ] Aprendizado por feedback (melhorar classificação com base em approve/reject)
- [ ] Integração com calendário (agendar reuniões mencionadas em e-mails)
- [ ] Mobile app (React Native)
- [ ] Deploy cloud (AWS/GCP) com auto-scaling
- [ ] Suporte a mais provedores (Yahoo, ProtonMail)

---

*Documento gerado em Julho 2026 como parte do projeto acadêmico AI Email Agent System.*


---

## Como Usar — Guia Passo a Passo do Usuário

### Pré-requisitos

Antes de usar o sistema, você precisa ter:
1. **Docker Desktop** instalado e rodando
2. **Node.js 18+** (para o frontend)
3. **Python 3.9+** (para o backend)
4. Uma **chave de API do Google Gemini** (gratuita em https://aistudio.google.com/apikey)
5. (Opcional) Credenciais OAuth do Gmail ou Microsoft para conectar contas reais

---

### Passo 1: Subir a Infraestrutura

```bash
# Na raiz do projeto
docker compose up -d
```

Isso inicia 3 containers:
- **PostgreSQL** (banco de dados) — porta 5432
- **Redis** (fila de tarefas) — porta 6379
- **ChromaDB** (busca vetorial) — porta 8001

---

### Passo 2: Configurar Variáveis de Ambiente

```bash
# Copie o template
cp backend/.env.example backend/.env

# Edite o .env e preencha pelo menos:
# - API_KEY (qualquer valor para desenvolvimento, ex: "minha-chave-dev")
# - GEMINI_API_KEY (obtida no Google AI Studio)
# - ENCRYPTION_KEY (gere com o comando abaixo)
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

---

### Passo 3: Executar Migrations do Banco

```bash
cd backend
source .venv/bin/activate   # ou: .venv/bin/python
alembic upgrade head
```

Isso cria as 6 tabelas necessárias no PostgreSQL.

---

### Passo 4: Iniciar o Backend

```bash
cd backend
.venv/bin/python -m uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

O backend estará disponível em: **http://localhost:8000**
- Documentação interativa (Swagger): http://localhost:8000/docs
- Health check: http://localhost:8000/health

---

### Passo 5: Iniciar o Frontend

```bash
cd frontend
npm install   # apenas na primeira vez
npm run dev
```

O dashboard estará disponível em: **http://localhost:3000**

---

### Passo 6: Fazer Login no Dashboard

1. Abra http://localhost:3000 no navegador
2. Na tela de login, digite a **API Key** que você configurou no `.env` (campo `API_KEY`)
3. Clique em "Continue"
4. Você será redirecionado ao Dashboard principal

---

### Passo 7: Conectar uma Conta de E-mail

1. No menu lateral, vá em **Settings**
2. Clique em **"Connect Gmail"** ou **"Connect Outlook"**
3. Você será redirecionado para a tela de consentimento OAuth do Google/Microsoft
4. Autorize o acesso de leitura e envio
5. Após autorizar, você volta ao dashboard com a conta conectada

> **Nota:** Para desenvolvimento sem OAuth real, o sistema funciona com e-mails inseridos manualmente via API.

---

### Passo 8: Acompanhar o Processamento

Uma vez conectada a conta:

1. **Emails chegam automaticamente** — O monitor busca novos e-mails a cada 60 segundos
2. **Ou clique em "Fetch"** — Busca manual via botão no dashboard
3. **O pipeline processa em background:**
   - Classificação aparece em segundos (badge colorido + prioridade)
   - Resumo aparece para e-mails longos
   - Rascunho de resposta aparece para e-mails urgentes/pessoais
4. **Notificação em tempo real** — O dashboard atualiza automaticamente via WebSocket

---

### Passo 9: Revisar e Agir sobre E-mails

#### Na lista de e-mails:
- E-mails são mostrados com **categoria** (badge colorido), **prioridade**, **confiança**
- Seção amarela no topo mostra e-mails que precisam de **revisão manual** (confiança baixa)
- Filtros: por categoria, prioridade, data

#### No detalhe de um e-mail:
- **Conteúdo completo** do e-mail
- **Resumo** (se gerado): 3 frases + lista de itens de ação
- **Rascunho de resposta** (se gerado): com botões de ação

#### Ações sobre o rascunho:
| Ação | O que acontece |
|------|----------------|
| **Approve & Send** | Envia o rascunho exatamente como está |
| **Edit** | Abre editor para modificar corpo (max 10.000 chars) e assunto (max 255 chars), depois envia |
| **Reject** | Marca para resposta manual, remove da fila |
| **Retry** | Aparece se o envio falhou — tenta enviar novamente |

---

### Passo 10: Desconectar Conta (se necessário)

1. Vá em **Settings**
2. Clique em **"Disconnect"** na conta desejada
3. Confirme — o sistema irá:
   - Revogar tokens OAuth
   - Deletar TODOS os e-mails processados daquela conta
   - Deletar todos os embeddings vetoriais
   - Confirmação aparece quando a deleção é concluída

---

## Fluxo Visual do Usuário

```
┌──────────────────────────────────────────────────────────────┐
│                        USUÁRIO                                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Login (API Key)                                          │
│       │                                                      │
│       ▼                                                      │
│  2. Dashboard — Lista de E-mails                             │
│       │                                                      │
│       ├─── ⚠️ Seção "Revisão Manual" (confiança < 0.75)      │
│       │                                                      │
│       ├─── 📋 Lista paginada (filtros: categoria/prioridade) │
│       │                                                      │
│       ▼                                                      │
│  3. Clica em um e-mail → Detalhe                             │
│       │                                                      │
│       ├─── 📧 Conteúdo completo                              │
│       ├─── 📋 Resumo (se > 200 palavras)                     │
│       ├─── ✉️ Rascunho de Resposta                            │
│       │       │                                              │
│       │       ├── ✅ Approve & Send                          │
│       │       ├── ✏️ Edit → Approve                           │
│       │       └── ❌ Reject                                  │
│       │                                                      │
│       ▼                                                      │
│  4. Settings — Gerenciar Contas                              │
│       │                                                      │
│       ├── Connect Gmail / Outlook                            │
│       ├── Ver status das contas                              │
│       └── Disconnect (deleta dados)                          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Exemplo Prático de Uso

### Cenário: Gerente de Projetos com 80 e-mails não lidos

**Sem o sistema:** Lê cada e-mail manualmente (~2 horas), decide prioridade mentalmente, redige respostas do zero.

**Com o sistema:**

1. **8:00** — Abre o dashboard. 80 e-mails já classificados:
   - 🔴 5 urgentes (clientes com problemas)
   - 🔵 12 pessoais (equipe pedindo aprovação)
   - 🟢 25 informativos (relatórios, newsletters)
   - 🟡 20 transacionais (confirmações, recibos)
   - ⚫ 18 spam/promocional

2. **8:02** — Olha primeiro os 5 urgentes. Cada um já tem:
   - Resumo: "Cliente X reporta falha no módulo de pagamento desde ontem. Afeta 200 usuários."
   - Itens de ação: ["Verificar logs do servidor", "Notificar equipe de pagamentos", "Responder cliente em 1h"]
   - Rascunho: "Olá [nome], obrigado por reportar. Estamos investigando o problema com prioridade máxima..."

3. **8:05** — Aprova 3 rascunhos como estão, edita 1 (adiciona informação técnica), rejeita 1 (precisa investigar antes)

4. **8:10** — Revisa os 12 pessoais. Aprova 8 respostas geradas, edita 4.

5. **8:20** — Os informativos já têm resumo. Lê os resumos em vez dos e-mails completos. 25 e-mails em 5 minutos.

6. **8:25** — Ignora spam. Marca transacionais como lidos.

**Resultado:** 80 e-mails processados em **25 minutos** em vez de 2 horas. Economia de **1h35min**.

---

## Comandos Rápidos (Cheat Sheet)

```bash
# Subir tudo (infraestrutura + backend + frontend)
docker compose up -d
cd backend && .venv/bin/python -m uvicorn src.api.app:create_app --factory --port 8000 --reload &
cd frontend && npm run dev &

# Parar tudo
docker compose down
# (Ctrl+C nos terminais do backend e frontend)

# Rodar testes
cd backend && .venv/bin/python -m pytest tests/ -v

# Ver logs do backend
# O terminal do uvicorn mostra logs em tempo real

# Buscar e-mails manualmente via API
curl -X POST http://localhost:8000/api/v1/emails/fetch \
  -H "X-API-Key: sua-api-key"

# Ver lista de e-mails processados
curl http://localhost:8000/api/v1/emails \
  -H "X-API-Key: sua-api-key"
```

---

## Perguntas Frequentes

**P: Preciso de conta Gmail ou Outlook para testar?**
R: Não. Para desenvolvimento, você pode inserir e-mails via API ou rodar sem conta conectada (o dashboard funciona, mas sem dados reais).

**P: Quanto custa o uso do Gemini?**
R: O Google Gemini tem tier gratuito generoso (60 requests/minuto no Flash). Para uso pessoal, geralmente é gratuito.

**P: Meus e-mails ficam armazenados?**
R: Sim, no PostgreSQL local e ChromaDB local (ambos rodando no seu computador via Docker). Ao desconectar a conta, tudo é deletado em até 24h.

**P: A IA pode enviar e-mails sem minha aprovação?**
R: Nunca. O sistema é human-in-the-loop: toda resposta requer clique explícito em "Approve & Send".

**P: Posso usar OpenAI em vez do Gemini?**
R: Sim. Basta configurar `OPENAI_API_KEY` no `.env`. Os agentes suportam ambos os provedores.

---

*Última atualização: Julho 2026*
