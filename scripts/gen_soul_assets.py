#!/usr/bin/env python3
"""R80 灵魂角色资产重出：洛神卡头 + 麒麟卡头 + 5 张灵魂角色场景壁纸。

用户实测（本轮四条）：
1.「那个『麒麟』的『做我的锁屏』那么好看，但是那个 logo 的麒麟怎么
   看上去呆呆的」——wallpapers/gd-earth.jpg 是暖光麦田里的整幅插画
   （3/4 侧脸、亮眼、笑口、毛皮有纹理、有轮廓光），而 icons/gd-earth.png
   是同一只灵兽的平涂抠图版：正面呆站、表情平、无纹理无光。差距不在
   画功在「有没有按插画口径画」。
2.「那个洛神怎么是个很丑的东西……他的『做我的壁纸』也是很难看」——
   ic-water.png 是一只青绿色团子生物，而同族四张（女娲/祝融/后土/刑天）
   全是「Q 版汉服神君」人形。洛神（洛水之神，《洛神赋》「翩若惊鸿
   婉若游龙」）本该是水边女神，团子既不好看也不对题。
3. 灵魂角色壁纸此前由 app_wallpaper.js 的 _wapSoulIcon 在前端拿透明底
   角色图铺暖渐变合成——没有环境没有氛围，所以「很难看」。

本脚本重出 7 张：
- gd-earth.png   麒麟卡头（369×512 RGBA）：按壁纸同款画风重画，白底+本地抠透明
- ic-water.png   洛神卡头（486×512 RGBA）：改成 Q 版水边女神，与同族四张同语言
- ic-wap-*.jpg   5 张灵魂角色场景壁纸（720×1280）：整幅插画，上部角色、
                 下部压暗给文字留可读区，接进 _wapSoulIcon 当底图

口径沿用 scripts/gen_icon_cutouts.py：apihub.agnes-ai.com、key 取
secrets/agnes_image.key（剥 apikey: 前缀）、模型 agnes-image-2.5-flash
（该账号已无 gpt-image-1；text image queue 不支持 background/output_format/
quality 参数，实测 400）。卡头仍走「纯白底出图 + 四边连通域抠底」两步。

用量：7 张。账号限 10 张/分钟，脚本每次请求后 sleep 8s 兜着。

用法：
  python3 scripts/gen_soul_assets.py gd-earth     # 单张试看
  python3 scripts/gen_soul_assets.py              # 全部
"""
import base64
import io
import json
import os
import sys
import time
import urllib.request
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

BASE = "https://apihub.agnes-ai.com/v1/images/generations"
OUT_ICON = "web/static/icons/"
OUT_WAP = "web/static/wallpapers/"
MODEL = "agnes-image-2.5-flash"
SIZE = "1024x1536"
WAP_SIZE = (720, 1280)          # 9:16 竖幅，与 _wapSoulIcon 画布同尺寸
SIZES = {"gd": (369, 512), "ic": (486, 512)}
GAP = 8.0                        # 账号 10 张/分钟，宁慢勿撞限流

# ── 卡头（白底出图 + 抠透明）──────────────────────────────────────────
HERO_STYLE = ("children's picture book illustration, painterly textured "
              "brushwork with visible soft strokes, kawaii chubby rounded "
              "character design, gentle warm palette, gentle cozy "
              "auspicious mood, single subject centered, full body, clean "
              "silhouette, plain flat pure white background, solid color, "
              "no gradient, no vignette, no texture on background, no "
              "ground shadow, no text, no watermark, no frame, no border")

HERO_JOBS = {
    # 麒麟：与 wallpapers/gd-earth.jpg 同一只灵兽、同一套画风画——3/4 侧脸
    # 转向观者、亮眼带高光、笑口、毛皮带鳞纹、暖轮廓光、迈步的动态，
    # 不再是「正面呆站表情平」的贴纸版。
    "gd-earth": HERO_STYLE + ", a chubby baby qilin with gentle deer-like "
                "body, soft earthy ochre-cream coat with subtle scale "
                "patterns, two tiny stub horns, big bright expressive eyes "
                "with clear highlights and warm reflected light, joyful "
                "open smile, head turned three-quarter toward the viewer, "
                "lively playful mid-step pose, warm golden rim light along "
                "the coat and horn tips, fresh wheat-field palette",
    # 洛神：从「青绿团子生物」改成 Q 版水边女神——长流发、飘逸宽袖罗裙、
    # 飘带、水珠涟漪、珍珠高光，与女娲/后土同一套人形神君语言。
    "ic-water": HERO_STYLE + ", a graceful young water goddess Luoshen of "
                "the Luo River, elegant chibi figure with long flowing "
                "indigo-dark hair and a delicate jade hairpin, flowing "
                "translucent teal-blue silk robes with wide drifting "
                "sleeves and long ribbons floating in the air, one hand "
                "lightly raised in a serene gesture, gentle knowing smile, "
                "big bright eyes with soft highlights, small water "
                "droplets and ripple motifs around her, deep blue-teal "
                "palette with pearl-white highlights, ethereal flowing mood",
}

