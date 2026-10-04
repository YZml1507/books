"""R3486 守护图腾锁屏：五灵兽竖幅底图（gd-wood..gd-water）。

与 gen_wallpapers.py 同管线：Agnes 离线烘图入库，前端变体画家
（variant.beast）叠字合成。五灵兽按「绘本 Q 版」口径——和店
里奶油熊系一致，不要写实凶相。

用法：BOOKS_LLM_API_KEY=… python scripts/gen_guardian_wap.py [gd-wood …]
"""
import json, os, sys, time, urllib.request
from io import BytesIO
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEY = os.environ.get("BOOKS_LLM_API_KEY")
if not KEY and os.path.exists("web/llm_config.json"):
    KEY = json.load(open("web/llm_config.json"))["fallbacks"][0]["api_key"]
OUT = "web/static/wallpapers/"
BASE = "https://apihub.agnes-ai.com/v1/images/generations"

STYLE = ("children's picture book illustration, kawaii chubby rounded "
         "creature design, soft warm palette, thick soft shapes, gentle "
         "cozy auspicious mood, portrait vertical composition, creature "
         "centered in lower two thirds, calm textured sky/space in upper "
         "half for text overlay, no text, no watermark, no scary features")

JOBS = {
    # 木·青龙：青绿小龙盘在云间
    "gd-wood": f"{STYLE}, a chubby baby azure eastern dragon (qinglong) "
               "with tiny horns and jade-green scales, curling playfully "
               "among soft spring clouds and young leaves, fresh "
               "sprouting mint-jade palette, hopeful upward growth mood",
    # 火·朱雀：朱红小凤鸟展翅
    "gd-fire": f"{STYLE}, a chubby baby vermilion phoenix (zhuque) with "
               "round body and glowing coral-red wings, perched proudly "
               "on a branch amid warm ember sparks and sunset clouds, "
               "warm coral-amber palette, bright brave shining mood",
    # 土·麒麟：大地色小麒麟
    "gd-earth": f"{STYLE}, a chubby baby qilin with gentle deer-like "
                "body, soft earthy ochre-cream coat and tiny stub "
                "horns, standing calmly on a peaceful meadow with "
                "wheat and warm soil tones, grounded steady mood",
    # 金·白虎：银白小老虎
    "gd-metal": f"{STYLE}, a chubby baby white tiger with round face, "
                "soft silver-white fur with faint grey stripes and "
                "golden eyes, sitting neatly among clean ginkgo leaves "
                "and moonlit mist, crisp silver-gold palette, tidy "
                "sharp guardian mood",
    # 水·玄武：深蓝小龟蛇
    "gd-water": f"{STYLE}, a chubby baby black tortoise (xuanwu) with "
                "a tiny friendly snake companion curled around its "
                "shell, resting on a moonlit lakeside rock with deep "
                "indigo water and fireflies, deep indigo-teal palette, "
                "calm deep-water mood",
}


def gen(name, prompt):
    body = json.dumps({
        "model": "gpt-image-1", "prompt": prompt,
        "size": "1024x1536", "quality": "high", "n": 1,
    }).encode()
    req = urllib.request.Request(
        BASE, data=body, method="POST",
        headers={"Authorization": "Bearer " + KEY,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    item = data["data"][0]
    if item.get("b64_json"):
        import base64
        raw = base64.b64decode(item["b64_json"])
    else:
        with urllib.request.urlopen(item["url"], timeout=300) as r2:
            raw = r2.read()
    from PIL import Image
    im = Image.open(BytesIO(raw)).convert("RGB")
    im = im.resize((720, 1280), Image.LANCZOS)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".jpg")
    im.save(path, "JPEG", quality=88)
    print(name, "->", path, os.path.getsize(path) // 1024, "KB")


def main():
    todo = sys.argv[1:] or list(JOBS)
    for n in todo:
        try:
            gen(n, JOBS[n])
        except Exception as e:
            print(n, "FAIL", e)
        time.sleep(2)


if __name__ == "__main__":
    main()
