"""Normalization utilities used before comparison.

The philosophy (spec Section 11):
- Normalize whitespace, unicode, common OCR artifacts, and units.
- Do NOT do aggressive fuzzy matching. Uncertainty must surface as flags,
  never as a silent match.

All functions here are pure — no I/O, no boto3. Easy to unit-test.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional


# ---- Unicode / whitespace --------------------------------------------------

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def unicode_normalize(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def is_devanagari(s: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in s)


# ---- Names -----------------------------------------------------------------

# Very small, safe Devanagari → Latin map for common land-record proper nouns.
# We deliberately do not include a full transliteration table here — the
# indic-transliteration library handles anything more nuanced. This map is
# a fallback used when the library isn't available (e.g., during unit tests).
_DEV_TO_LATIN_HINTS = {
    "राम": "ram",
    "प्रसाद": "prasad",
    "सीता": "sita",
    "देवी": "devi",
    "कुमार": "kumar",
    "सिंह": "singh",
    "शर्मा": "sharma",
    "यादव": "yadav",
    "पटेल": "patel",
    "गुप्ता": "gupta",
    "वर्मा": "verma",
    "उत्तर": "uttar",
    "प्रदेश": "pradesh",
    "रामपुर": "rampur",
    "मध्य": "madhya",
    "बिहार": "bihar",
    "राजस्थान": "rajasthan",
    "महाराष्ट्र": "maharashtra",
}


def _hint_translit(dev: str) -> str:
    """Best-effort Devanagari → Latin using a small hint map + naive fallback.

    Used only when the optional `indic-transliteration` package is unavailable.
    """
    words = dev.split()
    out = []
    for w in words:
        out.append(_DEV_TO_LATIN_HINTS.get(w, w))
    return " ".join(out)


def _transliterate(dev: str) -> str:
    """Convert a Devanagari string to a normalized Latin form."""
    try:  # pragma: no cover - depends on optional dependency at runtime
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate

        latin = transliterate(dev, sanscript.DEVANAGARI, sanscript.ITRANS)
        # ITRANS keeps diacritics like 'A' meaning long 'a'. Downcase and
        # strip non-alphanumerics so equality with an English record works.
        return re.sub(r"[^a-z0-9\s]", "", latin.lower())
    except Exception:
        return _hint_translit(dev).lower()


def normalize_name(name: Optional[str]) -> str:
    """Return a canonical, comparable form of a person or place name.

    - unicode normalize
    - transliterate Devanagari to Latin
    - lowercase, strip punctuation
    - collapse whitespace
    """
    if not name:
        return ""
    s = unicode_normalize(name)
    if is_devanagari(s):
        s = _transliterate(s)
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = normalize_whitespace(s)
    return s


def normalize_place(place: Optional[str]) -> str:
    """Same normalization as names — places use the same casing/transliteration."""
    return normalize_name(place)


# ---- Identifiers (Khasra, Khata, plot) -------------------------------------

_ID_ALLOWED = re.compile(r"[^0-9A-Za-z/\-]")


def normalize_id(value: Optional[str]) -> str:
    """Normalize a numeric identifier such as Khasra / Khata / plot number.

    - map Devanagari digits to ASCII
    - upper-case any letter suffix (e.g., '12a' → '12A')
    - unify '-' as '/' when used as a compound separator
    - strip whitespace
    """
    if not value:
        return ""
    s = str(value).translate(DEVANAGARI_DIGITS)
    s = _ID_ALLOWED.sub("", s)
    s = s.replace("-", "/")
    # Collapse multiple slashes
    s = re.sub(r"/+", "/", s).strip("/")
    # Upper-case any trailing letters ("12a" → "12A")
    s = re.sub(r"([0-9])([a-zA-Z])", lambda m: m.group(1) + m.group(2).upper(), s)
    return s


# ---- Area ------------------------------------------------------------------

# Conversion factors to square metres. Bigha and katha are state-dependent
# and must be resolved with the record's `state` field.
BASE_UNIT_M2 = {
    "square meter": 1.0,
    "square metre": 1.0,
    "sq meter": 1.0,
    "sqm": 1.0,
    "m2": 1.0,
    "m²": 1.0,
    "hectare": 10000.0,
    "ha": 10000.0,
    "acre": 4046.8564224,
    "gunta": 101.171,
    "guntha": 101.171,
    "cent": 40.4686,
    "square foot": 0.092903,
    "sqft": 0.092903,
    "ft2": 0.092903,
    "square yard": 0.836127,
    "sqyd": 0.836127,
}

BIGHA_M2_BY_STATE = {
    "uttar pradesh": 2508.38,
    "bihar": 2508.38,
    "madhya pradesh": 2529.28,
    "rajasthan": 2530.00,
    "haryana": 2529.28,
    "punjab": 2529.28,
    "himachal pradesh": 2529.28,
    "uttarakhand": 2529.28,
    "assam": 1333.33,
    "west bengal": 1338.61,
}
BIGHA_DEFAULT_M2 = 2529.0  # generic value if state is unknown

KATHA_M2_BY_STATE = {
    "bihar": 125.0,
    "west bengal": 66.9,
    "assam": 66.9,
    "jharkhand": 125.0,
}
KATHA_DEFAULT_M2 = 125.0


def _canonical_unit(unit: str) -> str:
    return re.sub(r"[^a-z0-9]", " ", unit.lower()).strip()


def area_to_m2(
    value: float,
    unit: Optional[str],
    state: Optional[str] = None,
) -> Optional[float]:
    """Convert an (area, unit) pair to square metres.

    Returns None if the unit is unknown. That is a signal to the caller
    to emit UNIT_INCONSISTENCY, not a silent failure.
    """
    if value is None or unit is None:
        return None
    u = _canonical_unit(unit)
    if u in BASE_UNIT_M2:
        return float(value) * BASE_UNIT_M2[u]
    if u.startswith("bigha"):
        state_key = (state or "").lower()
        return float(value) * BIGHA_M2_BY_STATE.get(state_key, BIGHA_DEFAULT_M2)
    if u.startswith("katha") or u.startswith("kattha"):
        state_key = (state or "").lower()
        return float(value) * KATHA_M2_BY_STATE.get(state_key, KATHA_DEFAULT_M2)
    return None


def area_plausible(m2: Optional[float]) -> bool:
    """Sanity range for individual parcels: 1 m² .. 10000 hectare."""
    if m2 is None:
        return False
    return 1.0 <= m2 <= 100_000_000.0


# ---- Dates -----------------------------------------------------------------

_DATE_PATTERNS = [
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"), "ymd"),
    (re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$"), "dmy"),
    (re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2})$"), "dmy2"),
]


def normalize_date(s: Optional[str]) -> Optional[str]:
    """Parse Indian-style dates (DD/MM/YYYY primary) into ISO YYYY-MM-DD.

    Returns None if the date is unparseable — caller decides how to flag.
    """
    if not s:
        return None
    text = normalize_whitespace(str(s)).translate(DEVANAGARI_DIGITS)
    for pat, mode in _DATE_PATTERNS:
        m = pat.match(text)
        if not m:
            continue
        if mode == "ymd":
            y, mo, d = m.group(1), m.group(2), m.group(3)
        elif mode == "dmy":
            d, mo, y = m.group(1), m.group(2), m.group(3)
        else:  # dmy2 — assume 20th century for yy >= 30, 21st for yy < 30
            d, mo, yy = m.group(1), m.group(2), m.group(3)
            yy_int = int(yy)
            y = str(1900 + yy_int if yy_int >= 30 else 2000 + yy_int)
        try:
            mo_i, d_i = int(mo), int(d)
            if not (1 <= mo_i <= 12 and 1 <= d_i <= 31):
                return None
            return f"{int(y):04d}-{mo_i:02d}-{d_i:02d}"
        except ValueError:
            return None
    return None
