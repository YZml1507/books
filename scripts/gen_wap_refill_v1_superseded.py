"""补拍 9 张开运壁纸（替换 2026-11-19 下架的 wap-10/11/12/13/14/15/19/20/21）。
沿用 gen_wallpapers.py 的 STYLE 模板与 9:16 裁切管线，新编号 wap-30..38
（旧 10..21 已下架，_WAP_COUNT 仍按 24 轮换——新图进池见 app.js 改动）。
用法：python3 gen_wap_refill.py
"""
import json, os, sys, time, urllib.request
from io import BytesIO

sys.path.insert(0, "/opt/books/app/scripts")
KEY_PATH = "/opt/books/app/web/llm_config.json"
AGNES_KEY = "sk-TV10dfgIYvTBziFZ1pga9RY6JZeYTJ74wbwHSIq2I3lUTKDh"
OUT = "/opt/books/app/web/static/wallpapers/"
BASE = "https://apihub.agnes-ai.com/v1/images/generations"

STYLE = ("cute chubby cream plush bear mascot, soft warm cream beige and pastel "
         "palette, children's picture book illustration, kawaii, thick soft "
         "rounded shapes, gentle cozy mood, portrait vertical composition, "
         "empty calm space in upper half for text overlay, no text, no watermark")

JOBS = {
    # 对应下架的 wap-10 冬夜石桥提灯
    "wap-30": f"{STYLE}, stone bridge at soft winter dusk, the cream bear sitting on the bridge lower third holding a tiny glowing lantern, gentle snowy pastel mood",
    # 对应 wap-11 海边草帽
    "wap-31": f"{STYLE}, pastel seaside morning, the cream bear wearing a tiny straw hat sitting on warm sand lower third gazing at soft waves, breezy summer mood",
    # 对应 wap-12 秋夜灯笼
    "wap-32": f"{STYLE}, golden autumn evening, falling ginkgo leaves, the cream bear walking lower third holding a small round paper lantern, warm harvest glow mood",
    # 对应 wap-13 雪地围巾
    "wap-33": f"{STYLE}, quiet snowy field with soft bare trees, the cream bear in a pastel pink scarf lower third catching a snowflake, gentle winter mood",
    # 对应 wap-14 山间小路
    "wap-34": f"{STYLE}, misty pastel green mountain path with soft light, the cream bear with a tiny backpack walking lower third, fresh quiet adventure mood",
    # 对应 wap-15 云上月夜
    "wap-35": f"{STYLE}, dreamy night sky with soft clouds and crescent moon, the cream bear sleeping on a fluffy cloud lower third, serene starlight mood",
    # 对应 wap-19 雪夜暖灯
    "wap-36": f"{STYLE}, snowy night with warm little cabin window glow, the cream bear in cozy scarf lower third holding a tiny lantern, cozy winter-night mood",
    # 对应 wap-20 日出热气球/云海
    "wap-37": f"{STYLE}, sunrise above a sea of soft clouds, the cream bear sitting in a small woven basket lower third watching golden light, hopeful rising mood",
    # 对应 wap-21 月牙云朵
    "wap-38": f"{STYLE}, pale moonlit night, the cream bear sitting on a smiling crescent moon lower third hugging a tiny star, sweet dreamy mood",
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
    os.makedirs(OUT, exist_ok=True)
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
