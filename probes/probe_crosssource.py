"""Two unrelated digitisations of 周易: do they agree?

Kanripo KR1a0001 (Mandoku, WYG/tls, traditional) vs Gutenberg #25501 (unknown
provenance). This is the multi-edition problem in its cheapest observable form —
if these disagree, "the same work" is not a single text and the data model must
carry edition identity rather than collapsing it.

Also exercises markitdown's EPUB converter on real CJK.
"""
import glob
import os
import re

from markitdown import MarkItDown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KR = os.path.join(ROOT, "data", "raw", "KR1a0001")
PG = os.path.join(ROOT, "data", "raw_ext", "gutenberg", "25501")

GUA64 = ("乾坤屯蒙需訟師比泰否同人大有謙豫隨蠱臨觀噬嗑賁剝復无妄大畜頤大過坎離"
         "咸恆遯大壯晉明夷家人睽蹇解損益夬姤萃升困井革鼎震艮漸歸妹豐旅巽兌渙節"
         "小畜履師比中孚小過既濟未濟履泰")

# --- markitdown on the EPUB ---
print("=== markitdown: EPUB converter on CJK ===")
epub = os.path.join(PG, "pg25501.epub")
res = MarkItDown().convert(epub)
md = res.text_content
heads = re.findall(r"^#{1,6}\s*(.+)$", md, re.M)
print(f"  chars={len(md):,}  markdown headings={len(heads)}")
print(f"  first 6 headings: {heads[:6]}")
cid = len(re.findall(r"\(cid:\d+\)", md))
repl = md.count("�")
print(f"  (cid:) markers={cid}  U+FFFD={repl}")

# --- plain txt as the comparison baseline ---
with open(os.path.join(PG, "pg25501.txt"), encoding="utf-8") as f:
    pg_txt = f.read()

kr_txt = "".join(
    re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
    for p in sorted(glob.glob(os.path.join(KR, "*.txt")))
)


def strip(s):
    s = re.sub(r"<pb:[^>]+>|&\w+;", "", s)
    return re.sub(r"[\s　¶/「」『』《》，。、：；？！（）()\[\]]", "", s)


kr_c, pg_c = strip(kr_txt), strip(pg_txt)
print("\n=== raw size ===")
print(f"  Kanripo KR1a0001 : {len(kr_c):,} chars")
print(f"  Gutenberg #25501 : {len(pg_c):,} chars")
print(f"  ratio            : {len(pg_c)/max(len(kr_c),1):.2f}x")

# --- script variant: traditional vs simplified ---
print("\n=== script form (sampled marker characters) ===")
for trad, simp in (("風", "风"), ("澤", "泽"), ("雷", "雷"), ("觀", "观"), ("無", "无")):
    print(f"  {trad}/{simp}: Kanripo {kr_c.count(trad):>5}/{kr_c.count(simp):<5}"
          f"  Gutenberg {pg_c.count(trad):>5}/{pg_c.count(simp):<5}")

# --- do canonical 爻辭 phrases appear in both? ---
print("\n=== canonical phrases present in each source ===")
PHRASES = ["元亨利貞", "潛龍勿用", "君子終日乾乾", "履霜堅冰至", "亢龍有悔",
           "見群龍无首", "利涉大川", "自天祐之"]
print(f"  {'phrase':14} {'Kanripo':>8} {'Gutenberg':>10}")
for p in PHRASES:
    print(f"  {p:14} {kr_c.count(p):>8} {pg_c.count(p):>10}")

# --- structural markup available for citation ---
print("\n=== citation anchors available ===")
print(f"  Kanripo   <pb:> page markers : {len(re.findall(r'<pb:', kr_txt)):,}")
print(f"  Kanripo   《X第N》 gua headings: {len(re.findall(r'《[^》]{1,4}第[一二三四五六七八九十]+》', kr_txt)):,}")
print(f"  Gutenberg page markers        : {len(re.findall(r'<pb:', pg_txt)):,}")
print(f"  Gutenberg 卦 name occurrences  : "
      f"{sum(1 for g in set(GUA64) if g in pg_c)} distinct chars of 64卦 present")
