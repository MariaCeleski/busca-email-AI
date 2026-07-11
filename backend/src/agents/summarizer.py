# =============================================================================
# Agente Sumarizador — gera resumos de e-mails usando o LLM Google Gemini.
#
# Objetivo: Receber um e-mail longo (> 200 palavras) e produzir um resumo
# conciso de no máximo 3 frases, além de extrair até 10 itens de ação.
#
# Entrada: RawEmail (remetente, assunto, corpo)
# Saída: SummaryResult (summary, action_items, is_fallback, no_content)
#
# Regras:
# - Se o corpo estiver vazio → retorna no_content=True sem chamar o LLM
# - Se o corpo tiver < 200 palavras → retorna o corpo original sem modificação
# - Se o corpo tiver >= 200 palavras → chama o LLM para resumir
# - Timeout: 8 segundos. Se exceder ou LLM falhar → usa fallback (primeiras 3 frases)
# =============================================================================
"""Agente Sumarizador — gera resumos de e-mails usando Google Gemini LLM."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import List, Optional

import google.generativeai as genai

from src.config import get_settings
from src.models.email import RawEmail
from src.models.summary import SummaryResult

logger = logging.getLogger(__name__)


class SummarizerAgent:
    """Sumariza e-mails e extrai itens de ação usando Google Gemini LLM."""

    # Limiar de palavras: e-mails com menos de 200 palavras não são sumarizados
    WORD_THRESHOLD = 200

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 8,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.gemini_api_key
        self._model_name = model or settings.gemini_model
        self._timeout = timeout

        # Configura o SDK do Gemini
        genai.configure(api_key=self._api_key)
        self._model = genai.GenerativeModel(self._model_name)

    # Método principal: gera resumo dentro do timeout de 8s.
    # Retorna fallback (primeiras 3 frases) em caso de falha do LLM ou timeout.
    async def summarize(self, email: RawEmail) -> SummaryResult:
        """Generate summary within 8s timeout.

        Returns fallback summary on LLM failure/timeout.
        """
        # Sem texto extraível → retorna indicação de conteúdo vazio
        if not email.body.strip():
            return SummaryResult(summary="", no_content=True)

        # Corpo abaixo do limiar → retorna corpo original sem modificação
        if not self.should_summarize(email):
            return SummaryResult(summary=email.body, action_items=[])

        prompt = self.build_summary_prompt(email)

        try:
            raw_output = await asyncio.wait_for(
                self._call_gemini(prompt),
                timeout=self._timeout,
            )
            return self._parse_summary(raw_output)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Sumarização falhou, usando fallback: %s", exc)
            return self.fallback_summary(email)

    # Verifica se o corpo do e-mail excede o limiar de 200 palavras.
    def should_summarize(self, email: RawEmail) -> bool:
        """Check if email body exceeds 200-word threshold."""
        return self._count_words(email.body) >= self.WORD_THRESHOLD

    # Constrói o prompt de sumarização e extração de itens de ação (em português).
    def build_summary_prompt(self, email: RawEmail) -> str:
        """Construct prompt for summarization and action item extraction."""
        return f"""Você é um assistente de sumarização de e-mails. Resuma o e-mail a seguir.

Regras:
- O resumo deve ter no máximo 3 frases
- Extraia até 10 itens de ação (coisas que o destinatário precisa fazer)
- Se não houver itens de ação, retorne uma lista vazia
- Preserve detalhes críticos incluindo datas, valores e nomes mencionados

Retorne APENAS um JSON válido com os seguintes campos:
- "summary": string (máximo 3 frases)
- "action_items": lista de strings (máximo 10 itens)

Detalhes do e-mail:
- De: {email.sender}
- Assunto: {email.subject}
- Corpo: {email.body[:3000]}

Responda APENAS com o objeto JSON, sem texto ou formatação adicional."""

    # Fallback: retorna as primeiras 3 frases quando o LLM falha.
    def fallback_summary(self, email: RawEmail) -> SummaryResult:
        """Return first 3 sentences as fallback when LLM fails."""
        summary = self._extract_first_sentences(email.body, n=3)
        return SummaryResult(
            summary=summary,
            action_items=[],
            is_fallback=True,
        )

    # Conta o número de palavras no texto.
    def _count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())

    # Extrai as primeiras N frases do texto.
    def _extract_first_sentences(self, text: str, n: int = 3) -> str:
        """Extract first n sentences from text."""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        selected = sentences[:n]
        return " ".join(selected)

    # Parseia a saída do LLM em um SummaryResult.
    def _parse_summary(self, raw_output: str) -> SummaryResult:
        """Parse LLM output into SummaryResult."""
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        data = json.loads(cleaned)

        summary = str(data.get("summary", ""))
        action_items: List[str] = [
            str(item) for item in data.get("action_items", [])
        ]
        # Limita itens de ação a 10
        action_items = action_items[:10]

        return SummaryResult(
            summary=summary,
            action_items=action_items,
        )

    # Chama a API do Gemini e retorna a resposta em texto bruto.
    async def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API and return raw text response."""
        response = await self._model.generate_content_async(prompt)

        if response.text is None:
            raise RuntimeError("Gemini returned empty response")

        return response.text
