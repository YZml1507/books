"""R3250 批次：判词心情熊 + 五行人格拟人 + renge 图标生图。

风格口径：奶油色毛绒小熊（对齐 daily-gift-bear.png 的既有 IP），
children's book 插画、暖奶油底色、居中构图。
"""
import json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEY = json.load(open('web/llm_config.json'))['fallbacks'][0]['api_key']
OUT = 'web/static/cream/'
BASE = "https://apihub.agnes-ai.com/v1/images/generations"

STYLE = ("cute chubby cream plush bear mascot, soft warm cream beige and pastel "
         "palette, children's picture book illustration, kawaii, thick soft "
         "rounded shapes, centered composition, plain warm cream background "
         "#FBF3E8, gentle cozy mood, no text, no watermark")

JOBS = {
    # 判词心情熊（替换日签判词圆盘的文字）
    "bear-day-good":  f"{STYLE}, the bear is joyfully holding a small golden sun, tiny flowers and sparkles around, arms up happy, bright cheerful",
    "bear-day-sml":   f"{STYLE}, the bear is smiling softly hugging a small warm cup of tea, tiny heart floating, content cozy",
    "bear-day-mid":   f"{STYLE}, the bear is sitting calmly with relaxed expression, small cloud and leaf, peaceful neutral",
    "bear-day-bad":   f"{STYLE}, the bear is wrapped in a soft pink blanket holding a tiny umbrella, small gentle rain cloud above, cozy self-care not sad, healing",
    # 五行人格拟人（bear-in-element 系列）
    "persona-wood":   f"{STYLE}, the bear wears a crown of green leaves and hugs a small potted tree sapling, fresh green accents, growing",
    "persona-fire":   f"{STYLE}, the bear holds a tiny glowing warm sun sparkler, soft orange coral glow, energetic warm",
    "persona-earth":  f"{STYLE}, the bear sits on a small round grassy hill holding a piece of bread, warm tan terracotta accents, grounded",
    "persona-metal":  f"{STYLE}, the bear proudly holds up a small shiny golden star gem, soft gold sparkle accents, refined bright",
    "persona-water":  f"{STYLE}, the bear rides a cute round blue water droplet wave, soft misty blue accents, flowing gentle",
    # renge 功能卡图标（与 cream-icon-* 系列同构图：单个主体居中图标感）
    "icon-renge":     "cute minimal flat icon, a small smiling five-petal flower with five soft pastel petals (pink orange yellow mint blue), warm cream background #FBF3E8, centered, children's book style, no text, square icon composition",
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
    path = OUT + name + ".jpg"
    with open(path, "wb") as f:
        f.write(data)
    print(f"OK {name} {len(data)//1024}KB {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    only = sys.argv[1:] or list(JOBS)
    for n in only:
        try:
            gen(n, JOBS[n])
        except Exception as e:
            print(f"FAIL {n}: {e}", flush=True)
