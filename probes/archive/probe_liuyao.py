import urllib.request, json
req = urllib.request.Request(
    "http://127.0.0.1:8183/api/liuyao",
    data=json.dumps({"method":"time","year":2026,"month":8,"day":26,"hour":12,"question":"最近工作顺利吗"}).encode("utf-8"),
    headers={"Content-Type":"application/json; charset=utf-8"})
with urllib.request.urlopen(req, timeout=10) as r:
    body = json.loads(r.read().decode("utf-8"))
print("keys:", list(body.keys()))
print("ben.gua_name:", body.get("ben", {}).get("gua_name"))
print("warm.one_liner:", body.get("warm", {}).get("one_liner"))
print("warm.reply[0:3]:", (body.get("warm", {}).get("reply") or [])[:3])
print("has question field?", "question" in body)
