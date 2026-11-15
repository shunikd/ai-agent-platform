import requests, json, pathlib, time
url='http://localhost:8000/v1/chat/completions'
payload={
    "model": "knowledge_qa",
    "messages": [{"role": "user", "content": "社内の有給休暇の取得手順は？"}]
}
resp=requests.post(url, json=payload)
print('status', resp.status_code)
print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
