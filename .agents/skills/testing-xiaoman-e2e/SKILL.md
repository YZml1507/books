---
name: testing-xiaoman-e2e
description: How to set up and drive end-to-end UI testing for 「小满的解忧铺」 (books repo) — mock LLM server, CJK input/font workarounds, huangli ask/chat verification flows
---

# E2E testing 「小满的解忧铺」 (books)

## Devin Secrets Needed
- None. All LLM behavior can be mocked locally.

## Serve the app with a mock LLM (required for chat/AI paths)
- `BOOKS_LLM_DISABLE=1` silently degrades: `/api/chat` returns `{}` (no `chat_task_id`), chat reply never writes back, `nameReviewBtn` stays disabled. To test real chat you must run a mock OpenAI-compatible server and launch uvicorn WITHOUT the disable flag:
  - Mock: bind `127.0.0.1:8901`, implement `POST /v1/chat/completions` → `{"choices":[{"message":{"content":"..."}}]}`. Working example was at `/tmp/mock_llm.py`; log request bodies to a file to verify backend-injected facts (e.g. `黄历判定：…`).
  - To exercise the `**`-fallback in `renderRichText`, make the reply contain paired `**粗体**` AND an unpaired `**` (e.g. a line that opens `**` and never closes it).
  - Launch: `BOOKS_LLM_API_KEY=mock BOOKS_LLM_BASE_URL=http://127.0.0.1:8901/v1 BOOKS_LLM_MODEL=mock .venv/bin/python -m uvicorn web.app:app --port 8123`
  - Same env vars also live in gitignored `web/llm_config.json`.

## CJK input: computer-tool `type` drops Chinese characters
- Neither the computer `type` action nor `xdotool type` can enter CJK into Chrome inputs. Use per-char Unicode keysyms instead:
  `DISPLAY=:0 xdotool key U<hex>` for each char (e.g. `出`=U51FA, `行`=U884C → `xdotool key U51FA` `xdotool key U884C`). A helper script `/tmp/type_cjk.sh "今天适合出行吗"` works if still present.
- Always verify the input's `.value` via `browser_console` after typing.

## CJK fonts may render as tofu in the desktop Chrome
- Install any CJK TTF into `~/.fonts` (repo has `data/external/starloom/...Alimama_DongFangDaKai_Regular.ttf`), then fully restart Chrome or glyphs stay tofu. Keep `--remote-debugging-port=29229` and `--user-data-dir=/home/ubuntu/.browser_data_dir` when relaunching so the computer tool reconnects.
- Don't `pkill -f "chrome.*--"` from a shell whose command line contains the same pattern — it kills your own shell. Kill via PID or a python script.

## Driving the UI reliably
- Screenshot space is 1024×768 but real display is 1600×1200 — click coordinates shift after layout changes (e.g. verdict card renders). Re-screenshot and click the visible position, or fall back to `browser_console` `el.click()` for stubborn buttons.
- `browser_console` only returns a value for a single-expression IIFE returning `JSON.stringify(...)`.

## Key selectors / flows
- Huangli view: `.func-card[data-view="huangli"]` → `#hlChips .hl-chip[data-hloffset]` (0/1/2/-1) → `#hlResult` `.hl-head` shows `YYYY-MM-DD`; free-input ask: `#hlAskInput` + `#hlAskBtn` → verdict `#hlVerdict`.
- Chat sidebar: `#recentToggle` opens `#recentSidebar`; `#chatInput` + `#chatSendBtn`; replies render via `renderRichText` (check `innerText` for `*` residue and count `<strong>`).
- Context chat: `💬 聊聊这件事` `#chatEntry` appears on result cards (qiming works; huangli result has no `.card` so no button there).
- Naming review: `data-view="qiming"` → defaults 李/1990/5/15/12/女 → `#qmSubmit` → `#nameReviewBtn` → `#nameReviewOut`.
- Backend fact merge: `services.chat_huangli_facts` handles 明天/后天/大后天 offsets (+1/+2/+3) and emits `黄历判定` strings — verify in the mock request log.

## Known baselines (do NOT report as regressions)
- `probe_ui_smoke` `btn:huangli` perpetually unstable here (font rendering), `probe_contract`/`probe_dollar_misuse` have existing FAILs.
- Huangli result shows `冲煞：[object Object]` — pre-existing bug (`esc()` on a chongsha object), identical on the base commit.
- Typed date prefixes in the huangli 问一嘴 input (明天/后天/大后天) are stripped for scene extraction but do NOT offset the judged day — the displayed day is used and the verdict says "今天". Chips and chat backend DO offset correctly.
