from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")
LATIN_RE = re.compile(r"[A-Za-z]")
TOKEN_RE = re.compile(r"[^\w\u0B80-\u0BFF]+", re.UNICODE)

# Conservative cinema-domain vocabulary. Proper names are deliberately absent.
TAMIL_TERMS: dict[str, str] = {
    "காதல்": "love romance",
    "குடும்பம்": "family",
    "கிராமம்": "village rural",
    "கிராமத்து": "village rural",
    "நகைச்சுவை": "comedy",
    "திகில்": "horror thriller",
    "பேய்": "ghost horror",
    "அரசியல்": "political politics",
    "நீதிமன்ற": "courtroom court",
    "நீதிமன்றம்": "courtroom court",
    "நீதி": "justice",
    "அநீதி": "injustice justice",
    "பழிவாங்கும்": "revenge",
    "பழிவாங்க": "revenge",
    "காவல்துறை": "police",
    "காவலர்": "police officer",
    "குற்றம்": "crime",
    "நட்பு": "friendship friends",
    "சிறை": "prison prisoner",
    "கைதி": "prisoner",
    "துரத்தல்": "chase",
    "உணர்ச்சிகரமான": "emotional",
    "ஒரே": "one",
    "இரவு": "night",
    "திரைப்படம்": "movie film",
    "படம்": "movie film",
}

TANGLISH_TERMS: dict[str, str] = {
    "kadhal": "love romance",
    "kaadhal": "love romance",
    "loveu": "love romance",
    "kudumbam": "family",
    "familyah": "family",
    "gramam": "village rural",
    "graamam": "village rural",
    "ooru": "village rural",
    "village-la": "village",
    "sirippu": "comedy",
    "comedy-ah": "comedy",
    "bayam": "horror fear",
    "pei": "ghost horror",
    "peyi": "ghost horror",
    "arasiyal": "political politics",
    "needhimandram": "courtroom court",
    "neethi": "justice",
    "pazhivangum": "revenge",
    "policeu": "police",
    "kuttram": "crime",
    "natpu": "friendship friends",
    "nanban": "friend friendship",
    "kaithi": "prisoner prison",
    "thurathal": "chase",
    "iravu": "night",
    "sentiment": "emotional",
    "massu": "action mainstream",
    "padam": "movie film",
    "padamum": "movie film",
    "kadhai": "story plot",
    "kathai": "story plot",
    "maari": "like similar",
    "mathiri": "like similar",
    "pola": "like similar",
    "la": "",
}

GENRE_ALIASES: dict[str, str] = {
    "romcom": "romance comedy",
    "rom-com": "romance comedy",
    "scifi": "science fiction",
    "sci-fi": "science fiction",
    "thrilling": "thriller",
    "funny": "comedy",
    "scary": "horror",
    "actioner": "action",
    "whodunnit": "mystery crime",
}

TANGLISH_MARKERS = frozenset(TANGLISH_TERMS) | {
    "enna",
    "oru",
    "venum",
    "irukra",
    "irukkura",
    "nalla",
    "semma",
}


@dataclass(frozen=True, slots=True)
class NormalizedQuery:
    original: str
    normalized: str
    detected_language: str
    expanded_terms: tuple[str, ...]


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\u200b", " ").replace("\ufeff", " ")
    value = TOKEN_RE.sub(" ", value.casefold())
    return " ".join(value.split())


def detect_language(value: str) -> str:
    has_tamil = bool(TAMIL_RE.search(value))
    has_latin = bool(LATIN_RE.search(value))
    if has_tamil and has_latin:
        return "mixed"
    if has_tamil:
        return "tamil"
    normalized = normalize_text(value)
    tokens = set(normalized.split())
    marker_count = len(tokens & TANGLISH_MARKERS)
    if marker_count >= 1:
        return "tanglish"
    return "english"


def normalize_query(value: str) -> NormalizedQuery:
    original = unicodedata.normalize("NFKC", value or "").strip()
    language = detect_language(original)
    normalized = normalize_text(original)
    expanded: list[str] = []

    for token in normalized.split():
        mapped = TAMIL_TERMS.get(token) or TANGLISH_TERMS.get(token) or GENRE_ALIASES.get(token)
        if mapped:
            expanded.extend(mapped.split())

    # Phrase-level additions retain the original normalized text for proper names.
    lowered = normalized
    if "one night" in lowered or ("ஒரே" in lowered and "இரவு" in lowered):
        expanded.extend(("one", "night", "single-night"))
    if "hidden gem" in lowered or "underrated" in lowered or "மறைக்கப்பட்ட" in lowered:
        expanded.extend(("hidden", "gem", "underrated", "obscure"))

    unique_expanded = tuple(dict.fromkeys(term for term in expanded if term))
    augmented = " ".join(part for part in (normalized, " ".join(unique_expanded)) if part).strip()
    return NormalizedQuery(
        original=original,
        normalized=augmented,
        detected_language=language,
        expanded_terms=unique_expanded,
    )


def parse_query_hints(normalized_query: str) -> dict[str, object]:
    """Extract only unambiguous constraints; explicit API filters win later."""
    hints: dict[str, object] = {}
    text = normalized_query.casefold()
    decade = re.search(r"\b((?:19|20)\d)0s\b", text)
    if decade:
        start = int(decade.group(1) + "0")
        hints["year_min"] = start
        hints["year_max"] = start + 9
    after = re.search(r"\b(?:after|since)\s+((?:19|20)\d{2})\b", text)
    before = re.search(r"\b(?:before|until)\s+((?:19|20)\d{2})\b", text)
    if after:
        hints["year_min"] = int(after.group(1))
    if before:
        hints["year_max"] = int(before.group(1))
    genres = [
        genre
        for genre in (
            "action",
            "adventure",
            "comedy",
            "crime",
            "drama",
            "family",
            "fantasy",
            "history",
            "horror",
            "mystery",
            "political",
            "romance",
            "thriller",
        )
        if re.search(rf"\b{re.escape(genre)}\b", text)
    ]
    if genres:
        hints["genres"] = genres
    return hints
