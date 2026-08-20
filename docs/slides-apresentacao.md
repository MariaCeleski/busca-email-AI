# Slides — AI Email Agent
## Apresentação do Mini-Projeto (2 slides)

> Copie o conteúdo de cada slide para PowerPoint, Google Slides ou Canva.

---

# SLIDE 1 — O Problema e a Proposta

## AI Email Agent — Sistema Multi-Agente de Gestão de E-mails

**Problema:**
Profissionais perdem horas diárias classificando, lendo e respondendo e-mails repetitivos.

**Proposta do Agente:**
Um sistema com 3 agentes de IA orquestrados por LangGraph que automatiza:

| Etapa | Agente | Entrada → Saída |
|-------|--------|-----------------|
| 1. Classificar | ClassifierAgent | E-mail → Categoria + Prioridade + Confiança |
| 2. Resumir | SummarizerAgent | E-mail longo → Resumo (3 frases) + Ações |
| 3. Responder | ResponseAgent | E-mail + Contexto → Rascunho de resposta |

**Ferramentas integradas:** OpenAI API, Gmail API, ChromaDB, PostgreSQL, Celery/Redis

**Diferencial:** Revisão humana (aprovar/editar/rejeitar) + Aprendizado por feedback

---

# SLIDE 2 — Fluxo LangGraph e Tecnologias

## Fluxo do Agente (StateGraph)

```
E-mail recebido
      │
      ▼
┌─────────────┐
│  CLASSIFICAR │ → Categoria, Prioridade, Confiança
└──────┬──────┘
       │ routing condicional
       ├─────────────────────────┐
       ▼                         ▼
┌─────────────┐          ┌─────────────┐
│   RESUMIR   │          │  RESPONDER  │
│ (se > 200   │          │ (se Urgente │
│  palavras)  │          │ ou Pessoal) │
└──────┬──────┘          └──────┬──────┘
       │                        │
       └────────┬───────────────┘
                ▼
      ┌─────────────────┐
      │ REVISÃO HUMANA  │ → Aprovar / Editar / Rejeitar
      └─────────────────┘
                │
                ▼
      ┌─────────────────┐
      │   FEEDBACK →    │ → Few-shot dinâmico (melhora futuras classificações)
      └─────────────────┘
```

**Stack:** Python · FastAPI · LangGraph · OpenAI GPT-4o-mini · React · PostgreSQL · Docker

**Números:** 511 testes | 17 branches | 3 agentes | 5 ferramentas | CI/CD GitHub Actions

**Repositório:** github.com/MariaCeleski/busca-email-AI

---

## Dicas para montar os slides visuais:

**Slide 1:**
- Fundo escuro (azul marinho #1a1a2e)
- Título grande em branco
- Tabela com as 3 etapas
- Ícones: 📧 📋 ✉️

**Slide 2:**
- Diagrama de fluxo visual (use SmartArt ou formas)
- Stack em badges coloridos na parte inferior
- QR Code ou link do repositório no canto
