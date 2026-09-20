"""books 项目生图工具 — 双轨共用

后端（并行双路，fallback 链）：
  1. agnes-image-2.1-flash  (https://apihub.agnes-ai.com/v1/images/generations)
     - 项目内推荐: 调性匹配小红书玄学审美，质量 7.5/10
     - 优点: 质量高、已有 key、出图稳定
  2. Pollinations.ai        (https://image.pollinations.ai/prompt/{prompt})
     - 项目原有: 免费快速无 key
     - 适用: 草图/占位图/大批量生成

使用:
  python scripts/image_gen.py "一个粉色水彩少女捧书" --backend agnes --out /tmp/test.png
  python scripts/image_gen.py "..." --backend pollinations --out /tmp/test.png
  python scripts/image_gen.py "..." --backend auto --size 1024x1024

密钥:
  - 环境变量 AGNES_API_KEY（首选）
  - 或 AGNES_KEY_FILE 指向的文本文件（内含「apikey: xxx」一行）
  - R230n（R26-P3）：此前钉死作者本机路径 C:/Users/Lenovo/... 入库——
    改环境变量驱动，路径不进代码。
"""
import os, sys, json, time, argparse, re, urllib.request, urllib.parse, urllib.error
from pathlib import Path

KEY_FILE = Path(os.environ.get("AGNES_KEY_FILE", "")) if os.environ.get("AGNES_KEY_FILE") else None
POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"
AGNES_BASE = "https://apihub.agnes-ai.com/v1"

def load_agnes_key() -> str:
    env = os.environ.get("AGNES_API_KEY")
    if env:
        return env.strip()
    if KEY_FILE is None or not KEY_FILE.exists():
        raise RuntimeError("未配置密钥：设 AGNES_API_KEY 或 AGNES_KEY_FILE=<密钥文件路径>")
    text = KEY_FILE.read_text(encoding="utf-8")
    m = re.search(r"apikey[：:]\s*(\S+)", text)
    if not m:
        raise RuntimeError(f"密钥文件解析失败: {KEY_FILE}")
    return m.group(1).strip()


def gen_agnes(prompt: str, out: str, model: str = "agnes-image-2.1-flash", size: str = "1024x1024") -> dict:
    """agnes-image 生图（OpenAI 兼容接口，返回 url，下载到 out）"""
    key = load_agnes_key()
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{AGNES_BASE}/images/generations",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    url = body["data"][0].get("url")
    if not url:
        return {"ok": False, "error": "no url in response", "raw": body}
    urllib.request.urlretrieve(url, out)
    return {"ok": True, "url": url, "out": out, "model": model, "elapsed": round(time.time() - t0, 1)}


def gen_pollinations(prompt: str, out: str, width: int = 1024, height: int = 1024) -> dict:
    """Pollinations.ai 生图（无 key，URL 直出；带 UA 避免 403）"""
    encoded = urllib.parse.quote(prompt)
    url = f"{POLLINATIONS_BASE}{encoded}?width={width}&height={height}&nologo=true&seed=42"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (books-image-gen)"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    Path(out).write_bytes(data)
    return {"ok": True, "url": url, "out": out, "model": "pollinations", "elapsed": round(time.time() - t0, 1), "bytes": len(data)}


def gen_auto(prompt: str, out: str, size: str = "1024x1024") -> dict:
    """自动 fallback: 先 agnes 失败再 pollinations"""
    try:
        r = gen_agnes(prompt, out, size=size)
        if r["ok"]:
            return r
        print(f"[auto] agnes 失败: {r.get('error')}, fallback pollinations")
    except Exception as e:
        print(f"[auto] agnes 异常: {e}, fallback pollinations")
    return gen_pollinations(prompt, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--backend", choices=["agnes", "pollinations", "auto"], default="auto")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", default="1024x1024")
    ap.add_argument("--model", default="agnes-image-2.1-flash")
    args = ap.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    if args.backend == "agnes":
        r = gen_agnes(args.prompt, args.out, model=args.model, size=args.size)
    elif args.backend == "pollinations":
        r = gen_pollinations(args.prompt, args.out)
    else:
        r = gen_auto(args.prompt, args.out, size=args.size)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(0 if r.get("ok") else 1)


if __name__ == "__main__":
    main()
