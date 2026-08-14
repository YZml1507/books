"""Test the play.py parser on Shakespeare."""
import sys
sys.path.insert(0, "src")
from guji.play import find_plays
from pathlib import Path

raw = (Path("data/raw_ext/generality") / "shakespeare" / "pg100.txt").read_text(encoding="utf-8", errors="replace")
plays = find_plays(raw)
print(f"plays/poems found: {len(plays)}")
print(f"  poems (no acts): {sum(1 for p in plays if p.is_poem)}")
print(f"  plays (with acts): {sum(1 for p in plays if not p.is_poem)}")
print()
for p in plays:
    act_count = len(p.acts)
    scene_count = sum(len(a["scenes"]) for a in p.acts)
    kind = "POEM" if p.is_poem else "PLAY"
    print(f"  [{p.ordinal:>2}] {kind} {p.title[:50]:<52} acts={act_count} scenes={scene_count}")
