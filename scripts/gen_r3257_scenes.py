"""R3257 日签场景主视觉：4 张宽幅场景图（bear-scene-*）。

判词从「圆盘贴熊头」升级成「熊活在对应天气/环境里」——
图本身承载档位信息：晴=吉、暖灯茶=小吉、灰窗=平、雨窗毯堡=凶(治愈向)。
横构图裁切 480×300 落盘（daily-level 从圆改圆角横幅）。
"""
import json, os, sys, time, urllib.request
from io import BytesIO
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEY = json.load(open('web/llm_config.json'))['fallbacks'][0]['api_key']
OUT = 'web/static/cream/'
BASE = "https://apihub.agnes-ai.com/v1/images/generations"

STYLE = ("cute chubby cream plush bear mascot, soft warm cream beige and pastel "
         "palette, children's picture book illustration, kawaii, thick soft "
         "rounded shapes, gentle cozy mood, no text, no watermark")

JOBS = {
    "bear-scene-good": f"{STYLE}, wide landscape scene: the bear stands on a sunny grassy hilltop with arms raised joyfully, big golden sun with soft rays, tiny wildflowers and butterflies, bright warm morning light",
    "bear-scene-sml":  f"{STYLE}, wide cozy scene: the bear sips warm tea sitting at a window seat with soft peach sunset light coming through, a small potted plant and steam curls, gentle contented mood",
    "bear-scene-mid":  f"{STYLE}, wide calm scene: the bear sits quietly on a windowsill looking at a mild plain sky with a few slow clouds, neutral peaceful everyday mood, soft even light",
    "bear-scene-bad":  f"{STYLE}, wide rainy scene: the bear wrapped in a fluffy pink blanket sits inside a small cushion fort by a rain-streaked window holding warm cocoa, rain drops on glass outside, cozy self-care healing mood not sad",
}


def gen(name, prompt):
    payload = json.dumps({
        "model": "agnes-image-2.1-flash", "prompt": prompt,
        "n": 1, "size": "1024x1024"}).encode()
    req = urllib.request.Request(BASE, data=payload, method="POST", headers={
        "Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.loads(r.read())
    url = body["data"][0]["url"]
    with urllib.request.urlopen(url, timeout=60) as r2:
        data = r2.read()
    from PIL import Image
    im = Image.open(BytesIO(data)).convert("RGB")
    # 居中裁 4:3 横幅再缩 480×360——主体居中构图，裁左右最稳
    w, h = im.size
    tw, th = int(w * 0.92), int(h * 0.69)
    im = im.crop(((w - tw) // 2, (h - th) // 2 - int(h * 0.06),
                  (w + tw) // 2, (h + th) // 2 - int(h * 0.06)))
    im = im.resize((480, 360), Image.LANCZOS)
    path = OUT + name + ".jpg"
    im.save(path, "JPEG", quality=84)
    print(f"OK {name} {os.path.getsize(path)//1024}KB "
          f"{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    only = sys.argv[1:] or list(JOBS)
    for n in only:
        try:
            gen(n, JOBS[n])
        except Exception as e:
            print(f"FAIL {n}: {e}", flush=True)