# ── 灵魂角色场景壁纸（整幅插画，不抠底）──────────────────────────────
WAP_STYLE = ("children's picture book illustration, painterly textured "
             "brushwork, rich atmospheric environment, soft cinematic "
             "lighting, gentle auspicious mood, full-bleed scene, "
             "cinematic vertical 9:16 composition, character standing in "
             "the upper-middle of the frame, environment darker and calmer "
             "toward the bottom edge for text legibility, no text, no "
             "watermark, no frame, no border")

WAP_JOBS = {
    "ic-wap-wood": WAP_STYLE + ", a gentle goddess Nüwa in flowing "
                   "sage-green robes standing in a misty ancient forest, "
                   "towering trees, soft green god-rays, floating petals, "
                   "jade-green palette",
    "ic-wap-fire": WAP_STYLE + ", a brave flame god Zhurong in "
                   "crimson-orange armor holding a torch standing before a "
                   "great sacred brazier at dusk, warm fire glow, floating "
                   "embers, deep red and amber sky, volcanic ground below",
    "ic-wap-earth": WAP_STYLE + ", a motherly earth goddess Houtu in "
                    "ochre-cream robes standing on fertile terraced fields "
                    "at golden hour, rolling hills, wheat and wildflowers, "
                    "rich dark soil in the foreground",
    "ic-wap-metal": WAP_STYLE + ", a headless warrior Xingtian dancing "
                    "with shield and battle-axe on a moonlit mountain "
                    "ridge, silver-steel palette, cold moonlight, clouds "
                    "and stars, dark rocky ground below",
    "ic-wap-water": WAP_STYLE + ", a graceful water goddess Luoshen in "
                    "flowing indigo-teal silk robes standing on a calm "
                    "misty river at dawn, long flowing hair and ribbons "
                    "drifting in the wind, soft water reflections, distant "
                    "mountains in blue mist, calm dark water in the "
                    "foreground",
}


def load_key() -> str:
    if os.environ.get("BOOKS_LLM_API_KEY"):
        return os.environ["BOOKS_LLM_API_KEY"].strip()
    for path in ("secrets/agnes_image.key", "web/llm_config.json"):
        if os.path.exists(path):
            txt = open(path, encoding="utf-8").read()
            if path.endswith(".json"):
                cfg = json.loads(txt)
                fbs = cfg.get("fallbacks") or []
                if fbs and fbs[0].get("api_key"):
                    return fbs[0]["api_key"].strip()
                return (cfg.get("api_key") or "").strip()
            line = txt.strip().splitlines()[0].strip()
            if line.lower().startswith("apikey:"):
                line = line.split(":", 1)[1].strip()
            return line
    raise SystemExit("找不到 agnes key（secrets/agnes_image.key）")


