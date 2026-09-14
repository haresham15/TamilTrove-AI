import sys, os
sys.path.insert(0, os.path.abspath("."))
from app.catalog import Catalog
from app.config import Settings
from app.ranking import SearchIndex
import numpy as np

settings = Settings()
catalog = Catalog.load(settings.data_path, settings.embeddings_path)
index = SearchIndex(catalog, settings)

query = "courtroom-la injustice fight panra padam"

print(f"--- QUERY: {query} ---")
hits, meta = index.search(query, page_size=20, include_debug=True)

for i, h in enumerate(hits[:10]):
    m = h.movie
    print(f"#{i+1}: {m.title} ({m.release_year})")
    print(f"   Final: {h.final:.3f} | Sem: {h.semantic:.3f} | Lex: {h.lexical:.3f} | Gem: {h.hidden_gem:.3f}")
    print(f"   Themes: {m.themes} | Genre: {m.genre}")
    print(f"   Why: {h.explanation.summary}")
    print(f"   Evidence: {[e.value for e in h.explanation.evidence]}")

# Also check Jai Bhim specifically
jb = next((h for h in hits if "jai bhim" in h.movie.title.lower()), None)
if jb:
    print(f"\nJai Bhim rank in hits: #{hits.index(jb)+1}")
    print(f"   Final: {jb.final:.3f} | Sem: {jb.semantic:.3f} | Lex: {jb.lexical:.3f} | Gem: {jb.hidden_gem:.3f}")
    print(f"   Overview: {jb.movie.overview}")
