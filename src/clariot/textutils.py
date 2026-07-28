"""Text helpers shared by the PDF parser and the client routing table."""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalize(value: str) -> str:
    """Uppercase, strip accents and collapse whitespace.

    Used for every comparison against configured labels and client names, so
    that "COMPAÑÍA", "compania" and "Compañia " all match the same entry.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE.sub(" ", without_accents).strip().upper()


def sanitize_filename(name: str, fallback: str = "archivo") -> str:
    """Make an arbitrary attachment name safe to use as a Windows filename."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    cleaned = _WHITESPACE.sub(" ", cleaned)
    return cleaned[:120] or fallback