def gen(prompt: str, key: str) -> Image.Image:
    body = json.dumps({"model": MODEL, "prompt": prompt,
                       "size": SIZE, "n": 1}).encode()
    req = urllib.request.Request(
        BASE, data=body, method="POST",
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    item = data["data"][0]
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    else:
        with urllib.request.urlopen(item["url"], timeout=300) as r2:
            raw = r2.read()
    return Image.open(io.BytesIO(raw)).convert("RGB")


def key_out_auto(im: Image.Image) -> tuple[Image.Image, dict]:
    """与 gen_icon_cutouts.py 同口径：抠「与四边连通」的白底，容差自适应。"""
    a = np.asarray(im).astype(np.int16)
    h, w, _ = a.shape
    border = np.concatenate([a[0, :, :], a[-1, :, :],
                             a[:, 0, :], a[:, -1, :]])
    bg = np.median(border, axis=0)
    best = None
    for tol in (26, 20, 14, 9, 6):
        dist = np.abs(a - bg).max(axis=2)
        cand = (dist <= tol).astype(bool)
        seen = np.zeros((h, w), dtype=bool)
        dq = deque()
        for y, x in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1),
                     (h // 2, 0), (h // 2, w - 1),
                     (0, w // 2), (h - 1, w // 2)):
            if cand[y, x] and not seen[y, x]:
                seen[y, x] = True
                dq.append((y, x))
        while dq:
            y, x = dq.popleft()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and cand[ny, nx] \
                        and not seen[ny, nx]:
                    seen[ny, nx] = True
                    dq.append((ny, nx))
        alpha = np.where(seen, 0, 255).astype(np.uint8)
        out = np.dstack([np.asarray(im), alpha])
        res = Image.fromarray(out, "RGBA").filter(ImageFilter.GaussianBlur(0.6))
        subj = a[alpha == 255]
        if len(subj):
            sd = np.abs(subj - bg).max(axis=1)
            mind = int(np.percentile(sd, 0.5))
        else:
            mind = -1
        info = {"bg": [int(x) for x in bg], "tol": tol,
                "transparent_pct": round(100.0 * (alpha == 0).mean(), 1),
                "corner_alpha": [int(alpha[0, 0]), int(alpha[0, w - 1]),
                                 int(alpha[h - 1, 0]),
                                 int(alpha[h - 1, w - 1])],
                "subj_min_dist": mind}
        best = (res, info)
        if mind >= tol + 6:
            break
    return best


def fit_canvas(im: Image.Image, tw: int, th: int) -> Image.Image:
    """按主体包围盒收框（8% 呼吸边）后居中放进透明画布——不让抠完的
    主体缩成一小团，也不让它顶到边。"""
    a = np.asarray(im)
    alpha = a[:, :, 3]
    ys, xs = np.where(alpha > 8)
    if not len(xs):
        return im.resize((tw, th), Image.LANCZOS)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    pad = int(0.08 * max(x1 - x0 + 1, y1 - y0 + 1))
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(im.width - 1, x1 + pad); y1 = min(im.height - 1, y1 + pad)
    im = im.crop((x0, y0, x1 + 1, y1 + 1))
    sc = min(tw / im.width, th / im.height)
    nw, nh = max(1, int(im.width * sc)), max(1, int(im.height * sc))
    im = im.resize((nw, nh), Image.LANCZOS)
    cv = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    cv.paste(im, ((tw - nw) // 2, (th - nh) // 2), im)
    return cv


def to_wap(im: Image.Image) -> Image.Image:
    """1024×1536（2:3）→ 720×1280（9:16）：居中横裁后缩到位。
    角色都画在画面中部，横裁不伤主体。"""
    tw, th = WAP_SIZE
    target_ratio = tw / th
    w, h = im.size
    nw = int(round(h * target_ratio))
    if nw > w:
        nh = int(round(w / target_ratio))
        top = (h - nh) // 2
        im = im.crop((0, top, w, top + nh))
    else:
        left = (w - nw) // 2
        im = im.crop((left, 0, left + nw, h))
    return im.resize((tw, th), Image.LANCZOS)


def main() -> int:
    key = load_key()
    want = sys.argv[1:]
    os.makedirs(OUT_ICON, exist_ok=True)
    os.makedirs(OUT_WAP, exist_ok=True)
    names = [n for n in list(HERO_JOBS) + list(WAP_JOBS)
             if not want or n in want]
    for i, name in enumerate(names):
        if i:
            time.sleep(GAP)
        try:
            im = gen(HERO_JOBS.get(name) or WAP_JOBS[name], key)
        except Exception as e:  # noqa: BLE001
            print(f"{name}: 生成失败 {type(e).__name__} {e}")
            continue
        if name in HERO_JOBS:
            cut, info = key_out_auto(im)
            tw, th = SIZES[name.split("-")[0]]
            out = fit_canvas(cut, tw, th)
            arr = np.asarray(out)
            op = arr[arr[:, :, 3] > 200]
            mean = op[:, :3].mean(axis=0).round(1).tolist() if len(op) else None
            out.save(OUT_ICON + name + ".png", optimize=True)
            print(f"{name}: {out.size} {out.mode} 主体均色={mean} "
                  f"角alpha={info['corner_alpha']} tol={info['tol']} "
                  f"透明{info['transparent_pct']}%")
        else:
            out = to_wap(im).convert("RGB")
            out.save(OUT_WAP + name + ".jpg", quality=88, optimize=True)
            print(f"{name}: {out.size} {out.mode} -> {OUT_WAP}{name}.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
