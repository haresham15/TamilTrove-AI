import urllib.request
import json

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/search",
    data=json.dumps({
        "query": "courtroom-la injustice fight panra padam",
        "page_size": 50,
        "include_debug": True
    }).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))

print(f"Detected language: {data.get('detected_language')}")
print(f"Normalized query: {data.get('normalized_query')}")
print(f"Query plot: {data.get('query_plot')}")

print("\nSearch for key films in top 50:")
for i, r in enumerate(data.get("results", [])):
    t = r["title"].lower()
    if any(k in t for k in ["jai bhim", "nerkonda", "verdict", "pavithra", "thummbad", "padam"]):
        print(f"Rank #{i+1}: {r['title']} ({r.get('release_year')}) - Final: {r.get('final_score'):.3f}")
        print(f"    Semantic: {r['scores']['semantic']:.3f}, Lexical: {r['scores']['lexical']:.3f}, Hidden Gem: {r['scores']['hidden_gem']:.3f}")
        print(f"    Evidence: {r.get('explanation', {}).get('evidence')}")
