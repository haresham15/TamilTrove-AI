import sys, os
sys.path.insert(0, os.path.abspath("."))
from app.catalog import Catalog
from app.config import Settings
from app.normalization import normalize_query

settings = Settings()
catalog = Catalog.load(settings.data_path, settings.embeddings_path)

print("Testing theme tagging after refinement:")
courtroom_rule = ("court", "courtroom", "lawyer", "advocate", "trial", "judge", "hearing", "prosecutor", "verdict", "legal drama", "legal case")

print("All courtroom movies under refined rule:")
courtroom_movies = []
for m in catalog.movies:
    full_text = f"{m.title} {m.genre} {m.overview}".lower()
    if any(k in full_text for k in courtroom_rule):
        courtroom_movies.append(m)

print(f"Total found: {len(courtroom_movies)}")
for m in courtroom_movies:
    print(f" - {m.title} ({m.release_year}) | Genre: {m.genre} | Director: {m.director}")
