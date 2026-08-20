# 🛠️ Troubleshooting - AI Email Agent

## ❌ Problemas Comuns e Soluções

### 1. Frontend não carrega (localhost:3001)

**Sintomas**: Página não abre ou erro de conexão
```bash
# Verificar se o processo está rodando
lsof -i :3001

# Se não estiver rodando, reiniciar:
cd frontend
npm run dev
```

### 2. Backend não responde (localhost:8080)

**Sintomas**: Erro de API ou timeout
```bash
# Verificar status
curl http://localhost:8080/health

# Se não responder, reiniciar:
cd backend
source .venv/bin/activate
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8080 --reload
```

### 3. Dados não carregam no Frontend

**Sintomas**: Lista de emails vazia ou erro de autenticação

**Solução 1**: Verificar API Key
- Use: `dev-api-key-2024`
- Limpe localStorage se necessário: F12 > Application > Local Storage > Clear

**Solução 2**: Teste endpoints diretamente
```bash
# Teste dados demo
curl -H "X-API-Key: dev-api-key-2024" http://localhost:8080/api/v1/emails/demo
```

### 4. Erro de CORS

**Sintomas**: "Access to fetch blocked by CORS policy"

**Verificação**: CORS deve estar configurado para ambas as portas:
```python
# Em backend/src/config.py
cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]
```

### 5. Serviços Docker não rodando

**Sintomas**: Erro de conexão com PostgreSQL/Redis
```bash
# Verificar status
docker-compose ps

# Reiniciar se necessário
docker-compose down
docker-compose up -d
```

## 🔍 Comandos de Diagnóstico

### Verificar Todos os Serviços
```bash
# Frontend (deve retornar 200)
curl -s -I http://localhost:3001

# Backend Health (deve retornar {"status":"healthy"})
curl -H "X-API-Key: dev-api-key-2024" http://localhost:8080/health

# PostgreSQL (via Docker)
docker-compose exec postgres psql -U postgres -d email_agent -c "SELECT 1;"

# Redis (via Docker)  
docker-compose exec redis redis-cli ping
```

### Verificar Processos Ativos
```bash
# Frontend (Node/Vite)
ps aux | grep -E "(vite|npm.*dev)"

# Backend (Python/uvicorn)
ps aux | grep -E "(uvicorn|python.*app)"

# Docker services
docker-compose ps
```

### Verificar Logs
```bash
# Backend logs (se rodando via uvicorn)
tail -f backend/logs/app.log  # se existir

# Docker logs
docker-compose logs postgres
docker-compose logs redis
docker-compose logs chromadb
```

## 🔧 Reinicialização Completa

Se tudo falhar, use esta sequência:

```bash
# 1. Parar tudo
docker-compose down
pkill -f "uvicorn"
pkill -f "npm run dev"

# 2. Reiniciar infraestrutura
docker-compose up -d

# 3. Reiniciar backend
cd backend
source .venv/bin/activate
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8080 --reload &

# 4. Reiniciar frontend  
cd ../frontend
npm run dev &

# 5. Aguardar 30 segundos e testar
sleep 30
curl http://localhost:3001
curl -H "X-API-Key: dev-api-key-2024" http://localhost:8080/health
```

## 📞 Checklist de Verificação

- [ ] Docker Compose rodando: `docker-compose ps`
- [ ] PostgreSQL conectável: `docker-compose exec postgres psql -U postgres -c "SELECT 1;"`
- [ ] Redis respondendo: `docker-compose exec redis redis-cli ping`
- [ ] Backend health OK: `curl -H "X-API-Key: dev-api-key-2024" http://localhost:8080/health`
- [ ] Frontend acessível: `curl -I http://localhost:3001`
- [ ] API demo funcionando: `curl -H "X-API-Key: dev-api-key-2024" http://localhost:8080/api/v1/emails/demo`
- [ ] Login com API key: `dev-api-key-2024`

## 🆘 Se Nada Funcionar

1. **Cheque as portas**: `lsof -i :3001` e `lsof -i :8080`
2. **Verifique .env**: Backend deve ter `API_KEY=dev-api-key-2024`
3. **Limpe cache**: Ctrl+F5 no browser
4. **Reinicie Docker**: `docker-compose restart`
5. **Verifique logs**: Procure erros nos terminais

## ✅ Status Esperado

Quando tudo estiver funcionando:

```bash
$ curl -H "X-API-Key: dev-api-key-2024" http://localhost:8080/health
{"status":"healthy"}

$ curl -I http://localhost:3001
HTTP/1.1 200 OK

$ docker-compose ps
NAME                     COMMAND                  SERVICE    STATUS
email-agent-chromadb-1   "uvicorn chromadb.ap…"   chromadb   Up
email-agent-postgres-1   "docker-entrypoint.s…"   postgres   Up  
email-agent-redis-1      "docker-entrypoint.s…"   redis      Up
```

---
*Guia atualizado automaticamente*