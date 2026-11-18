#!/usr/bin/env python3
"""R78 守护图腾/灵魂角色卡头插画：黑底 PNG → 透明底 PNG。

用户实测（截图 2/3）：卡面上的麒麟等插画四角一块纯黑，而同一只灵兽经
「做我的锁屏」出来的整幅插画（wallpapers/gd-*.jpg）是暖色完整的——差距
不在画功在背景。仓库里 10 张 icons/gd-*.png、ic-*.png 全是「不透明 PNG +
纯 (0,0,0) 底」，注释却写着「agnes 出图抠透明」（并没有抠，生成脚本也没
入库，是一次性命令的产物）。

本脚本用现役生图管线重出这 10 张，并把底抠透明：
- 端点/口径与 scripts/gen_guardian_wap.py 同族（apihub.agnes-ai.com，
  key 取 secrets/agnes_image.key，模型用当前可用的 agnes-image-2.5-flash
  ——旧的 gpt-image-1 已不在账号可用列表里）；
- 该端点的 text image queue 不支持 background/output_format/quality 参数
  （实测 400），所以按「纯白底出图 + 本地连通域抠底」两步走：
  提示词点名 plain flat pure white background，拿到图后以四边中值为底色
  参考，用洪水填充只抠「与四边连通」的白底（主体内同色岛不误伤），
  再对 alpha 做 1px 羽化。白底与现役暖色主体（赭石/奶油/青/朱/银/靛）
  的通道差都在 40 以上，容差取 26 是安全侧。

用法：
  python3 scripts/gen_icon_cutouts.py gd-earth     # 单张试看
  python3 scripts/gen_icon_cutouts.py              # 全部 10 张
"""
import base64
import io
import json
import os
import sys
import urllib.request
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BASE = "https://apihub.agnes-ai.com/v1/images/generations"
OUT = "web/static/icons/"
MODEL = "agnes-image-2.5-flash"
SIZE = "1024x1536"

# 现役文件的输出尺寸（.sm-hero 卡头 150px 高 + 海报 _art 两处用法）
SIZES = {"gd": (369, 512), "ic": (486, 512)}

STYLE = ("children's picture book illustration, kawaii chubby rounded "
         "creature design, thick soft shapes, soft warm palette, gentle "
         "cozy auspicious mood, single subject centered, full body, clean "
         "silhouette, plain flat pure white background, solid color, no "
         "gradient, no vignette, no texture, no ground shadow, no text, "
         "no watermark, no frame, no border")

