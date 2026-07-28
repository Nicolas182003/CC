"""Phrase translation through Gemini, over plain HTTP.

Chosen when Google Cloud billing is not available: an AI Studio key is free and
needs no credit card. The free tier's terms allow Google to use submitted text to
improve their products, which is acceptable *only* because of what actually
travels here — a generic sentence from an Alfa Laval template, with no company,
plant, machine or serial number in it. The resolver guarantees that; see
``clariot.resolver``.

No SDK: one HTTPS call with the standard library keeps the dependency list short
and the failure modes obvious.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Mapping, Sequence

logger = logging.getLogger(__name__)

ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
# An alias, not a pinned version, on purpose. Google retires specific model names
# ("no longer available to new users"), which would silently stop translation on a
# machine nobody administers. The phrase cache already guarantees consistency:
# a model change can only affect phrases nobody has translated yet.
DEFAULT_MODEL = "gemini-flash-latest"
TIMEOUT_SECONDS = 60

PROMPT = """Traduce al español de Chile las siguientes frases de un reporte técnico \
de monitoreo de vibraciones en bombas industriales (Alfa Laval).

Reglas:
- Devuelve SOLO un array JSON de strings, en el mismo orden y con la misma \
cantidad de elementos que la entrada.
- Español técnico neutro y profesional, apto para enviar a un cliente industrial.
- No agregues explicaciones, comillas extra, numeración ni comentarios.
- Conserva la puntuación final de cada frase.
- Usa obligatoriamente esta terminología:
{terms}

Frases a traducir:
{payload}"""


class GeminiTranslationError(RuntimeError):
    """Raised when the phrases could not be translated."""


class GeminiTextTranslator:
    """Translates report phrases with Gemini. Free tier, no credit card."""
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        terms: Mapping[str, str] | None = None,
    ) -> None:
        if not api_key:
            raise GeminiTranslationError(
                "GEMINI_API_KEY is empty. Get a free key at "
                "aistudio.google.com/apikey and put it in .env."
            )
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.terms = dict(terms or {})

    def _prompt(self, texts: Sequence[str]) -> str:
        terms = (
            "\n".join(f"  - {src} = {dst}" for src, dst in self.terms.items())
            or "  (sin terminologia definida)"
        )
        payload = json.dumps(list(texts), ensure_ascii=False, indent=2)
        return PROMPT.format(terms=terms, payload=payload)

    def _post(self, body: dict) -> dict:
        request = urllib.request.Request(
            ENDPOINT.format(model=self.model),
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            if exc.code == 400 and "API_KEY_INVALID" in detail:
                raise GeminiTranslationError(
                    "La clave de Gemini es invalida. Revisa GEMINI_API_KEY en .env."
                ) from exc
            if exc.code == 404 and "no longer available" in detail:
                raise GeminiTranslationError(
                    f"El modelo '{self.model}' fue retirado por Google. Cambia "
                    "glossary.gemini_model a 'gemini-flash-latest' en settings.yaml."
                ) from exc
            if exc.code == 429:
                raise GeminiTranslationError(
                    "Se agoto la cuota gratuita de Gemini por ahora. Las frases "
                    "quedan sin traducir y se reintentan en la proxima corrida."
                ) from exc
            raise GeminiTranslationError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise GeminiTranslationError(f"Sin conexion con Gemini: {exc.reason}") from exc

    def translate(self, texts: Sequence[str]) -> list[str]:
        """Translate several phrases in one request."""
        if not texts:
            return []

        data = self._post(
            {
                "contents": [{"parts": [{"text": self._prompt(texts)}]}],
                "generationConfig": {
                    # Lowest possible variability. The cache is what really
                    # guarantees consistency, but there is no reason to invite
                    # creative rewording in the first place.
                    "temperature": 0.0,
                    "responseMimeType": "application/json",
                },
            }
        )

        try:
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            reason = data.get("promptFeedback", {}).get("blockReason", "respuesta vacia")
            raise GeminiTranslationError(f"Gemini no devolvio traduccion: {reason}") from exc

        try:
            results = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GeminiTranslationError(
                f"Gemini devolvio algo que no es JSON: {raw[:200]!r}"
            ) from exc

        if not isinstance(results, list) or len(results) != len(texts):
            raise GeminiTranslationError(
                f"Se pidieron {len(texts)} traducciones y llegaron "
                f"{len(results) if isinstance(results, list) else 'otra cosa'}"
            )
        return [str(item).strip() for item in results]

    def usage(self) -> str:
        return f"modelo {self.model}, cuota gratuita de AI Studio"
