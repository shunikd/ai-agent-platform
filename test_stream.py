import requests, json
url = "http://localhost:8000/v1/chat/completions"
payload = {
    "model": "knowledge_qa",
    "messages": [{"role": "user", "content": "社内の有給休暇取得手順は？"}],
    "stream": True,
}
resp = requests.post(url, json=payload, stream=True)
for line in resp.iter_lines():
    if line:
        decoded = line.decode('utf-8')
        if decoded.startswith('data:'):
            try:
                data = json.loads(decoded[5:].strip())
                print('Chunk:', data)
            except Exception:
                print('Raw:', decoded)
