import urllib.request
import json
req = urllib.request.Request(
    "http://127.0.0.1:8183/api/bazi",
    data=json.dumps({"year":1990,"month":5,"day":15,"hour":12,"gender":"女","scope":"day"}).encode("utf-8"),
    headers={"Content-Type":"application/json; charset=utf-8"})
with urllib.request.urlopen(req, timeout=10) as r:
    body = json.loads(r.read().decode("utf-8"))
print("keys:", list(body.keys()))
print("paipan:", body.get("paipan"))
print("calc.day_luck:", body.get("calc", {}).get("day_luck"))
print("warm.one_liner:", body.get("warm", {}).get("one_liner"))
print("warm.first line:", (body.get("warm", {}).get("reply") or [""])[0][:80])
