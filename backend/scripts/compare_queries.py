import urllib.request
import json

def test_query(q):
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/search",
        data=json.dumps({"query": q, "page_size": 6, "include_debug": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    print(f"\n=======================================================")
    print(f"QUERY: '{q}'")
    print(f"Detected: {data.get('detected_language')}")
    print(f"Normalized: {data.get('normalized_query')}")
    print(f"=======================================================")
    for i, r in enumerate(data.get("results", [])):
        print(f"#{i+1}: {r['title']} ({r.get('release_year')}) - Score: {r['final_score']:.3f}")
        print(f"    Scores: Sem={r['scores']['semantic']:.3f}, Lex={r['scores']['lexical']:.3f}, Gem={r['scores']['hidden_gem']:.3f}")
        print(f"    Summary: {r.get('explanation', {}).get('summary')}")
        print(f"    Evidence: {[e['value'] for e in r.get('explanation', {}).get('evidence', [])]}")

if __name__ == "__main__":
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/search",
        data=json.dumps({"query": "courtroom-la injustice fight panra padam", "page_size": 20, "include_debug": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    for i, r in enumerate(data.get("results", [])):
        print(f"#{i+1:2d}: {r['title']:25} ({r.get('release_year')}) | Final: {r['final_score']:.3f} | Sem: {r['scores']['semantic']:.3f} | Lex: {r['scores']['lexical']:.3f}")
        print(f"     Themes: {r.get('themes')} | Evidence: {[e['value'] for e in r.get('explanation', {}).get('evidence', [])]}")
