# Roteiro de Apresentação — AI Email Agent System

## Informações do Projeto
- **Aluna:** Maria de Lourdes Celeski
- **Repositório:** https://github.com/MariaCeleski/busca-email-AI
- **Duração sugerida:** 10-15 minutos

---

## Slide 1: Título

**AI Email Agent System**
Sistema multi-agente de IA para gerenciamento inteligente de e-mails

- Classifica, resume e gera respostas automaticamente
- Human-in-the-loop: humano aprova antes de enviar
- Stack: Python, FastAPI, LangGraph, OpenAI, React

---

## Slide 2: O Problema

> "Profissionais gastam em média 2,5 horas por dia lendo e respondendo e-mails."

- Caixa de entrada lotada
- Dificuldade de priorizar o que é urgente
- Tempo gasto escrevendo respostas repetitivas
- E-mails importantes se perdem entre spam e newsletters

---

## Slide 3: A Solução

Um sistema que **automatiza a triagem** de e-mails usando 3 agentes de IA coordenados:

1. **Agente Classificador** → Categoriza (Urgente, Pessoal, Spam...) + Prioriza (Alta, Média, Baixa)
2. **Agente Sumarizador** → Resume e-mails longos em 3 frases + extrai itens de ação
3. **Agente de Resposta** → Gera rascunho imitando o tom do usuário

O humano **mantém controle total** — nada é enviado sem aprovação explícita.

---

## Slide 4: Arquitetura (Fluxo)

```
Gmail/Outlook → Monitor → Classificador → Roteamento → Sumarizador/Resposta → Dashboard → Aprovação Humana
```

- **Entrada:** E-mail bruto (remetente, assunto, corpo)
- **Processamento:** Pipeline multi-agente com LangGraph
- **Saída:** Classificação + Resumo + Rascunho de resposta
- **Decisão:** Humano aprova, edita ou rejeita

---

## Slide 5: LangGraph — Orquestração dos Agentes

O LangGraph é usado para **coordenar os agentes como um grafo de estados**:

- **Estado:** TypedDict com email, classification, summary, draft_reply
- **Nós:** classify → summarize → generate_response → publish_results
- **Routing condicional:** Decide qual agente executar baseado na classificação
- **Dual path:** E-mails urgentes longos recebem TANTO resumo quanto resposta

Isso demonstra: **planejamento, execução, uso de ferramentas e resposta final.**

---

## Slide 6: Ferramentas Integradas

| Ferramenta | Para que serve |
|-----------|---------------|
| **OpenAI GPT-4o-mini** | Classificação, sumarização, geração de respostas |
| **ChromaDB** | Busca semântica de e-mails similares (memória de longo prazo) |
| **Gmail API** | Leitura e envio de e-mails reais |
| **PostgreSQL** | Persistência de resultados processados |
| **Redis + Celery** | Processamento assíncrono em background |

---

## Slide 7: Memória e Contexto

O sistema usa **memória em múltiplos níveis:**

1. **Curto prazo:** Estado do workflow (classification flui entre nós do grafo)
2. **Longo prazo:** ChromaDB armazena embeddings de todos os e-mails processados
3. **Tone matching:** O Response Agent busca os 5 e-mails mais similares e imita o estilo de escrita

---

## Slide 8: Segurança

- Tokens OAuth criptografados com **AES-256-GCM**
- Autenticação por **API Key + JWT**
- **Circuit breaker** para degradação graciosa quando APIs externas falham
- Logs de acesso **sem conteúdo de e-mail** (privacidade)
- **Human-in-the-loop** — nenhuma resposta enviada sem aprovação

---

## Slide 9: Demonstração ao Vivo

**Passos para demonstrar:**
1. Abrir http://localhost:3000 → Login com API key
2. Dashboard mostra e-mails classificados (badges coloridos)
3. Clicar em um e-mail → ver resumo + rascunho de resposta
4. Aprovar / Editar / Rejeitar o rascunho
5. Settings → conta Gmail conectada

---

## Slide 10: Documentação com IA

O projeto documenta todo o processo de desenvolvimento com IA:

- `docs/historico-prompts.md` — 34 prompts organizados por fase
- Padrões de prompting identificados: Instrução Direta, Diagnóstico, Delegação com Contexto
- Refatorações documentadas (monorepo, migração OpenAI)
- Código comentado em português nos agentes

---

## Slide 11: Testes e CI/CD

- **511 testes** automatizados (unit + integration + property)
- Todos gerados com assistência de IA
- Pipeline CI/CD no GitHub Actions (pytest + TypeScript build)
- Versionamento GitFlow com **16 branches** demonstrando etapas

---

## Slide 12: Números do Projeto

| Métrica | Valor |
|---------|-------|
| Linhas de código | ~12.000 |
| Testes | 511 |
| Agentes de IA | 3 |
| Ferramentas integradas | 5 |
| Branches no GitHub | 16 |
| Documentos .md | 8 |
| Prompts documentados | 34 |
| Endpoints REST | 9 + WebSocket |

---

## Slide 13: Conclusão

O projeto demonstra na prática:

✅ Agente com objetivo claro (entrada/processo/saída definidos)
✅ LangGraph com estado, nós e routing condicional
✅ Integração de ferramentas (ChromaDB, Gmail, PostgreSQL, OpenAI)
✅ Memória de curto e longo prazo
✅ Segurança e validação em múltiplas camadas
✅ Documentação completa do processo com IA
✅ Versionamento GitFlow com evidência de desenvolvimento por etapas

---

## Possíveis Perguntas da Banca

**P: Por que LangGraph em vez de LangChain simples?**
R: LangGraph permite fluxo cíclico com estado, routing condicional e retry — essencial para coordenar múltiplos agentes com lógica de decisão.

**P: Como o sistema lida com falhas da IA?**
R: 3 tentativas por agente, timeout de 30s, circuit breaker que abre após 5 falhas consecutivas. Fallback: sumarizador retorna primeiras 3 frases.

**P: Os e-mails ficam seguros?**
R: Tokens criptografados AES-256, logs sem conteúdo, deleção completa em 24h ao desconectar, human-in-the-loop obrigatório.

**P: Qual o custo de operação?**
R: GPT-4o-mini: ~$0.15 por 1000 e-mails classificados. Infraestrutura local via Docker (custo zero).

**P: Como foi o processo de desenvolvimento com IA?**
R: 34 ciclos de prompting documentados em historico-prompts.md. Padrões: Instrução Direta, Diagnóstico, Delegação com Contexto, Continuação Implícita.

---

## Checklist Pré-Apresentação

- [ ] Docker rodando (`docker compose up -d`)
- [ ] Backend rodando (`cd backend && .venv/bin/python -m uvicorn ...`)
- [ ] Frontend rodando (`cd frontend && npm run dev`)
- [ ] Celery worker rodando (para busca real de e-mails)
- [ ] Dashboard com e-mails classificados visíveis
- [ ] GitHub aberto mostrando branches e commits

---

*Material preparado em Julho 2026*
