# Guia de Configuração Completo

## Pré-requisitos

- Docker Desktop instalado e rodando
- Node.js 18+ instalado
- Python 3.9+ instalado
- Conta Google (para Gmail + Gemini)

---

## Parte 1: Gerar Chaves Locais

Essas chaves são criadas por você e ficam apenas na sua máquina.

### 1.1 — API_KEY

Protege a API REST contra acessos não autorizados.

Abra o terminal e escolha uma string segura:

```
minha-api-key-secreta-2024
```

Pode ser qualquer texto. Exemplo mais seguro:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copie o resultado. Será usado em `backend/.env` e `frontend/.env`.

---

### 1.2 — ENCRYPTION_KEY

Chave AES-256 para criptografar tokens OAuth no banco. Precisa ser exatamente 32 bytes em base64.

```bash
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

Exemplo de saída: `k7Dq3mN+x2R8sPvL1bWt5Yf0jH6nA9cE4gUiKoMwZr0=`

Copie o resultado.

---

### 1.3 — JWT_SECRET_KEY

Segredo para assinar tokens JWT de autenticação.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Exemplo de saída: `aB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uV3wX4yZ5`

Copie o resultado.

---

## Parte 2: Obter GEMINI_API_KEY (Gratuito)

A chave do Gemini é o "cérebro" do sistema — usada para classificar, resumir e gerar respostas.

### Passo a passo:

1. Acesse: https://aistudio.google.com/apikey

2. Faça login com sua conta Google

3. Clique em **"Create API Key"**

4. Selecione um projeto existente ou crie um novo (qualquer nome serve)

5. A chave aparecerá na tela, algo como:
   ```
   AIzaSyD1a2B3c4D5e6F7g8H9i0J1k2L3m4N5o6P
   ```

6. Copie a chave

### Limites do plano gratuito:
- 15 requisições/minuto
- 1 milhão de tokens/dia
- Suficiente para desenvolvimento e testes

---

## Parte 3: Configurar OAuth do Gmail

Permite que o sistema leia e envie e-mails da sua conta Gmail.

### 3.1 — Criar projeto no Google Cloud

1. Acesse: https://console.cloud.google.com/

2. No topo, clique no seletor de projeto → **"New Project"**
   - Nome: `AI Email Agent` (ou qualquer nome)
   - Clique **Create**

3. Aguarde criar e selecione o projeto no seletor

---

### 3.2 — Ativar a Gmail API

1. No menu lateral: **APIs & Services** → **Library**

2. Pesquise por **"Gmail API"**

3. Clique no resultado e depois clique **"Enable"**

---

### 3.3 — Configurar a tela de consentimento OAuth

1. Menu lateral: **APIs & Services** → **OAuth consent screen**

2. Selecione **"External"** → clique **Create**

3. Preencha:
   - App name: `AI Email Agent`
   - User support email: seu email
   - Developer contact: seu email

4. Clique **Save and Continue**

5. Na tela de **Scopes**: clique **Add or Remove Scopes**
   - Pesquise e adicione:
     - `https://www.googleapis.com/auth/gmail.readonly`
     - `https://www.googleapis.com/auth/gmail.send`
   - Clique **Update** → **Save and Continue**

6. Na tela de **Test users**: clique **Add Users**
   - Adicione seu email Gmail
   - Clique **Save and Continue**

7. Revise e clique **Back to Dashboard**

---

### 3.4 — Criar credenciais OAuth 2.0

1. Menu lateral: **APIs & Services** → **Credentials**

2. Clique **"+ Create Credentials"** → **"OAuth client ID"**

3. Application type: **Web application**

4. Name: `AI Email Agent Local`

5. Em **Authorized redirect URIs**, clique **+ Add URI** e insira:
   ```
   http://localhost:8000/api/v1/auth/gmail/callback
   ```

6. Clique **Create**

7. Um modal aparecerá com:
   - **Client ID**: algo como `123456789-abcdef.apps.googleusercontent.com`
   - **Client Secret**: algo como `GOCSPX-AbCdEfGhIjKlMnOpQr`

8. Copie ambos

---

