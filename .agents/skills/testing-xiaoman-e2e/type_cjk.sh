#!/usr/bin/env bash
# Type CJK text into the focused window via per-char Unicode keysyms —
# computer-tool `type` and `xdotool type` both drop Chinese chars.
#
# Usage: ./type_cjk.sh "今天适合出行吗"
set -euo pipefail
text="${1:?usage: type_cjk.sh <text>}"
while IFS= read -r keysym; do
  DISPLAY="${DISPLAY:-:0}" xdotool key "$keysym"
done < <(python3 -c 'import sys; [print(f"U{ord(c):04X}") for c in sys.argv[1]]' "$text")
