# 🎬 Comandos Prontos para Vídeo - Zapier Demo

## 📋 **Comandos para Copiar e Colar Durante a Gravação**

### **1. Teste Rápido de Conectividade**
```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/" \
  -H "Content-Type: application/json" \
  -d '{"event_type": "demo_test", "message": "🎬 Teste de conectividade para vídeo", "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}'
```

### **2. Email Acadêmico Processado (Para o vídeo)**
```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "email_processed",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "email": {
      "sender": "professor@faculdade.edu.br",
      "subject": "🎓 Avaliação Final - Projeto AI Email Agent",
      "provider": "gmail"
    },
    "classification": {
      "category": "Academic", 
      "priority": "High",
      "confidence": 0.96
    },
    "summary": {
      "summary": "Professor solicita apresentação do projeto final com sistema de IA"
    },
    "draft_reply": {
      "subject": "Re: Projeto pronto para apresentação",
      "body": "Prezado Professor, nosso sistema está funcionando perfeitamente..."
    },
    "system": {"model_used": "gpt-4o-mini", "environment": "production"}
  }'
```

### **3. Agente Completou Classificação**
```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "agent_completed",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "agent_name": "classifier",
    "email_id": "demo_video_001", 
    "classification": {
      "category": "Urgent",
      "priority": "High", 
      "confidence": 0.95
    },
    "system": {"model_used": "gpt-4o-mini", "processing_time": 1.2}
  }'
```

### **4. Email Empresarial Crítico**
```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "email_processed",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "email": {
      "sender": "cliente.vip@empresa.com",
      "subject": "🚨 CRÍTICO: Sistema Indisponível",
      "provider": "outlook"
    },
    "classification": {
      "category": "Urgent",
      "priority": "Critical",
      "confidence": 0.99
    },
    "summary": {
      "summary": "Cliente VIP reporta sistema crítico fora do ar",
      "impact": "500+ usuários afetados"
    },
    "draft_reply": {
      "subject": "URGENTE - Equipe mobilizada",
      "body": "Equipe técnica foi acionada imediatamente..."
    },
    "system": {"escalation_triggered": true}
  }'
```

---

## 🎯 **Sequência Recomendada para o Vídeo**

### **Momento 1: Explicar + Testar Conectividade**
- Falar sobre integração Low-Code
- Executar **Comando 1** (teste rápido)
- Mostrar notificação chegando no Slack

### **Momento 2: Demonstração Real** 
- No Dashboard: clicar "Buscar E-mails" ou "Demo"
- Aguardar pipeline processar
- Mostrar notificações automáticas no Slack

### **Momento 3: Cenários Adicionais**
- Executar **Comando 2** (email acadêmico)
- Executar **Comando 3** (agente completado)  
- Executar **Comando 4** (email crítico)
- Mostrar Zapier History com execuções

---

## 📱 **Mensagens Esperadas no Slack**

### **Teste de Conectividade**
```
🎬 Demo Test Received
Message: 🎬 Teste de conectividade para vídeo
Time: 2024-08-19 21:45:30
```

### **Email Processado**
```
📧 Email Processed Complete
From: professor@faculdade.edu.br
Subject: 🎓 Avaliação Final - Projeto AI Email Agent
Category: Academic (96% confidence)  
Summary: Professor solicita apresentação do projeto final...
```

### **Agente Completado**
```
🤖 AI Agent Completed
Agent: classifier
Result: Urgent/High (95% confidence)
Processing Time: 1.2s
```

---

## ✅ **Checklist Pré-Gravação**

- [ ] **Slack aberto** no canal correto
- [ ] **Terminal pronto** com comandos copiados
- [ ] **Dashboard** funcionando em localhost:3001
- [ ] **Zapier Dashboard** aberto (para mostrar history)
- [ ] **Teste rápido** executado com sucesso
- [ ] **Ambiente silencioso** (sem outras notificações)

---

## 🕐 **Timing Sugerido**

- **Comando 1**: Execute → aguarde 2s → mostre Slack
- **Pipeline real**: Clique botão → aguarde 30s → mostre notificações
- **Comando 2-4**: Execute cada um → aguarde 2s entre eles
- **Zapier History**: Mostre ao final (15s)
- **Total**: ~4-5 minutos de demonstração prática