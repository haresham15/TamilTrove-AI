import json

with open("data/movies_processed.json", encoding="utf-8") as f:
    movies = json.load(f)

targets = ['Jai Bhim', 'Nerkonda Paarvai', 'Thummbad', 'Pavithra 1994', 'The Verdict', 'Tamizh Padam 2.0', 'English Padam']
for t in targets:
    found = [m for m in movies if m['title'].lower() == t.lower()]
    if found:
        m = found[0]
        print(f"=== {m['title']} ===")
        print("Director:", m.get("director"))
        print("Cast:", m.get("cast"))
        print("Genre:", m.get("genre"))
        print("Overview:", m.get("overview"))
        print()
