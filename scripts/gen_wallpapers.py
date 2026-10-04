"""R3317 每日开运壁纸：10 张竖幅底图（wap-00..09）。

设计（全网调研结论）：开运壁纸是小红书真付费需求（~29元/张），
我们的产品形态=每天一张「底图+幸运色判词+日签」可一键保存晒图。
底图生图不走运行时（慢且要 key），离线烘 10 张入库按日轮换；
前端 canvas 叠字合成成品（复用海报机管线）。

用法：BOOKS_LLM_API_KEY=… python scripts/gen_wallpapers.py [wap-00 wap-03 …]
"""
import json, os, sys, time, urllib.request
from io import BytesIO
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEY = os.environ.get("BOOKS_LLM_API_KEY")
if not KEY and os.path.exists("web/llm_config.json"):
    KEY = json.load(open("web/llm_config.json"))["fallbacks"][0]["api_key"]
OUT = "web/static/wallpapers/"
BASE = "https://apihub.agnes-ai.com/v1/images/generations"

STYLE = ("cute chubby cream plush bear mascot, soft warm cream beige and pastel "
         "palette, children's picture book illustration, kawaii, thick soft "
         "rounded shapes, gentle cozy mood, portrait vertical composition, "
         "empty calm space in upper half for text overlay, no text, no watermark")

JOBS = {
    "wap-00": f"{STYLE}, sunrise over soft golden meadow, the bear small in lower third stretching arms toward morning light, hopeful new-day mood",
    "wap-01": f"{STYLE}, pastel pink blossom garden, petals drifting, the bear sitting on a wooden bench lower third holding a tiny flower, gentle lucky mood",
    "wap-02": f"{STYLE}, starry indigo night sky with constellations, the bear on a hilltop lower third holding a small glowing lantern, dreamy wishes mood",
    "wap-03": f"{STYLE}, cozy warm tea window scene, afternoon peach light, the bear on windowsill lower third with steaming cup, contented hygge mood",
    "wap-04": f"{STYLE}, soft mint green forest path with light dapples, the bear walking along lower third with tiny backpack, fresh adventure mood",
    "wap-05": f"{STYLE}, lavender dusk seaside, pastel waves, the bear sitting on a smooth rock lower third watching horizon, calm reflective mood",
    "wap-06": f"{STYLE}, golden hour autumn ginkgo leaves falling, the bear under a big ginkgo tree lower third catching a leaf, warm harvest mood",
    "wap-07": f"{STYLE}, soft rainy day window bokeh, warm interior glow, the bear wrapped in pink blanket lower third with cocoa, healing self-care mood",
    "wap-08": f"{STYLE}, moonlit snowy night, gentle falling snowflakes, the bear in a cozy scarf lower third making a tiny snowman friend, serene winter mood",
    "wap-09": f"{STYLE}, pastel rainbow after rain over rolling hills, the bear jumping joyfully lower third with arms up, bright lucky-celebration mood",
}

# R3362 主题系列：节日/节气限定底图——前端按当日 j.festival /
# j.term.name 对表选用，非节点日仍走 10 张日轮换。命名 wap-t-*。
THEME_JOBS = {
    "wap-t-halloween": f"{STYLE}, halloween night, soft jack-o-lanterns glowing warm orange, tiny candy corn scattered, the bear in a little wizard hat lower third holding a mini pumpkin, playful not spooky, deep purple dusk sky",
    "wap-t-xmas": f"{STYLE}, cozy christmas eve, small decorated pine tree with warm fairy lights, wrapped gifts in pastel paper, gentle snow outside window, the bear in a tiny red scarf lower third holding a gift box, warm festive mood",
    "wap-t-nye": f"{STYLE}, new year eve celebration, soft golden fireworks and sparkles over night sky, pastel confetti falling, the bear lower third holding a small sparkler looking up at sky, hopeful countdown mood",
    "wap-t-cny": f"{STYLE}, chinese new year, soft red lanterns glowing, golden paper cut decorations, warm festive crimson and gold palette, the bear in a tiny red outfit lower third holding a mini lantern, joyful spring festival mood",
    "wap-t-valentine": f"{STYLE}, valentine day, soft pink hearts and roses floating, warm blush pink palette, the bear lower third holding a tiny heart-shaped balloon, sweet romantic mood",
    "wap-t-frost": f"{STYLE}, late autumn frost morning, golden orange maple leaves with white frost edges, misty soft light, the bear lower third in a cozy coat touching a frosted leaf, crisp harvest-end mood",
    "wap-t-winterstart": f"{STYLE}, early winter day, first cold wind, bare branches with last golden leaves, pale warm sunlight, the bear lower third wrapping a soft scarf around itself, cozy seasonal-turn mood",
    "wap-t-snow": f"{STYLE}, gentle snowfall day, big soft snowflakes drifting, white and pale blue world, the bear lower third catching snowflakes on its paw with delighted face, pure first-snow joy",
    "wap-t-solstice": f"{STYLE}, winter solstice longest night, deep blue starry evening, warm glowing window with steaming dumplings on table, the bear lower third holding a warm bowl, family-warmth mood",
    "wap-t-deepcold": f"{STYLE}, deepest winter cold, frosted window with icy flower patterns, warm candlelight indoors, the bear lower third in fluffy earmuffs sipping hot cocoa, snug against-the-cold mood",
    "wap-t-spring": f"{STYLE}, early spring awakening, first pale green buds and plum blossoms on branches, soft morning light and gentle drizzle, the bear lower third holding a tiny sprouting leaf, new-beginning hopeful mood",
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
    w, h = im.size
    # 中心裁 9:16 竖幅（底部留主体，上部留叠字净空）
    tw = int(w * 0.5625)
    im = im.crop(((w - tw) // 2, 0, (w + tw) // 2, h))
    im = im.resize((720, 1280), Image.LANCZOS)
    os.makedirs(OUT, exist_ok=True)
    path = OUT + name + ".jpg"
    im.save(path, "JPEG", quality=82)
    print(f"OK {name} {os.path.getsize(path)//1024}KB "
          f"{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    if not KEY:
        sys.exit("BOOKS_LLM_API_KEY 未注入且无 web/llm_config.json")
    only = sys.argv[1:] or list(JOBS)
    for n in only:
        try:
            src = JOBS.get(n) or THEME_JOBS[n]
            gen(n, src)
        except Exception as e:
            print(f"FAIL {n}: {e}", flush=True)
