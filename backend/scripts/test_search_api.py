import urllib.request
import json

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/v1/search',
    data=json.dumps({'query': 'courtroom-la injustice fight panra padam'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
res = urllib.request.urlopen(req)
data = json.loads(res.read())
print('Total matches:', data.get('total_matches'))
for i, m in enumerate(data['results'][:8]):
    title = m.get('title')
    year = m.get('release_year')
    score = m.get('scores', {}).get('final', 0)
    summary = m.get('explanation', {}).get('summary', '')
    evidence = [e.get('value') for e in m.get('explanation', {}).get('evidence', [])]
    print(f"{i+1}. {title} ({year}) | Score: {score:.3f} | {summary} | Evidence: {evidence}")
