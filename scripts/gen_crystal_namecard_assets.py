#!/usr/bin/env python3
"""R81 守护水晶 / 灵魂名片：补 agnes 生图资产。

用户直报（2026-11-19 第 4 条）：「水晶，名片这些你都没有用生图模型
（agnes）画出来呀」——同排八件里，守护图腾（wallpapers/gd-*.jpg）和
灵魂角色（icons/ic-*.png + wallpapers/ic-wap-*.jpg）都是 agnes 烘的真
插画，唯独守护水晶与灵魂名片两张海报/卡面是纯渐变底+文字，视觉上
「一件有图五件没图」，用户一眼看穿。

本脚本补 10 张（两族各 5，按五行）：
- web/static/img/gem/gem-<wx>.jpg  晶石静物（4:3 横幅，接 _crCard 卡头
                                  与 crystal 海报卡图）
- web/static/img/nc/nc-<wx>.jpg    命盘印记（4:3 横幅，按日主五行，
                                  接 _ncCard 卡头与 namecard 海报卡图）

口径沿用 scripts/gen_soul_assets.py：apihub.agnes-ai.com、key 取
secrets/agnes_image.key（剥 apikey: 前缀）、模型 agnes-image-2.5-flash
（该账号已无 gpt-image-1；text image queue 不支持 background/output_format/
quality 参数，实测 400）。账号限 10 张/分钟，每次请求后 sleep 8s 兜着。

用法：
  python3 scripts/gen_crystal_namecard_assets.py gem-wood   # 单张试看
  python3 scripts/gen_crystal_namecard_assets.py            # 全部 10 张
"""
import json
import os
import sys
import time
import urllib.request
from io import BytesIO

from PIL import Image

BASE = "https://apihub.agnes-ai.com/v1/images/generations"
KEY_FILE = "secrets/agnes_image.key"
MODEL = "agnes-image-2.5-flash"
SIZE = "1024x768"          # agnes 回落 4:3（1152×864），与海报卡图区同族
OUT_GEM = "web/static/img/gem/"
OUT_NC = "web/static/img/nc/"
FINAL = (720, 540)         # 4:3，海报卡图区 416×320 / 416×270 contain 足够
GAP = 8.0                  # 账号 10 张/分钟，宁慢勿撞限流

STYLE = ("children's picture book illustration, painterly textured "
         "brushwork with visible soft strokes, soft warm cream palette, "
         "gentle cozy auspicious mood, single hero subject centered, "
         "clean composition, calm textured warm cream linen ground, "
         "generous negative space in the lower third, soft diffused "
         "window light, subtle gold accents, no text, no letters, no "
         "watermark, no frame, no border, no collage, no grid")

# ── 守护水晶：五颗晶石静物（与 app.js _CR_GEM 的五行一一对应）───────
GEM_JOBS = {
    "gem-wood": STYLE + ", a single translucent green phantom quartz "
                "crystal point with soft mossy green phantom layers "
                "inside, resting on warm cream linen beside one small "
                "sprig of young leaves, fresh sage-jade palette, "
                "quiet growing mood",
    "gem-fire": STYLE + ", a single banded coral-red agate stone polished "
                "smooth with warm orange bands, resting on warm cream "
                "linen beside a tiny amber ember spark, warm coral-amber "
                "palette, bright brave mood",
    "gem-earth": STYLE + ", a single honey-yellow citrine crystal cluster "
                 "with rounded terminations, resting on warm cream linen "
                 "beside one dry wheat stalk, rich ochre-gold palette, "
                 "grounded steady mood",
    "gem-metal": STYLE + ", a single clear white quartz crystal point with "
                 "a silvery sheen, resting on warm cream linen beside a "
                 "pale ginkgo leaf in cool moonlight, crisp silver-gold "
                 "palette, tidy sharp mood",
    "gem-water": STYLE + ", a single soft blue aquamarine crystal point "
                 "with pale translucent layers, resting on warm cream "
                 "linen beside a small ripple of water, deep blue-teal "
                 "palette, calm deep-water mood",
}

# ── 灵魂名片：五枚命盘印记（按 app.js _SM_GAN_WX 的日主五行）───────
NC_STYLE = ("children's picture book illustration, painterly textured "
            "brushwork with visible soft strokes, a single mystical "
            "bronze medallion emblem centered, softly weathered antique "
            "metal surface with fine engraved motifs, warm cream "
            "background, gentle gold rim light, cozy auspicious mood, "
            "generous negative space around the medallion, no text, no "
            "letters, no runes, no watermark, no frame, no border")

NC_JOBS = {
    "nc-wood": NC_STYLE + ", an ancient bronze mirror medallion carved "
               "with climbing vines and tree growth rings, a tiny jade "
               "green sprouting bud at its center, sage-jade palette, "
               "hopeful upward growth mood",
    "nc-fire": NC_STYLE + ", an ancient bronze medallion shaped like a "
               "sacred brazier with rising flame petals, a small crimson "
               "ember glowing at its heart, warm coral-amber palette, "
               "bright brave shining mood",
    "nc-earth": NC_STYLE + ", an ancient round clay-bronze medallion "
                "engraved with terraced fields and wheat ears, a golden "
                "grain motif at its center, rich ochre-cream palette, "
                "grounded fertile mood",
    "nc-metal": NC_STYLE + ", an ancient square bronze medallion with "
                "ginkgo leaves and a crescent moon in fine silver "
                "engraving, a crisp metal edge, cool silver-gold "
                "palette, tidy sharp guardian mood",
    "nc-water": NC_STYLE + ", an ancient bronze medallion carved with "
               "concentric water ripples and a tiny tortoise-shell "
               "pattern, a pale blue pearl at its center, deep "
               "indigo-teal palette, calm deep-water mood",
}

JOBS = {}
for k, v in GEM_JOBS.items():
    JOBS[k] = (v, OUT_GEM)
for k, v in NC_JOBS.items():
    JOBS[k] = (v, OUT_NC)


def load_key() -> str:
    text = open(KEY_FILE, encoding="utf-8").read().strip()
    return text.split(":", 1)[1].strip() if ":" in text else text


def gen(name, prompt):
    key = load_key()
    body = json.dumps({
        "model": MODEL, "prompt": prompt, "size": SIZE, "n": 1,
    }).encode()
    req = urllib.request.Request(
        BASE, data=body, method="POST",
        headers={"Authorization": "Bearer " + key,
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
    im = Image.open(BytesIO(raw)).convert("RGB")
    im = im.resize(FINAL, Image.LANCZOS)
    out_dir = JOBS[name][1]
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name + ".jpg")
    im.save(path, "JPEG", quality=86, optimize=True)
    print(name, "->", path, os.path.getsize(path) // 1024, "KB")


def main():
    todo = sys.argv[1:] or list(JOBS)
    for n in todo:
        if n not in JOBS:
            print(n, "SKIP 未知任务名；可选：", " ".join(JOBS))
            continue
        try:
            gen(n, JOBS[n][0])
        except Exception as e:
            print(n, "FAIL", repr(e)[:200])
        time.sleep(GAP)


if __name__ == "__main__":
    main()
