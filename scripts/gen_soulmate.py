"""R3373 正缘画像：6 张气质型底图（sm-metal/wood/water/fire/earth/peach）。

设计（全网调研结论）：「灵魂伴侣/正缘画像」是 2025 验证过的最大
AI 玄学爆款机制（Starla 日下载峰值 11 万）。我们的形态=生日排盘
→日主五行定气质型→氛围感底图+特征标签+相遇信号，一键海报晒图。
不写实脸（肖像风险），写光影氛围+剪影意象——「样子是想象，
信号是真的」口径。

底图与壁纸同管线离线烘入库，前端 canvas 叠字。命名 sm-*。
用法：BOOKS_LLM_API_KEY=… python scripts/gen_soulmate.py [sm-metal …]
"""
import json, os, sys, time, urllib.request
from io import BytesIO

KEY = os.environ.get("BOOKS_LLM_API_KEY")
if not KEY and os.path.exists("web/llm_config.json"):
    KEY = json.load(open("web/llm_config.json"))["fallbacks"][0]["api_key"]
OUT = "web/static/soulmate/"
BASE = "https://apihub.agnes-ai.com/v1/images/generations"

# 与壁纸同一奶熊治愈系（品牌一致），但画面主题换成「相遇氛围」——
# 熊只作氛围点缀（小比例、远景或剪影），留上半叠字净空。
STYLE = ("cute chubby cream plush bear mascot small in scene, soft warm cream "
         "beige and pastel palette, children's picture book illustration, "
         "kawaii, thick soft rounded shapes, gentle romantic mood, portrait "
         "vertical composition, dreamy bokeh atmosphere, empty calm space in "
         "upper half for text overlay, no text, no watermark, no realistic "
         "human face")

JOBS = {
    # 金日主→清冷白月光型：月色银辉、干净克制
    "sm-metal": f"{STYLE}, cool moonlit night, pale silver moonlight on a quiet street, two paper cranes floating mid-air, a distant figure silhouette under ginkgo tree, serene pristine first-love mood, silver and pale blue palette",
    # 木日主→青竹少年感型：林间新绿、清爽朝气
    "sm-wood": f"{STYLE}, fresh bamboo grove after rain, dappled green light, a distant figure in light shirt walking on forest path with bicycle, youthful refreshing first-sight mood, mint and jade palette",
    # 水日主→深海温柔型：靛蓝海面、沉静包容
    "sm-water": f"{STYLE}, deep indigo seaside at blue hour, gentle waves with glowing jellyfish light, a distant figure standing on pier looking at sea, deep calm devoted mood, navy and soft teal palette",
    # 火日主→暖阳元气型：琥珀晨光、明朗热烈
    "sm-fire": f"{STYLE}, warm amber sunrise over open field, golden light rays through soft clouds, a distant figure running with a kite, bright warm passionate mood, apricot and coral palette",
    # 土日主→大地安稳型：麦田暖棕、踏实可靠
    "sm-earth": f"{STYLE}, golden wheat field at late afternoon, warm earthy brown and honey tones, a distant figure carrying small basket on country path, dependable grounded homey mood",
    # 命中咸池/红鸾→桃花浪漫型：花瓣月下、心动信号
    "sm-peach": f"{STYLE}, dreamy pink blossom rain at dusk, petals drifting in soft lantern light, two distant figures almost meeting under a blossom arch, fated romantic encounter mood, blush pink and warm gold palette",
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
            gen(n, JOBS[n])
        except Exception as e:
            print(f"FAIL {n}: {e}", flush=True)
