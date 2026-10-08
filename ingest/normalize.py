"""Unicode/whitespace canonicalization shared by ingest and verifier.

Chunk text is stored canonicalized (case preserved); quote matching in
verify/verifier.py applies the same folding plus casefold, so quotes with
curly quotes, em-dashes or odd spacing still verify.
"""

import re
import unicodedata

_PUNCT_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
    }
)
_WS = re.compile(r"\s+")


def canonicalize(s: str, fold_case: bool = False) -> str:
    """NFKC + punctuation fold + whitespace collapse (+ optional casefold)."""
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_PUNCT_MAP)
    s = _WS.sub(" ", s).strip()
    return s.casefold() if fold_case else s
