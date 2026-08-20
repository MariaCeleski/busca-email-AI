# 🎨 Guia de Configuração Make.com - AI Email Agent System

## 🎯 Objetivo

Configurar automação visual no Make.com que consome a API do AI Email Agent System e executa ações baseadas no processamento de emails.

## 📋 Pré-requisitos

1. ✅ Backend rodando com webhook endpoints (`/api/v1/webhooks/make`)
2. ✅ Conta Make.com criada (gratuita ou paga)
3. ✅ API key configurada no backend (`dev-api-key-2024`)

## 🚀 Passo a Passo

### **1. Criar Conta Make.com**

1. Acesse: https://make.com
2. Clique em "Get Started Free"
3. Crie conta com email
4. Confirme email e faça login

### **2. Criar Novo Scenario**

1. No dashboard, clique em "Create a new scenario"
2. Nome do scenario: "AI Email Agent - Status Monitor"
3. Selecione pasta/team conforme necessário

### **3. Configurar Trigger (Timer)**

1. Clique no "+" para adicionar primeiro módulo
2. Busque por "Tools" → Selecione "Timer"
3. Configure:
   - **Type**: Interval
   - **Interval**: Every 5 minutes
   - **Start date**: Now
4. Clique "OK"

### **4. Adicionar HTTP Request**

1. Clique no "+" após o Timer
2. Busque por "HTTP" → Selecione "HTTP - Make a request"
3. Configure:
   - **URL**: `http://localhost:8080/api/v1/emails/stats`
   - **Method**: GET
   - **Headers**:
     - `X-API-Key`: `dev-api-key-2024`
     - `Content-Type`: `application/json`
4. Clique "OK"

### **5. Adicionar Filtro de Condição**

1. Clique no "+" após HTTP Request
2. Busque por "Tools" → Selecione "Set variable"
3. Configure filtro para processar apenas quando há emails novos:
   - **Variable name**: `has_new_emails`
   - **Variable value**: `{{if(1.data.total > 0; "yes"; "no")}}`

### **6. Adicionar Ação Condicional**

1. Adicione outro HTTP Request (apenas se `has_new_emails = "yes"`)
2. Configure:
   - **URL**: `http://localhost:8080/api/v1/webhooks/make`
   - **Method**: POST  
   - **Headers**:
     - `X-API-Key`: `dev-api-key-2024`
     - `Content-Type`: `application/json`
   - **Body (JSON)**:
   ```json
   {
     "event": "make_check",
     "timestamp": "{{now}}",
     "stats": {
       "total_emails": "{{1.data.total}}",
       "unread_count": "{{1.data.unread}}",
       "processed_today": "{{1.data.processed_today}}"
     },
     "source": "make.com",
     "scenario": "email_monitor"
   }
   ```

### **7. Adicionar Notificação (Opcional)**

1. Adicione módulo "Email" ou "Slack" ou "Discord"
2. Configure notificação para quando houver atividade:
   - **Subject**: "AI Email Agent - Nova atividade"
   - **Body**: "Processados {{1.data.total}} emails. Status: ativo."

### **8. Testar Scenario**

1. Clique em "Run once" no canto superior
2. Verifique se cada módulo executa sem erros
3. Confirme que os dados fluem corretamente entre módulos
4. Verifique logs do backend para confirmar recebimento do webhook

### **9. Ativar Scenario**

1. Clique no botão "ON/OFF" para ativar
2. Scenario rodará automaticamente a cada 5 minutos
3. Monitore execuções na aba "History"

## 📊 Exemplo de Payload Recebido

Quando o Make.com enviar dados para `/api/v1/webhooks/make`, o backend receberá:

```json
{
  "event": "make_check",
  "timestamp": "2024-12-19T10:30:00Z",
  "stats": {
    "total_emails": "15",
    "unread_count": "3", 
    "processed_today": "8"
  },
  "source": "make.com",
  "scenario": "email_monitor"
}
```

## 🔧 Troubleshooting

### **Erro: Connection Refused**
- Verifique se backend está rodando na porta 8080
- Confirme se endpoint `/api/v1/webhooks/make` responde

### **Erro: 401 Unauthorized**
- Verifique se header `X-API-Key` está correto
- Confirme que API key no .env é `dev-api-key-2024`

### **Erro: 404 Not Found**
- Confirme URL completa: `http://localhost:8080/api/v1/webhooks/make`
- Verifique se router webhooks está registrado no app.py

### **Scenario não executando**
- Verifique se está ativado (botão ON)
- Confirme intervalo do timer
- Veja logs em "History" para detalhes

## 🎨 Cenários Avançados

### **Scenario 2: Email Alert System**
- Trigger: HTTP webhook do Zapier
- Ação: Enviar email/SMS quando email urgente detectado

### **Scenario 3: Data Export**
- Trigger: Timer diário  
- Ação: Exportar relatório de emails processados para Google Sheets

### **Scenario 4: Integration Chain**
- Trigger: Make.com HTTP request
- Ação: Chamar Zapier webhook (chain de automações)

## 📈 Monitoramento

### **Métricas Importantes**
- Execuções por dia
- Taxa de sucesso/erro
- Tempo médio de execução
- Dados processados

### **Logs Úteis**
- History tab no Make.com
- Backend logs: `tail -f backend/logs/app.log`
- Network tab no browser (para debug)

## 🔗 Links Úteis

- **Make.com Docs**: https://docs.make.com/
- **Templates**: https://make.com/templates
- **API Reference**: Local `http://localhost:8080/docs`
- **Support**: https://make.com/help

---

## ✅ Validação Final

Após configurar, valide que:

1. ✅ Scenario criado e ativo
2. ✅ Executa a cada 5 minutos automaticamente  
3. ✅ Backend recebe requests do Make.com
4. ✅ Logs mostram webhook calls sucessful
5. ✅ Notificações funcionando (se configuradas)

**Status**: Integração Make.com operacional! 🎨