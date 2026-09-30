"""R3256 梦符图第二批：剩余 25 张，实现 52 符号 100% 专图覆盖。

风格同 gen_r3250/gen_r3255：奶油色毛绒小熊 IP、children's book、
暖奶油底、160×160 落盘。敏感题材一律可爱化（血→创可贴、
丧尸→抱枕城堡、去世→望星已第一批）。
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
    "dream-family-scare": f"{STYLE}, the bear hugs a small family photo frame close to its chest, worried tender eyes, warm lamp glow",
    "dream-self":    f"{STYLE}, the bear floats gently like a soft translucent spirit above its sleeping self, peaceful dreamy, not scary",
    "dream-family":  f"{STYLE}, the bear sits at a warm dinner table with two older bears, home cooking, family warmth",
    "dream-naked":   f"{STYLE}, the bear wrapped only in a big fluffy towel blushes hard, hiding behind it, embarrassed cute",
    "dream-elevator":f"{STYLE}, the bear stands inside a small cute elevator pressing a button panel, door half open, puzzled",
    "dream-baby":    f"{STYLE}, the bear gently holds a tiny bundled baby plush in a soft blanket, tiny bottle nearby, tender new-life",
    "dream-blood":   f"{STYLE}, the bear looks at a small cute bandage on its paw, tiny first-aid kit open nearby, not graphic, caring",
    "dream-dog":     f"{STYLE}, the bear walks a small happy puppy on a tiny leash, park path, both cheerful",
    "dream-home":    f"{STYLE}, the bear stands before a small old countryside house with chimney smoke and a red door, nostalgic warm",
    "dream-school":  f"{STYLE}, the bear sits at a classroom desk with tiny bear classmates, chalkboard behind, nostalgic school day",
    "dream-food":    f"{STYLE}, the bear sits at a round table with a steaming hotpot and small dishes, feast mood, happy",
    "dream-mirror":  f"{STYLE}, the bear looks into a small standing oval mirror, the reflection winks back playfully, curious",
    "dream-bugs":    f"{STYLE}, the bear leans down watching a line of cute cartoon ants marching past a leaf, curious not gross",
    "dream-toilet":  f"{STYLE}, the bear with legs crossed hops toward a small door with a restroom sign, urgent funny cute",
    "dream-kiss":    f"{STYLE}, two bears touch noses blushing, tiny hearts floating, sweet innocent kiss moment",
    "dream-period":  f"{STYLE}, the bear hugs a small hot water bottle on a couch, tiny calendar with a red circle day, cozy self-care",
    "dream-idol":    f"{STYLE}, the bear waves a glowing light stick at a tiny stage with star lights, fan concert excitement",
    "dream-car":     f"{STYLE}, the bear grips the wheel of a tiny cute car with wide eyes, soft speed lines, cartoon tension not scary",
    "dream-haircut": f"{STYLE}, the bear sits in a tiny salon chair while a small bear stylist trims with scissors, hair snippets floating",
    "dream-theft":   f"{STYLE}, the bear holds an open empty little bag upside down, a coin rolls away, searching worried cute",
    "dream-fishing": f"{STYLE}, the bear sits on a grassy bank holding a small fishing rod, a tiny bucket with a fish beside, calm pond",
    "dream-alone":   f"{STYLE}, the bear sits alone on one end of a bench holding a small flower, two distant bears chatting far away, gentle lonely",
    "dream-zombie":  f"{STYLE}, the bear hides inside a sofa cushion fort holding a pillow shield, a tiny goofy plush zombie shambling outside, playful not scary",
    "dream-indream": f"{STYLE}, the bear sleeps inside a big dream bubble, and inside that bubble another tiny bear sleeps in a smaller bubble, dreamy recursion",
    "dream-looks":   f"{STYLE}, the bear pouts at a tiny pimple on its cheek in a small hand mirror, dramatic cute worry",
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
