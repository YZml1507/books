#!/usr/bin/env python3
"""wap-39：替换下架的 wap-37。原主题热气球没画出来，换「山坡看日出」，
与 wap-37 同样的 hopeful rising mood 但构图可靠（不依赖模型画热气球气球囊）。
"""
import json, os, sys, time, urllib.request
from io import BytesIO

AGNES_KEY = "sk-TV10dfgIYvTBziFZ1pga9RY6JZeYTJ74wbwHSIq2I3lUTKDh"
OUT = "/opt/books/app/web/static/wallpapers/"
BASE = "https://apihub.agnes-ai.com/v1/images/generations"

STYLE = ("flat 2D kawaii sticker illustration of a chubby cream-colored cartoon "
         "teddy bear mascot with big round black dot eyes, tiny smile, round "
         "ears, blush cheeks, simple matte flat colors with soft pastel "
         "palette, clean thick outlines, children's picture book style, no fur "
         "texture, not 3D, not realistic, flat simple background with gentle "
         "gradient, large empty space in upper half for text overlay, no text, "
         "no watermark")

PROMPT = (f"{STYLE}, vertical portrait composition, the bear sitting cross-"
          "legged on a rounded pastel hilltop in lower third, seen from behind "
          "at three-quarter angle, watching a soft peach-and-lavender sunrise "
          "with a small smiling sun peeking over the horizon, two tiny birds "
          "in the sky, hopeful new-day mood")


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
    gen("wap-39", PROMPT)
