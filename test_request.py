import requests, json
url='http://localhost:8001/search'
payload={"query":"社内規定の有給休暇の申請方法について","top_k":5}
resp=requests.post(url,json=payload)
print(resp.status_code)
print(json.dumps(resp.json(),ensure_ascii=False,indent=2))
