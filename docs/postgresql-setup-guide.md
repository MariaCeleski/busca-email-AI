# 🐘 Guia de Instalação PostgreSQL - AI Email Agent System

## Problema Identificado
- ❌ PostgreSQL não está instalado no sistema
- ❌ MCP server "postgres" falha com "spawn npx ENOENT"
- ✅ Node.js está instalado via NVM

---

## 🚀 Soluções Disponíveis

### Opção A: PostgreSQL via Homebrew (Recomendado)
```bash
# Instalar PostgreSQL
brew install postgresql@14

# Iniciar serviço
brew services start postgresql@14

# Criar usuário e database
createuser -s postgres
createdb email_agent

# Testar conexão
psql -U postgres -d email_agent -c "SELECT version();"
```

### Opção B: PostgreSQL via App (Mais Simples)
```bash
# Baixar e instalar Postgres.app
# https://postgresapp.com/

# Adicionar ao PATH (adicione ao ~/.zshrc)
export PATH=$PATH:/Applications/Postgres.app/Contents/Versions/latest/bin

# Recarregar terminal
source ~/.zshrc

# Criar database
createdb email_agent
```

### Opção C: PostgreSQL via Docker (Isolado)
```bash
# Criar e rodar container PostgreSQL
docker run -d \
  --name postgres-email-agent \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=email_agent \
  -p 5432:5432 \
  postgres:14

# Testar conexão
docker exec -it postgres-email-agent psql -U postgres -d email_agent
```

---

## ⚡ Solução Temporária: Desabilitar MCP PostgreSQL

Se você quiser continuar sem PostgreSQL por enquanto: