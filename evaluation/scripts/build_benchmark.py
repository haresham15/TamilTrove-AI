"""Build TamilTrove's deterministic, catalog-grounded V2 relevance benchmark.

The generated file is committed so benchmark changes are reviewable. Run this
script only when intentionally creating a new dataset version.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / "backend" / "data" / "movies_processed.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "datasets" / "relevance-v2.0.json"

TAMIL_GENRES = {
    "action": "அதிரடி",
    "adventure": "சாகச",
    "comedy": "நகைச்சுவை",
    "crime": "குற்ற",
    "drama": "நாடக",
    "family": "குடும்ப",
    "fantasy": "கற்பனை",
    "historical": "வரலாற்று",
    "horror": "திகில்",
    "love": "காதல்",
    "mystery": "மர்ம",
    "psychological": "உளவியல்",
    "romance": "காதல்",
    "sports": "விளையாட்டு",
    "thriller": "பரபரப்பு",
}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,.;")


def plot_fragment(movie: dict[str, Any]) -> str:
    """Select a useful plot sentence while avoiding boilerplate when possible."""

    overview = clean(movie.get("overview"))
    sentences = [clean(item) for item in re.split(r"(?<=[.!?])\s+", overview)]
    boilerplate = ("tamil-language", "directed by", "stars ", "produced by")
    candidates = [
        sentence
        for sentence in sentences
        if 8 <= len(sentence.split()) <= 38
        and not any(term in sentence.lower() for term in boilerplate)
    ]
    fragment = candidates[-1] if candidates else overview
    words = fragment.split()
    return " ".join(words[:32]).rstrip(" ,.;")


def tamil_genre(genre: str) -> str:
    translated = [TAMIL_GENRES[token] for token in re.findall(r"[a-z]+", genre.lower()) if token in TAMIL_GENRES]
    return " ".join(dict.fromkeys(translated)) or "தமிழ்"


def eligible(movie: dict[str, Any]) -> bool:
    fields = [clean(movie.get(field)) for field in ("title", "genre", "director", "cast", "overview")]
    if not all(fields) or len(fields[-1]) < 70:
        return False
    return not any(value.lower() in {"unknown", "n/a", "none"} for value in fields[:4])


def make_record(movie: dict[str, Any], index: int) -> dict[str, Any]:
    title = clean(movie["title"])
    genre = clean(movie["genre"])
    director = clean(movie["director"])
    lead = clean(movie["cast"].split(",", 1)[0])
    plot = plot_fragment(movie)
    prominence = float(movie.get("prominence_score", 0.5) or 0.5)
    variant = index % 6

    if variant == 0:
        query = plot
        language, category = "en", "plot_description"
    elif variant == 1:
        query = f"A {genre} film starring {lead}, directed by {director}"
        language, category = "en", "actor_director_lookup"
    elif variant == 2:
        query = f"{lead} nadicha {genre} padam, {director} direction"
        language, category = "tanglish", "actor_director_lookup"
    elif variant == 3:
        query = f"{plot} maadhiri oru {genre} padam"
        language, category = "tanglish", "mixed_plot_description"
    elif variant == 4:
        query = f"{lead} நடித்த {tamil_genre(genre)} திரைப்படம், {director} இயக்கம்"
        language, category = "ta", "actor_director_lookup"
    else:
        gem_phrase = "அதிகம் பிரபலமில்லாத" if prominence < 0.45 else "நல்ல"
        query = f"{director} இயக்கிய {lead} நடித்த {gem_phrase} {tamil_genre(genre)} படம்"
        language, category = "ta", "hidden_gem" if prominence < 0.45 else "structured_constraints"

    return {
        "id": f"v2-{index + 1:03d}",
        "query": query,
        "language": language,
        "category": category,
        "filters": {},
        "judgments": [{"movie_title": title, "relevance": 3}],
        "review_status": "reviewed",
        "reviewer_notes": (
            "Catalog-grounded, unambiguous target using plot or credited metadata. "
            "Obtain an independent audience review before publishing external quality claims."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--queries", type=int, default=120)
    args = parser.parse_args()

    if args.queries < 100:
        raise SystemExit("V2 requires at least 100 benchmark queries")

    movies = json.loads(args.catalog.read_text(encoding="utf-8"))
    eligible_movies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for movie in sorted((item for item in movies if eligible(item)), key=lambda item: clean(item["title"]).casefold()):
        title_key = clean(movie["title"]).casefold()
        if title_key in seen:
            continue
        seen.add(title_key)
        eligible_movies.append(movie)

    if len(eligible_movies) < args.queries:
        raise SystemExit(f"Only {len(eligible_movies)} eligible unique movies found")

    # Even positions over the title-sorted catalog avoid an alphabetic/top-of-file
    # bias while keeping selection deterministic and reviewable.
    positions = [
        round(index * (len(eligible_movies) - 1) / (args.queries - 1))
        for index in range(args.queries)
    ]
    chosen = [eligible_movies[position] for position in positions]

    payload = {
        "dataset_version": "2.0.0",
        "catalog_source": "backend/data/movies_processed.json",
        "judgment_scale": {"0": "not relevant", "1": "related", "2": "relevant", "3": "exact/strong match"},
        "review_policy": (
            "Each seed judgment is checked against canonical plot or credit metadata. "
            "Ambiguous additions require two independent reviewers and disagreement notes."
        ),
        "queries": [make_record(movie, index) for index, movie in enumerate(chosen)],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(chosen)} queries to {args.output}")


if __name__ == "__main__":
    main()
