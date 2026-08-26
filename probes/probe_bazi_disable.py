import urllib.request, json
body = json.dumps({"year":1990,"month":5,"day":15,"hour":10,"gender":"男"}).encode("utf-8")
req = urllib.request.Request("http://127.0.0.1:8183/api/bazi", data=body,
                              headers={"Content-Type":"application/json"})
r = urllib.request.urlopen(req, timeout=10)
out = json.loads(r.read().decode("utf-8"))
print("keys:", list(out.keys()))
print("has ai_task_id?", "ai_task_id" in out)
print("ai_polish:", out.get("ai_polish"))