JOBS = {
    # ── 守护图腾（gd-*）：五灵兽，与 gen_guardian_wap.py 同一套口径 ──
    "gd-wood": f"{STYLE}, a chubby baby azure eastern dragon (qingqing) "
               "with tiny horns and jade-green scales, curling playfully, "
               "fresh sprouting mint-jade palette, hopeful upward mood",
    "gd-fire": f"{STYLE}, a chubby baby vermilion phoenix (zhuque) with "
               "round body and glowing coral-red wings, perched proudly, "
               "warm coral-amber palette, bright brave shining mood",
    "gd-earth": f"{STYLE}, a chubby baby qilin with gentle deer-like body, "
                "soft earthy ochre-cream coat and tiny stub horns, standing "
                "calmly on nothing, grounded steady mood",
    "gd-metal": f"{STYLE}, a chubby baby white tiger with round face, soft "
                "silver-white fur with faint grey stripes and golden eyes, "
                "sitting neatly, crisp silver-gold palette, tidy sharp mood",
    "gd-water": f"{STYLE}, a chubby baby black tortoise (xuanwu) with a "
                "tiny friendly snake companion curled around its shell, "
                "deep indigo-teal palette with warm firefly highlights, "
                "calm deep-water mood",
    # ── 灵魂角色（ic-*）：日主本命神话角色，全部公有领域原型 ──
    "ic-wood": f"{STYLE}, a gentle goddess Nüwa in flowing sage-green "
               "robes, nurturing creator deity, soft jade-green palette, "
               "kind warm mood",
    "ic-fire": f"{STYLE}, a brave flame god Zhurong in crimson-orange "
               "armor holding a torch, radiant warm fire palette, upright "
               "shining mood",
    "ic-earth": f"{STYLE}, a motherly earth goddess Houtu in ochre-cream "
                "robes, steady and generous, warm soil palette, grounded "
                "comforting mood",
    "ic-metal": f"{STYLE}, a headless warrior Xingtian still dancing with "
                "shield and battle-axe, silver-steel palette, fierce "
                "determined mood, face concealed by chest markings",
    "ic-water": f"{STYLE}, a graceful water goddess Luoshen in flowing "
                "indigo silk sleeves, delicate and serene, deep blue-teal "
                "palette, gentle flowing mood",
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


def gen(name: str, key: str) -> Image.Image:
    body = json.dumps({"model": MODEL, "prompt": JOBS[name],
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
    return Image.open(io.BytesIO(raw)).convert("RGB"), raw


def key_out_white(im: Image.Image, tol: int = 26) -> tuple[Image.Image, dict]:
    """把与四边连通的纯白底抠透明。返回 (RGBA 图, 诊断信息)。"""
    a = np.asarray(im).astype(np.int16)
    h, w, _ = a.shape
    border = np.concatenate([a[0, :, :], a[-1, :, :],
                             a[:, 0, :], a[:, -1, :]])
    bg = np.median(border, axis=0)
    dist = np.abs(a - bg).max(axis=2)
    cand = (dist <= tol).astype(bool)
    # 连通域：从四边向内的 BFS（ImageDraw.floodfill 在本机 Pillow 不存在）
    seen = np.zeros((h, w), dtype=bool)
    dq = deque()
    for y, x in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1),
                 (h // 2, 0), (h // 2, w - 1), (0, w // 2), (h - 1, w // 2)):
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
    res = Image.fromarray(out, "RGBA")
    # 1px 羽化：消掉白底与主体之间的硬锯齿（白底在暖色卡上本就近乎隐形）
    res = res.filter(ImageFilter.GaussianBlur(0.6))
    info = {"bg": [int(x) for x in bg], "tol": tol,
            "transparent_pct": round(100.0 * (alpha == 0).mean(), 1),
            "corner_alpha": [int(alpha[0, 0]), int(alpha[0, w - 1]),
                             int(alpha[h - 1, 0]), int(alpha[h - 1, w - 1])]}
    subj = a[alpha == 255]
    if len(subj):
        # 主体离底色有多近——近到容差之内说明这只灵兽本身是白的
        # （白虎），容差得往下收，否则会把毛皮一起抠掉。
        sd = np.abs(subj - bg).max(axis=1)
        info["subj_min_dist"] = int(np.percentile(sd, 0.5))
    else:
        info["subj_min_dist"] = -1
    return res, info


def key_out_auto(im: Image.Image) -> tuple[Image.Image, dict]:
    """容差自适应：在「底色抠得干净」与「别把浅色主体抠掉」之间取最大
    可用值。主体 0.5 分位到底色的距离必须比容差高出 6 以上，否则收紧。"""
    best = None
    for tol in (26, 20, 14, 9, 6):
        res, info = key_out_white(im, tol)
        best = (res, info)
        if info["subj_min_dist"] >= tol + 6:
            break
    return best


def main() -> int:
    key = load_key()
    names = sys.argv[1:] or list(JOBS)
    os.makedirs(OUT, exist_ok=True)
    for name in names:
        if name not in JOBS:
            print("未知任务:", name)
            continue
        tw, th = SIZES[name.split("-")[0]]
        try:
            im, raw = gen(name, key)
        except Exception as e:  # noqa: BLE001
            print(f"{name}: 生成失败 {type(e).__name__} {e}")
            continue
        cut, info = key_out_auto(im)
        # 诊断：主体是否还在（不透明像素的平均色不应接近白）
        arr = np.asarray(cut)
        op = arr[arr[:, :, 3] > 200]
        subj_mean = op[:, :3].mean(axis=0).round(1).tolist() if len(op) else None
        ys, xs = np.where(arr[:, :, 3] > 200)
        bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] \
            if len(ys) else None
        # 收框：生成图的主体只占画面约 1/5，直接等比缩到卡头尺寸会让
        # 灵兽缩成一小团（现役文件的主体几乎占满画幅）。按主体包围盒裁
        # 出、留 8% 呼吸边，再放进目标画布居中，保持现役的构图密度。
        if bbox:
            pad = int(0.08 * max(bbox[2] - bbox[0], bbox[3] - bbox[1]))
            box = (max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                   min(cut.width, bbox[2] + pad + 1),
                   min(cut.height, bbox[3] + pad + 1))
            cut = cut.crop(box)
        cut.thumbnail((tw, th), Image.LANCZOS)
        canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        canvas.paste(cut, ((tw - cut.width) // 2, (th - cut.height) // 2), cut)
        cut = canvas
        path = os.path.join(OUT, name + ".png")
        cut.save(path, "PNG", optimize=True)
        print(f"{name}: 源 {im.size} 透明 {info['transparent_pct']}% "
              f"四角alpha {info['corner_alpha']} 底色 {info['bg']} | "
              f"主体均色 {subj_mean} 主体盒 {bbox} "
              f"tol={info['tol']} 主次距={info['subj_min_dist']} -> {path} "
              f"{os.path.getsize(path)//1024}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
