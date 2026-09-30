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
    # R3252 签面小插画（打卡翻面后的卡面——与 CHECKIN_LABEL 同语义）
    "sign-egg":       f"{STYLE}, the bear is happily hatching out of a big cream egg shell, small sparkles, lucky egg",
    "sign-melon":     f"{STYLE}, the bear is eating a big slice of red watermelon, juice drop, relaxed snack time",
    "sign-fish":      f"{STYLE}, the bear is lazily napping hugging a small blue fish pillow, tiny 'z z' mood, cozy break",
    "sign-wave":      f"{STYLE}, the bear waves a tiny wand blowing away a small grey rain cloud, rainbow peeking, turn luck around",
    "sign-rich":      f"{STYLE}, the bear holds a big red envelope and a shiny gold coin, small coins sparkling, lucky money",
    "sign-candy":     f"{STYLE}, the bear hugs a big swirl lollipop candy, tiny sweets around, sweet day",
    "sign-ashore":    f"{STYLE}, the bear proudly climbs onto a grassy shore holding a graduation flag, success landing",
    "sign-lucky":     f"{STYLE}, the bear slides down a small soft rainbow holding a four-leaf clover, smooth green light",
    "sign-birthday":  f"{STYLE}, the bear wears a party crown and holds a small birthday cake with one candle, confetti",
    # 合婚结果顶部插画——双熊同框
    "hehun-bear":     f"{STYLE}, two cute plush bears holding hands side by side, small heart above them, sweet couple, warm pink accents",
    # R3253 梦境符号缩略图（解梦卡的象征头像，可爱化不吓人）
    "dream-teeth":    f"{STYLE}, the bear holds up a tiny white tooth looking surprised, small sparkles, dream mood",
    "dream-chase":    f"{STYLE}, the bear runs playfully looking back at a small puff cloud chasing it, cartoon motion lines, not scary",
    "dream-fall":     f"{STYLE}, the bear gently floats down holding a big green leaf like a parachute, soft clouds around",
    "dream-fly":      f"{STYLE}, the bear flies happily with two tiny wings over soft cream clouds, stars, dreamy",
    "dream-exam":     f"{STYLE}, the bear sits at a small desk writing a test paper with a pencil, tiny sweat drop, cute anxious",
    "dream-ex":       f"{STYLE}, the bear holds a small old photo letter with a soft nostalgic smile, tiny heart, bittersweet cute",
    "dream-crush":    f"{STYLE}, the bear with small heart eyes holds a folded love note and a tiny flower, shy blushing",
    "dream-snake":    f"{STYLE}, the bear curiously looks at a tiny cute friendly snake, both smiling, not scary",
    "dream-water":    f"{STYLE}, the bear sits in a tiny paper boat on soft pastel blue waves, small raindrops, calm dreamy",
    "dream-lost":     f"{STYLE}, the bear holds a small map looking puzzled at a cute wooden signpost with two arrows, forest path",
    "dream-wedding":  f"{STYLE}, the bear wears a tiny white veil and holds a small flower bouquet, wedding bell sparkle, sweet",
    "dream-cat":      f"{STYLE}, the bear cuddles a small cream kitten in its arms, both content, cozy",
    "dream-bear":     f"{STYLE}, the bear sleeps peacefully curled on a big soft crescent moon among tiny stars, dreamy night, generic dream icon",
    # R3253 黄历「我打算」场景小图
    "scene-move":     f"{STYLE}, the bear carries a small cardboard moving box, tiny house behind, moving day",
    "scene-open":     f"{STYLE}, the bear cuts a red ribbon in front of a tiny cute shop, small flags, grand opening",
    "scene-date":     f"{STYLE}, the bear holds a small bouquet of flowers wearing a tiny bow, sweet date, hearts",
    "scene-interview":f"{STYLE}, the bear in a tiny necktie holds a small resume paper, sitting straight, interview",
    "scene-travel":   f"{STYLE}, the bear pulls a tiny rolling suitcase holding a folded map, small plane in sky, travel",
    "scene-sign":     f"{STYLE}, the bear stamps a small red seal on a document with a fountain pen, contract signing",
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
