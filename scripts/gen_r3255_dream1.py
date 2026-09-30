"""R3255 梦符图第一批：15 张高情绪密度/噩梦向符号（含鬼压床）。

风格口径与 gen_r3250_assets.py 一致：奶油色毛绒小熊 IP、
children's book 插画、暖奶油底色、居中构图、160×160 落盘。
"""
import json, os, sys, time, urllib.request
from io import BytesIO
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEY = json.load(open('web/llm_config.json'))['fallbacks'][0]['api_key']
OUT = 'web/static/cream/'
BASE = "https://apihub.agnes-ai.com/v1/images/generations"

STYLE = ("cute chubby cream plush bear mascot, soft warm cream beige and pastel "
         "palette, children's picture book illustration, kawaii, thick soft "
         "rounded shapes, centered composition, plain warm cream background "
         "#FBF3E8, gentle cozy mood, no text, no watermark")

JOBS = {
    # 噩梦/情绪向优先——可爱化不吓人
    "dream-ghost":   f"{STYLE}, the bear hugs a big pillow tight looking at a tiny cute round white ghost, the ghost is smiling friendly, night lamp glow, scared-but-cute",
    "dream-frozen":  f"{STYLE}, the bear lies in bed under a soft blanket with a tiny cute round shadow creature sitting gently on the blanket, sleepy night mood, not scary",
    "dream-gone":    f"{STYLE}, the bear looks up at one big warm glowing star in a soft night sky, holding a small flower, tender remembrance, gentle tears of love",
    "dream-cry":     f"{STYLE}, the bear cries big cartoon tears into a tiny handkerchief, a small heart bandage nearby, soft and comforting not tragic",
    "dream-hair":    f"{STYLE}, the bear holds a tiny comb looking at a few loose fluff hairs floating, puzzled cute, mirror nearby",
    "dream-breakup": f"{STYLE}, the bear sits by a rainy window holding a small paper crane, one side of a bench empty, wistful but gentle",
    "dream-fight":   f"{STYLE}, two plush bears facing away with puffed cheeks, a small storm cloud between them, cartoon quarrel, cute not mean",
    "dream-cheat":   f"{STYLE}, the bear holds a tiny cracked paper heart, looking at two distant small bear silhouettes, soft rain, sad-cute",
    "dream-late":    f"{STYLE}, the bear runs with a tiny clock under its arm toward a departing cute train, motion lines, hurry",
    "dream-trapped": f"{STYLE}, the bear peeks out from a small room with a round window, pushing a big cute door, looking for the way out, curious not scared",
    "dream-work":    f"{STYLE}, the bear in a tiny necktie holds a stack of papers, a bigger grumpy cat boss silhouette pointing, office stress cute",
    "dream-phone":   f"{STYLE}, the bear pats empty pockets looking for a tiny phone, the phone peeks from under a pillow, worried cute",
    "dream-ghosted": f"{STYLE}, the bear stares at a tiny phone with a speech bubble left unread, small greyed check mark bubble, waiting",
    "dream-money":   f"{STYLE}, the bear picks up a shiny gold coin from the ground, small coins scattered sparkling, lucky find",
    "dream-fire":    f"{STYLE}, the bear holds a tiny water bucket looking at a small cute orange flame, brave firefighter mood, not scary",
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
    # 落盘即压：160×160 JPEG——与同族 dream-*.jpg 规格一致
    from PIL import Image
    im = Image.open(BytesIO(data)).convert("RGB").resize(
        (160, 160), Image.LANCZOS)
    path = OUT + name + ".jpg"
    im.save(path, "JPEG", quality=82)
    print(f"OK {name} {os.path.getsize(path)//1024}KB "
          f"{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    only = sys.argv[1:] or list(JOBS)
    for n in only:
        try:
            gen(n, JOBS[n])
        except Exception as e:
            print(f"FAIL {n}: {e}", flush=True)
