"""补拍 9 张开运壁纸 v2——扁平贴纸绘本风（修正 v1 的 3D 毛绒跑偏）。
用法：/opt/books/venv/bin/python gen_wap_refill_v2.py [wap-30 ...]
"""
import json, os, sys, time, urllib.request
from io import BytesIO

AGNES_KEY = "sk-TV10dfgIYvTBziFZ1pga9RY6JZeYTJ74wbwHSIq2I3lUTKDh"
OUT = "/opt/books/app/web/static/wallpapers/"
BASE = "https://apihub.agnes-ai.com/v1/images/generations"

# 原版风格锚定：扁平 2D 卡通贴纸插画，大黑豆眼，哑光色块，无毛绒纹理
STYLE = ("flat 2D kawaii sticker illustration of a chubby cream-colored cartoon "
         "teddy bear mascot with big round black dot eyes, tiny smile, round "
         "ears, blush cheeks, simple matte flat colors with soft pastel "
         "palette, clean thick outlines, children's picture book style, no fur "
         "texture, not 3D, not realistic, flat simple background with gentle "
         "gradient, bear positioned in lower third, large empty space in upper "
         "half for text overlay, no text, no watermark")

JOBS = {
    "wap-30": f"{STYLE}, bear sitting on a small stone bridge at dusk holding a glowing paper lantern, snowy village background",
    "wap-31": f"{STYLE}, bear wearing a straw hat sitting on warm beach sand, tiny sail boat on pastel sea horizon, summer mood",
    "wap-32": f"{STYLE}, bear walking through falling golden autumn leaves holding a round paper lantern, warm orange evening",
    "wap-33": f"{STYLE}, bear wearing a pink knitted scarf standing in soft snow, catching a snowflake on its paw, pale winter",
    "wap-34": f"{STYLE}, bear with tiny green backpack walking a winding path through misty pastel green hills, fresh morning",
    "wap-35": f"{STYLE}, bear sleeping curled on a fluffy cloud in night sky, crescent moon and tiny stars, deep blue dreamy night",
    "wap-36": f"{STYLE}, bear in cozy scarf holding a lantern beside a little cabin with warm glowing window, snowy night",
    "wap-37": f"{STYLE}, bear sitting in a small woven hot-air balloon basket floating above pastel clouds at sunrise, hopeful mood",
    "wap-38": f"{STYLE}, bear hugging a glowing star while sitting on a smiling crescent moon, soft lavender night sky",
}


def gen(name, prompt):
    payload = json.dumps({
        "model": "agnes-image-2.5-flash", "prompt": prompt,
        "n": 1, "size": "1024x1024",
        "extra_body": {"response_format": "url"}}).encode()
    req = urllib.request.Request(BASE, data=payload, method="POST", headers={
        "Authorization": "Bearer " + AGNES_KEY, "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.loads(r.read())
    url = body["data"][0]["url"]
    with urllib.request.urlopen(url, timeout=60) as r2:
        data = r2.read()
    from PIL import Image
    im = Image.open(BytesIO(data)).convert("RGB")
    w, h = im.size
    tw = int(w * 0.5625)
    im = im.crop(((w - tw) // 2, 0, (w + tw) // 2, h))
    im = im.resize((720, 1280), Image.LANCZOS)
    path = OUT + name + ".jpg"
    im.save(path, "JPEG", quality=82)
    print(f"OK {name} {os.path.getsize(path)//1024}KB {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    only = sys.argv[1:] or list(JOBS)
    for n in only:
        try:
            gen(n, JOBS[n])
        except Exception as e:
            print(f"FAIL {n}: {e}", flush=True)
