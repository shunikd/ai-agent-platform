import requests, json
url='http://localhost:8000/v1/chat/completions'
payload={
    "model":"code_reviewer",
    "messages":[{"role":"user","content":"Write a hello world function in python."}],
    "stream":False
}
resp=requests.post(url,json=payload)
print('status', resp.status_code)
print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
