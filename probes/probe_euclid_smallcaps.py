"""Find where 'P r o b l e m' comes from in Euclid html."""
import re
from pathlib import Path

h = (Path("data/raw_ext/generality") / "euclid-elements" / "pg21076.html").read_text(encoding="utf-8", errors="replace")

# Is 'P r o b l e m' literally in the raw html?
m = re.search(r"P r o b l e m", h)
print(f"'P r o b l e m' in raw html: {bool(m)}  at {m.start() if m else None}")

# Look for single-char spans
ms = re.findall(r'<span class="[^"]*">[A-Za-z]</span>', h)
print(f"single-char spans: {len(ms)}")
for s in ms[:8]:
    print(f"  {s!r}")

# Search for 'Problem' near a proposition heading
idx = h.find("PROPOSITION")
if idx < 0:
    idx = h.find("PROP.")
print(f"first 'PROP.' at {idx}")
if idx > 0:
    chunk = h[idx:idx+1500]
    print("=== 1500 chars from first PROP. ===")
    print(chunk)
