import urllib.request
import json

def query_api(query: str):
    print(f"\n=======================================================")
    print(f"QUERY: '{query}'")
    print(f"=======================================================")
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/search",
        data=json.dumps({"query": query, "page_size": 6}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    
    seed = data.get("seed_movie")
    if seed:
        print(f"Detected Seed Movie: {seed.get('title')} ({seed.get('release_year')}) [ID: {seed.get('id')}]")
    
    for i, r in enumerate(data.get("results", [])):
        score = r.get("final_score", 0.0)
        expl = r.get("explanation", {}).get("summary", "")
        ev = [f"{e['type']}:{e['value']}" for e in r.get("explanation", {}).get("evidence", [])]
        print(f"#{i+1}: {r['title']} ({r['release_year']}) - Score: {score:.3f}")
        print(f"    Director: {r.get('director')}, Cast: {r.get('cast', [])[:3]}")
        print(f"    Summary: {expl}")
        print(f"    Evidence: {', '.join(ev[:4])}")

if __name__ == "__main__":
    query_api("movies like LEO")
    query_api("action thriller with big star, high budget and anirduh music")
