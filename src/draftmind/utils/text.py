"""Utilidades de texto."""

import re

_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t]+")


def strip_html(text: str) -> str:
    """Quita las etiquetas de las descripciones de Data Dragon.

    Data Dragon usa etiquetas propias (<stats>, <passive>, <lol-uikit-...>)
    que Qt no entiende; los saltos de línea se conservan.
    """
    text = _BREAK.sub("\n", text or "")
    text = _TAG.sub("", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
