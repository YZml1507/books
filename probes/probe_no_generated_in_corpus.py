"""probe_no_generated_in_corpus.py — 生成文本不得入库（审查轨 R120a，D-140a）。

**宪法第三条硬约束**：「绝对不可入库的一类内容：生成文本。这条是硬约束，
不是偏好。」判据是「能否追溯到印本/底本」。

R178b 用 `guji.interpreter` 确定性规则引擎替换了 LLM 生成式解读，解读文本
仍然是**机器合成的叙述**（不是印本原文），因此仍属"生成文本"，必须与语料
物理隔离。允许的落点只有 `data/history.db`（D-039 用户显式授权的查询历史，
与语料库物理隔离、不参与检索）。

本 probe 从三个角度独立验证，任一角度失败即 FAIL：

  1. **静态**：`interpreter.py` 不得 import 任何网络/数据库设施，也不得出现
     corpus/knowledge 的写入调用。
  2. **动态**：真打 `/api/bazi` 与 `/api/ask` 拿到解读文本，然后在 corpus.db
     的全文索引与 knowledge.db 的 derived 表里**搜这段文本的特征片段**——
     搜到即说明生成文本已污染语料/知识库。
  3. **计数**：调用前后 corpus.db 的 unit 数、knowledge.db 的 derived 数
     必须一字不差；history.db 允许增长（授权落点），且本 probe 退出前清理。

第 2 条是关键：静态检查只能证明"这个版本的代码没写"，动态检查证明"实际
跑一遍确实没进去"。宪法第三条偏离 4 要求「独立见证」，两者缺一不可。

复现命令：
    C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe probes\\probe_no_generated_in_corpus.py
退出码：0 = 隔离成立；1 = 生成文本进了语料/知识库；2 = 无法判定。
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CORPUS_DB = os.path.join(ROOT, "data", "index", "corpus.db")
KNOWLEDGE_DB = os.path.join(ROOT, "data", "index", "knowledge.db")
INTERP = os.path.join(ROOT, "src", "guji", "interpreter.py")

# 生成层禁止触碰的设施
FORBIDDEN_IMPORTS = re.compile(
    r"^\s*(?:from|import)\s+(requests|urllib|http|httpx|socket|openai|anthropic"
    r"|sqlite3|aiohttp)\b", re.M)
FORBIDDEN_WRITES = re.compile(
    r"(INSERT\s+INTO|KnowledgeBase\(|\.record\(|corpus\.db|knowledge\.db)")


def load_app():
    try:
        mod = __import__("web.app", fromlist=["app", "create_app"])
    except ImportError:
        sys.path.insert(0, os.path.join(ROOT, "web"))
        mod = __import__("app", fromlist=["app", "create_app"])
    return mod.app if hasattr(mod, "app") else mod.create_app()


def counts() -> dict:
    out = {}
    with sqlite3.connect(CORPUS_DB) as c:
        out["corpus.unit"] = c.execute("SELECT COUNT(*) FROM unit").fetchone()[0]
    with sqlite3.connect(KNOWLEDGE_DB) as k:
        out["kb.derived"] = k.execute("SELECT COUNT(*) FROM derived").fetchone()[0]
        out["kb.evidence"] = k.execute(
            "SELECT COUNT(*) FROM evidence").fetchone()[0]
    return out


def shingles(text: str, n: int = 12, take: int = 6) -> list[str]:
    """取若干长片段做 LIKE 检索指纹。

    ⚠ **不要**先 `re.sub(r"\\s+","",text)`：库里存的原文保留换行与空白，
    去空白后的针永远匹配不上干草堆（本 probe 第一版实测踩过——阳性对照
    0/6 命中就是这么来的，见 D-140a）。做法是**保留原始空白**，只跳过
    以标点/空白为主的片段。
    """
    out = []
    step = max(1, len(text) // (take + 2))
    for i in range(0, max(1, len(text) - n), step):
        seg = text[i:i + n]
        if len(seg) < n:
            continue
        # 片段里必须有足够的实字（汉字/字母/数字），否则 LIKE 意义不大
        solid = len(re.findall(r"[\w\u4e00-\u9fff]", seg))
        if solid >= n // 2:
            out.append(seg)
        if len(out) >= take:
            break
    return out


def main() -> int:
    from fastapi.testclient import TestClient
    from guji import history as history_db

    for p in (CORPUS_DB, KNOWLEDGE_DB, INTERP):
        if not os.path.exists(p):
            print(f"probe_no_generated_in_corpus FAIL-ENV: 缺 {p}")
            return 2

    failures: list[str] = []

    # ── 1. 静态：解读层不得接触网络与数据库 ─────────────────
    src = open(INTERP, encoding="utf-8").read()
    bad_imp = FORBIDDEN_IMPORTS.findall(src)
    # 只看代码行，排除 docstring 里的说明文字
    code_lines = [l for l in src.split("\n")
                  if not l.strip().startswith("#")]
    bad_wr = [l.strip() for l in code_lines if FORBIDDEN_WRITES.search(l)
              and "不进" not in l and "隔离" not in l]
    print("1. 静态检查 src/guji/interpreter.py")
    print(f"   禁用 import 命中：{bad_imp or '无'}")
    print(f"   数据库写入调用命中：{bad_wr or '无'}")
    if bad_imp:
        failures.append(f"interpreter.py 引入了禁用设施：{bad_imp}")
    if bad_wr:
        failures.append(f"interpreter.py 出现数据库写入：{bad_wr}")

    # ── 2+3. 动态：真跑一遍，再在语料/知识库里搜生成文本 ──────
    client = TestClient(load_app())
    before = counts()
    hist_before = history_db.count()
    print(f"\n2. 调用前计数：{before}（history {hist_before}）")

    # ⚠ 判据关键（本 probe 第一版实测踩过，见 D-140a）：
    # `interpretation.text` 里**混着古籍引文**——解读本来就该引原文，那些片段
    # 在 corpus.db 里当然搜得到。拿整段 text 去搜必然误报"污染"。
    # 正确判据：只取**叙述部分**（sections[].lines，即机器合成的话），
    # 引文部分（citations）反而**应该**能在语料里找到，那是引用正确的证据。
    def narrative(it: dict) -> str:
        parts = []
        for sec in it.get("sections") or []:
            parts.append(str(sec.get("title") or ""))
            for ln in sec.get("lines") or []:
                parts.append(str(ln))
        return "\n".join(parts)

    texts: list[tuple[str, str]] = []
    quotes: list[tuple[str, list]] = []
    r = client.post("/api/bazi", json={"year": 1990, "month": 5, "day": 15,
                                       "hour": 10, "gender": "男",
                                       "question": "事业运如何？"})
    if r.status_code == 200:
        it = r.json().get("interpretation") or {}
        if narrative(it):
            texts.append(("/api/bazi", narrative(it)))
            quotes.append(("/api/bazi", it.get("citations") or []))
    r2 = client.post("/api/ask", json={"q": "無爲", "max_addresses": 2})
    if r2.status_code == 200:
        it2 = r2.json().get("interpretation") or {}
        if narrative(it2):
            texts.append(("/api/ask", narrative(it2)))
            quotes.append(("/api/ask", it2.get("citations") or []))

    if not texts:
        print("probe_no_generated_in_corpus FAIL-ENV: 拿不到任何解读文本，"
              "无法验证隔离（端点形状变了？）")
        return 2
    print(f"   取到解读**叙述**文本 {len(texts)} 段："
          f"{', '.join(f'{u}({len(t)}字)' for u, t in texts)}")
    print(f"   （引文部分单列 {sum(len(q) for _, q in quotes)} 条，"
          f"它们**应该**能在语料里找到——见第 5 步）")

    after = counts()
    hist_after = history_db.count()
    print(f"\n3. 调用后计数：{after}（history {hist_after}）")
    for k in before:
        if before[k] != after[k]:
            failures.append(f"{k} 在解读调用后变化：{before[k]} → {after[k]}"
                            f"（语料/知识库必须一字不差）")
    if hist_after <= hist_before:
        print("   ⚠ history.db 未增长——解读未落授权库（不算违规，但与 D-039 不符）")

    # 全文搜索：生成文本的指纹不得出现在语料或 derived 里
    print("\n4. 在 corpus.db / knowledge.db 里搜生成文本指纹")
    hits = []
    with sqlite3.connect(CORPUS_DB) as c, sqlite3.connect(KNOWLEDGE_DB) as k:
        for url, text in texts:
            for seg in shingles(text):
                n_unit = c.execute(
                    "SELECT COUNT(*) FROM unit WHERE text LIKE ?",
                    (f"%{seg}%",)).fetchone()[0]
                n_der = k.execute(
                    "SELECT COUNT(*) FROM derived WHERE claim LIKE ?",
                    (f"%{seg}%",)).fetchone()[0]
                n_ev = k.execute(
                    "SELECT COUNT(*) FROM evidence WHERE quote LIKE ?",
                    (f"%{seg}%",)).fetchone()[0]
                if n_unit or n_der or n_ev:
                    hits.append((url, seg, n_unit, n_der, n_ev))
    if hits:
        for url, seg, a, b, cc in hits:
            print(f"   ❌ {url} 片段 {seg!r} → corpus.unit={a} "
                  f"derived={b} evidence={cc}")
        failures.append(f"生成的叙述文本片段在语料/知识库中被搜到 {len(hits)} 处")
    else:
        print("   ✅ 叙述文本指纹在 corpus.unit / derived / evidence 中零命中")

    # ── 5. 阳性对照：引文必须能在语料里找到 ────────────────
    # 宪法第三条偏离 4：「没有已知阳性对照的质量闸门等于没有闸门」。
    # 若第 4 步只会返回"零命中"，它可能只是**搜索本身没生效**。用引文做对照：
    # 引文来自语料，必须搜得到。搜不到说明搜索路径坏了，第 4 步的"零命中"
    # 不能采信。
    print("\n5. 阳性对照：解读引用的古籍原文必须能在 corpus.db 里找到")
    checked = found = 0
    with sqlite3.connect(CORPUS_DB) as c:
        for url, cites in quotes:
            for cite in cites[:3]:
                q = cite.get("text") if isinstance(cite, dict) else None
                if not q:
                    continue
                # 引文首行常带展示用前缀（如 `【命理探原·强弱】`、`** 43 第四十三章`），
                # 那不是底本原文。取中段做对照，避开前缀。保留原始空白。
                segs = shingles(str(q), n=12, take=3)
                if not segs:
                    continue
                checked += 1
                n = 0
                for seg in segs:
                    n = c.execute("SELECT COUNT(*) FROM unit WHERE text LIKE ?",
                                  (f"%{seg}%",)).fetchone()[0]
                    if n:
                        break
                if n:
                    found += 1
                else:
                    print(f"   ⚠ {url} 引文片段 {segs[0]!r} 在语料中找不到")
    print(f"   对照结果：{found}/{checked} 条引文片段在语料中命中")
    if checked and found == 0:
        failures.append("阳性对照失败：没有任何引文能在 corpus.db 里搜到——"
                        "说明第 4 步的搜索路径无效，其'零命中'结论不可采信")
    elif not checked:
        print("   ⚠ 无可用引文做对照（citations 为空或无 text 字段），"
              "第 4 步结论的强度下降")

    # ── 清理授权落点的本轮新增（L-22）────────────────────
    cleaned = []
    n_extra = history_db.count() - hist_before
    if n_extra > 0:
        for rec in history_db.list_records(200)[:n_extra]:
            if history_db.delete_record(rec["id"]):
                cleaned.append(f"history#{rec['id']}")
    print(f"\n清理：{', '.join(cleaned) or '无'}；"
          f"history {hist_before} → {history_db.count()}")

    if failures:
        print("\nprobe_no_generated_in_corpus FAIL（宪法第三条：生成文本不得入库）")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nprobe_no_generated_in_corpus PASS: 解读文本只进 history.db"
          "（D-039 授权），corpus.db / knowledge.db 零污染")
    return 0


if __name__ == "__main__":
    sys.exit(main())
