import re
import unicodedata

_BULLET_GLYPHS = "●▪◦‣∙■□➢➤►▶"
_BULLET_TRANS = {ord(c): "•" for c in _BULLET_GLYPHS}
_INVISIBLE = re.compile(r"[​‌‍⁠﻿­]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_text(raw: str) -> str:
    """Normalise unicode, newlines, bullets and whitespace; keep line structure."""
    text = unicodedata.normalize("NFKC", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _INVISIBLE.sub("", text)
    text = _CONTROL.sub(" ", text)
    text = text.translate(_BULLET_TRANS)
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def snippet(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
