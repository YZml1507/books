"""R3（StepFun Studio 自主优化·周期一）日签场景主视觉提质：4 张宽幅场景图。

沿 R3257 同构图同 prompt（drop-in 替换，语义不变），换更强后端
agnes-image-2.5-flash + 2 倍分辨率（480×360 → 960×720，覆盖 3x 视网膜）
+ 提质量（q84 → q85+optimize）。cozy/lantern 两张无脚本溯源，不重绘。

密钥：AGNES_KEY_FILE 指向含「apikey: xxx」一行的文件（chmod 600）。
"""
import json, os, sys, time
from io import BytesIO
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from image_gen import gen_agnes

OUT = "web/static/cream/"

STYLE = ("cute chubby cream plush bear mascot, soft warm cream beige and pastel "
         "palette, children's picture book illustration, kawaii, thick soft "
         "rounded shapes, gentle cozy mood, no text, no watermark")

JOBS = {
    "bear-scene-good": f"{STYLE}, wide landscape scene: the bear stands on a sunny grassy hilltop with arms raised joyfully, big golden sun with soft rays, tiny wildflowers and butterflies, bright warm morning light",
    "bear-scene-sml":  f"{STYLE}, wide cozy scene: the bear sips warm tea sitting at a window seat with soft peach sunset light coming through, a small potted plant and steam curls, gentle contented mood",
    "bear-scene-mid":  f"{STYLE}, wide calm scene: the bear sits quietly on a windowsill looking at a mild plain sky with a few slow clouds, neutral peaceful everyday mood, soft even light",
    "bear-scene-bad":  f"{STYLE}, wide rainy scene: the bear wrapped in a fluffy pink blanket sits inside a small cushion fort by a rain-streaked window holding warm cocoa, rain drops on glass outside, cozy self-care healing mood not sad",
}


def gen(name: str, prompt: str, size: str = "1024x1024") -> None:
    tmp = f"/tmp/r3-{name}.png"
    r = gen_agnes(prompt, tmp, model="agnes-image-2.5-flash", size=size)
    from PIL import Image
    im = Image.open(tmp).convert("RGB")
    # 与 R3257 同裁剪逻辑（中置 92%×69%、上移 6%），2 倍分辨率落盘
    w, h = im.size
    tw, th = int(w * 0.92), int(h * 0.69)
    im = im.crop(((w - tw) // 2, (h - th) // 2 - int(h * 0.06),
                  (w + tw) // 2, (h + th) // 2 - int(h * 0.06)))
    im = im.resize((960, 720), Image.LANCZOS)
    path = OUT + name + ".jpg"
    im.save(path, "JPEG", quality=85, optimize=True)
    os.remove(tmp)
    print(f"OK {name} {os.path.getsize(path)//1024}KB {r['elapsed']}s", flush=True)


if __name__ == "__main__":
    only = sys.argv[1:] or list(JOBS)
    for n in only:
        try:
            gen(n, JOBS[n])
        except Exception as e:
            print(f"FAIL {n}: {e}", flush=True)
