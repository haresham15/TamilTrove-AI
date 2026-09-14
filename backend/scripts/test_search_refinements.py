import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog import Catalog
from app.config import Settings
from app.normalization import normalize_query
from app.ranking import SearchIndex
from app.schemas import SearchRequest

def inspect():
    settings = Settings(environment="test", enable_transformer=True)
    catalog = Catalog.load(settings.data_path, settings.embeddings_path)
    index = SearchIndex(catalog, settings)

    q = "movies like LEO"
    norm_q = normalize_query(q)
    results, _, _ = index.rank(norm_q, SearchRequest(query=q, page_size=30, diversity=0.0))
    for i, r in enumerate(results[:25], 1):
        print(f"{i:2d}. {r.movie.title} ({r.movie.release_year}) | Dir: {r.movie.director} | Music: {r.movie.music_director} | Final: {r.final:.4f} | Lex: {r.lexical:.4f} | Sem: {r.semantic:.4f}")

    print("\n--- Kaithi position ---")
    for i, r in enumerate(results, 1):
        if r.movie.title.lower() == "kaithi":
            print(f"Kaithi is at rank {i}: Final={r.final:.4f}, Lex={r.lexical:.4f}, Sem={r.semantic:.4f}, Ev={[e['value'] for e in r.evidence]}")

if __name__ == "__main__":
    inspect()
