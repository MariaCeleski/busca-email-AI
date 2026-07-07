# Guia de APIs e Endereços para Configuração do .env

## Visão Geral

| Variável | Serviço | URL para obter | Custo |
|---|---|---|---|
| `GEMINI_API_KEY` | Google Gemini (IA) | https://aistudio.google.com/apikey | Gratuito |
| `GOOGLE_CLIENT_ID` | Gmail OAuth | https://console.cloud.google.com/apis/credentials | Gratuito |
| `GOOGLE_CLIENT_SECRET` | Gmail OAuth | https://console.cloud.google.com/apis/credentials | Gratuito |
| `MICROSOFT_CLIENT_ID` | Outlook OAuth | https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps | Gratuito |
| `MICROSOFT_CLIENT_SECRET` | Outlook OAuth | https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps | Gratuito |
| `API_KEY` | Interna (você cria) | Terminal local | — |
| `ENCRYPTION_KEY` | Interna (você cria) | Terminal local | — |
| `JWT_SECRET_KEY` | Interna (você cria) | Terminal local | — |

---

## 1. Google Gemini API (Classificação, Resumo, Respostas)

**O que é:** O LLM que classifica e-mails, gera resumos e rascunhos de resposta.

**URL:** https://aistudio.google.com/apikey

**Passos:**
1. Acessar o link acima
2. Login com conta Google
3. Clicar "Create API Key"
4. Selecionar/criar projeto
5. Copiar a chave gerada

**Variável no .env:**
```
GEMINI_API_KEY=AIzaSy...sua-chave
```

**Documentação oficial:** https://ai.google.dev/gemini-api/docs/api-key

**Limites gratuitos:** 15 req/min, 1M tokens/dia

---

## 2. Gmail API (Leitura e Envio de E-mails)

**O que é:** Permite ler e-mails da inbox e enviar respostas via Gmail.

### 2.1 — Ativar a API

**URL:** https://console.cloud.google.com/apis/library/gmail.googleapis.com

**Passos:**
1. Acessar o link acima
2. Selecionar o projeto (ou criar um novo)
3. Clicar "Enable"

### 2.2 — Configurar tela de consentimento OAuth

**URL:** https://console.cloud.google.com/apis/credentials/consent

**Passos:**
1. Acessar o link acima
2. User Type: "External" → Create
3. Preencher App name, email de suporte, email do desenvolvedor
4. Em Scopes: adicionar `gmail.readonly` e `gmail.send`
5. Em Test users: adicionar seu email Gmail
6. Salvar

### 2.3 — Criar credenciais OAuth

**URL:** https://console.cloud.google.com/apis/credentials

**Passos:**
1. Acessar o link acima
2. "+ Create Credentials" → "OAuth client ID"
3. Application type: "Web application"
4. Authorized redirect URIs: `http://localhost:8000/api/v1/auth/gmail/callback`
5. Clicar "Create"
6. Copiar Client ID e Client Secret

**Variáveis no .env:**
```
GOOGLE_CLIENT_ID=123456789-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-AbCdEfGh...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/gmail/callback
```

**Documentação oficial:** https://developers.google.com/gmail/api/guides

---

## 3. Microsoft Graph API (Outlook — Alternativa ao Gmail)

**O que é:** Permite ler e-mails e enviar respostas via Outlook/Microsoft 365.

### 3.1 — Registrar aplicação

**URL:** https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade

**Passos:**
1. Acessar o link acima
2. Login com conta Microsoft
3. "+ New registration"
4. Name: "AI Email Agent"
5. Supported account types: "Accounts in any organizational directory and personal Microsoft accounts"
6. Redirect URI: Web → `http://localhost:8000/api/v1/auth/microsoft/callback`
7. Clicar "Register"
8. Copiar o **Application (client) ID** da página Overview

### 3.2 — Criar Client Secret

**URL:** https://portal.azure.com → App registrations → Sua app → "Certificates & secrets"

**Passos:**
1. Abrir a app registrada
2. Menu lateral: "Certificates & secrets"
3. "+ New client secret"
4. Description: "ai-email-agent-dev"
5. Expires: 24 months
6. Clicar "Add"
7. Copiar o **Value** (aparece apenas uma vez!)

### 3.3 — Adicionar permissões

**URL:** https://portal.azure.com → App registrations → Sua app → "API permissions"

**Passos:**
1. "+ Add a permission"
2. Selecionar "Microsoft Graph"
3. "Delegated permissions"
4. Adicionar:
   - `Mail.ReadWrite`
   - `Mail.Send`
   - `offline_access`
5. Clicar "Add permissions"

**Variáveis no .env:**
```
MICROSOFT_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MICROSOFT_CLIENT_SECRET=valor-do-secret-criado
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/v1/auth/microsoft/callback
MICROSOFT_TENANT_ID=common
```

**Documentação oficial:** https://learn.microsoft.com/en-us/graph/auth/

---

## 4. Chaves Geradas Localmente

Essas não requerem nenhum serviço externo. Execute no terminal:

### 4.1 — API_KEY

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Variável no .env:**
```
API_KEY=resultado-do-comando-acima
```

### 4.2 — ENCRYPTION_KEY

```bash
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

**Variável no .env:**
```
ENCRYPTION_KEY=resultado-do-comando-acima
```

### 4.3 — JWT_SECRET_KEY

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Variável no .env:**
```
JWT_SECRET_KEY=resultado-do-comando-acima
```

---

## 5. Infraestrutura Local (Docker)

Estas variáveis já vêm preenchidas no `.env.example` e funcionam com o Docker padrão:

| Variável | Valor padrão | Serviço |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/email_agent` | PostgreSQL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery Broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery Results |
| `CHROMADB_HOST` | `localhost` | ChromaDB |
| `CHROMADB_PORT` | `8001` | ChromaDB |

**Não precisa alterar** a menos que mude as portas do Docker.

---

## 6. Frontend (.env)

Crie `frontend/.env`:

```
VITE_API_URL=http://localhost:8000
VITE_API_KEY=mesma-api-key-do-backend
```

---

## Resumo de URLs Importantes

| Ação | URL |
|---|---|
| Criar Gemini API Key | https://aistudio.google.com/apikey |
| Google Cloud Console | https://console.cloud.google.com/ |
| Ativar Gmail API | https://console.cloud.google.com/apis/library/gmail.googleapis.com |
| Criar OAuth Credentials (Google) | https://console.cloud.google.com/apis/credentials |
| Configurar OAuth Consent (Google) | https://console.cloud.google.com/apis/credentials/consent |
| Azure App Registrations | https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps |
| Docs Gemini API | https://ai.google.dev/gemini-api/docs |
| Docs Gmail API | https://developers.google.com/gmail/api |
| Docs Microsoft Graph | https://learn.microsoft.com/en-us/graph/overview |
