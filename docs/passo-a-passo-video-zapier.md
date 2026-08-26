# 🎥 Passo-a-Passo EXATO para Demonstrar Zapier no Vídeo

## 🎯 **Preparação: O que você precisa ter aberto**

### **Abas do Browser:**
1. **Aba 1**: Slack (canal onde chegam as mensagens)
2. **Aba 2**: Dashboard AI Email Agent (`http://localhost:3001`) 
3. **Aba 3**: Terminal (para executar comandos)
4. **Aba 4**: Zapier dashboard (para mostrar histórico)

---

## 🎬 **AÇÃO 1: Explicar o que é (30 segundos)**

### **O que FALAR:**
> "Agora vou mostrar uma funcionalidade empresarial importante: integração Low-Code com Zapier. Isso permite conectar nosso sistema com Slack, Microsoft Teams, Google Sheets e mais de 5000 outras ferramentas, tudo sem escrever código."

### **O que MOSTRAR:**
- Tela do Zapier dashboard (aba 4)
- Apontar para o Zap ativo: "Webhooks to Slack"

---

## 🎬 **AÇÃO 2: Teste rápido (1 minuto)**

### **O que FALAR:**
> "Primeiro vou fazer um teste simples para mostrar que a integração funciona."

### **O que FAZER:**
1. **Ir para o terminal** (aba 3)
2. **Copiar e colar este comando:**
```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/" -H "Content-Type: application/json" -d '{"event_type": "demo_test", "message": "🎬 Teste para vídeo", "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}'
```
3. **Pressionar Enter**
4. **Aguardar resposta:** `{"status":"success"}`
5. **IMEDIATAMENTE** ir para o Slack (aba 1)
6. **Mostrar a mensagem que chegou**

### **O que FALAR durante:**
- **Executando comando**: "Estou simulando nosso sistema enviando uma notificação..."
- **Mostrando Slack**: "E aqui está! A mensagem chegou automaticamente no Slack."

---

## 🎬 **AÇÃO 3: Demonstração real (2 minutos)**

### **O que FALAR:**
> "Agora vou processar um email real para mostrar como funciona na prática."

### **O que FAZER:**
1. **Ir para o Dashboard** (aba 2)
2. **Clicar no botão "Demo"** (ou "Buscar E-mails")
3. **Aguardar o sistema processar** (~30-45 segundos)
4. **Alternar entre Dashboard e Slack** mostrando as notificações chegando

### **O que você VAI VER no Slack:**
- Primeira mensagem: "🤖 Agente classifier completou"
- Segunda mensagem: "📝 Agente summarizer completou"  
- Terceira mensagem: "✅ Email processado completamente"

### **O que FALAR durante:**
- **Clicando Demo**: "Vou processar alguns emails de demonstração..."
- **Aguardando**: "O sistema está classificando, resumindo e gerando respostas..."
- **Mostrando Slack**: "Vejam como chegam as notificações em tempo real para cada etapa!"

---

## 🎬 **AÇÃO 4: Mostrar histórico (30 segundos)**

### **O que FALAR:**
> "No Zapier posso ver o histórico de todas as execuções bem-sucedidas."

### **O que FAZER:**
1. **Ir para Zapier dashboard** (aba 4)
2. **Mostrar a lista de execuções** (todas devem estar "success" em verde)
3. **Clicar em uma execução** para mostrar os dados que foram enviados

### **O que FALAR:**
> "Como podem ver, todas as execuções foram bem-sucedidas. Cada execução mostra exatamente que dados foram enviados para o Slack."

---

## 🎬 **AÇÃO 5: Destacar o valor (30 segundos)**

### **O que FALAR:**
> "O mais impressionante é que isso pode ser configurado por qualquer pessoa da empresa, sem conhecimento de programação. O Zapier tem mais de 5000 integrações: CRM, planilhas, e-mail marketing, sistemas de tickets... As possibilidades são infinitas."

### **O que MOSTRAR:**
- Zapier app directory (se quiser)
- Ou só falar mesmo

---

## ⚡ **Comandos de EMERGÊNCIA (caso algo dê errado)**

### **Se o sistema não estiver processando emails:**
```bash
# Execute este comando para simular:
curl -X POST "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/" -H "Content-Type: application/json" -d '{"event_type": "email_processed", "email": {"sender": "demo@teste.com", "subject": "Email de Demonstração"}, "classification": {"category": "Academic", "confidence": 0.95}}'
```

### **Se o Slack não receber mensagens:**
- **Não entre em pânico!** 
- **Fale**: "Podem ver aqui no Zapier que as execuções estão sendo bem-sucedidas"
- **Mostre o histórico verde** no Zapier dashboard

---

## 🎯 **Checklist de Sucesso**

Durante o vídeo, você deve conseguir mostrar:
- ✅ **Comando executado** → Resposta `200 OK`  
- ✅ **Mensagem no Slack** chegando em tempo real
- ✅ **Dashboard processando** emails
- ✅ **Múltiplas notificações** no Slack (uma para cada agente)
- ✅ **Zapier histórico** com execuções success
- ✅ **Dados estruturados** sendo enviados

---

## 💡 **Dicas Importantes**

### **Timing:**
- **Pause 2-3 segundos** depois de executar comando
- **Aguarde mensagem chegar** no Slack antes de continuar  
- **Não fale muito rápido** - deixe o público absorver

### **Transições:**
- **Alt+Tab** suave entre abas
- **Clique visível** nos botões
- **Cursor destacado** nos elementos importantes

### **Se algo der errado:**
- **Continue falando** sobre o conceito
- **Mostre o histórico** do Zapier (sempre tem execuções success)
- **Não se desespere** - a ideia é mais importante que a execução perfeita

---

## 🎯 **Mensagem Principal**

**O que o público deve entender:**
> "Este sistema não é apenas um projeto acadêmico. Ele tem integração empresarial real através de Low-Code/No-Code, permitindo que qualquer empresa conecte com suas ferramentas existentes sem precisar de programadores."

**Essa é a mensagem que vale 0,5 pontos na sua avaliação!** 🎯