## Parte 4: Montar os Arquivos .env

### 4.1 — `backend/.env`

```bash
cd backend
cp .env.example .env
```

Abra `backend/.env` e preencha com as chaves obtidas:

```env
# --- Chaves obrigatórias ---
API_KEY=cole-sua-api-key-aqui
ENCRYPTION_KEY=cole-sua-encryption-key-aqui
JWT_SECRET_KEY=cole-seu-jwt-secret-aqui
GEMINI_API_KEY=cole-sua-gemini-key-aqui

# --- Gmail OAuth ---
GOOGLE_CLIENT_ID=cole-seu-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=cole-seu-GOCSPX-secret

# --- Infraestrutura (já funcionam com Docker padrão) ---
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/email_agent
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

O restante das variáveis pode ficar com os valores padrão do `.env.example`.

---

### 4.2 — `frontend/.env`

```bash
cd frontend
```

Crie o arquivo `frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
VITE_API_KEY=cole-a-mesma-api-key-do-backend
```

A `VITE_API_KEY` **deve ser idêntica** à `API_KEY` do `backend/.env`.

---

## Parte 5: Subir Tudo

### 5.1 — Docker (infraestrutura)

```bash
# Na raiz do projeto
docker compose up -d
```

Verifique:
```bash
docker ps
# Deve mostrar: email-agent-postgres, email-agent-redis, email-agent-chromadb
```

---

### 5.2 — Backend

```bash
cd backend
source .venv/bin/activate

# Criar as tabelas no banco
alembic upgrade head

# Iniciar o servidor
uvicorn src.api.app:create_app --factory --reload --port 8000
```

Teste:
```bash
curl http://localhost:8000/health
# Deve retornar: {"status":"healthy"}
```

---

### 5.3 — Frontend

```bash
cd frontend
npm install   # só precisa na primeira vez
npm run dev
```

Acesse: http://localhost:3000

---

### 5.4 — Celery Worker (opcional, para processamento em background)

Abra outro terminal:

```bash
cd backend
source .venv/bin/activate
celery -A src.tasks.celery_app worker --loglevel=info --concurrency=10
```

---

## Parte 6: Conectar sua Conta Gmail

1. Acesse o dashboard: http://localhost:3000

2. Clique em **"Configurações"** no menu

3. Clique **"Conectar Gmail"**

4. Você será redirecionado para o Google
   - Selecione sua conta
   - Clique "Continuar" (pode aparecer aviso de app não verificado — clique "Advanced" → "Go to AI Email Agent")
   - Conceda as permissões solicitadas

5. Após autorizar, você volta ao dashboard

6. O sistema começa a buscar e-mails automaticamente (a cada 60 segundos)

7. E-mails aparecerão no **Painel** classificados com categoria, prioridade e resumos

---

## Resolução de Problemas

| Problema | Solução |
|---|---|
| `relation "processed_emails" does not exist` | Execute `alembic upgrade head` no backend |
| `401 Invalid or missing API key` | Verifique que `VITE_API_KEY` = `API_KEY` |
| `Connection refused` no frontend | Backend precisa estar rodando na porta 8000 |
| Google OAuth erro "redirect_uri_mismatch" | O URI no Google Cloud deve ser exatamente `http://localhost:8000/api/v1/auth/gmail/callback` |
| `GEMINI_API_KEY` não funciona | Verifique se copiou a chave completa sem espaços |
| Docker containers não sobem | Execute `docker compose down` e depois `docker compose up -d` |
| ChromaDB timeout | Verifique se a porta 8001 está mapeada (`docker ps`) |

---

## Verificação Final

Checklist para confirmar que tudo está funcionando:

- [ ] `docker ps` mostra 3 containers healthy
- [ ] `curl http://localhost:8000/health` retorna `{"status":"healthy"}`
- [ ] `curl http://localhost:8000/api/v1/emails -H "X-API-Key: sua-key"` retorna `{"items":[],...}`
- [ ] http://localhost:3000 carrega o dashboard
- [ ] Conta Gmail conectada nas Configurações
- [ ] E-mails começam a aparecer no Painel após 60 segundos
