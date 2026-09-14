import json

with open("data/movies_processed.json", encoding="utf-8") as f:
    movies = json.load(f)

targets = {"Leo", "Vikram", "Kaithi", "Master", "Jailer", "Beast", "Thunivu", "Trigger", "Blue Star", "Kaththi"}
for m in movies:
    if m.get("title") in targets or m.get("canonical_title") in targets:
        print(f"{m.get('title')} ({m.get('release_year')}): id={m.get('id') or m.get('movie_id')}, dir={m.get('director')}, music={m.get('music_director')}, prom={m.get('prominence_score')}, genres={m.get('genres')}")

