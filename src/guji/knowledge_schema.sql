-- G8: Source / Derived / Conversation physical separation.
--
-- A SEPARATE DATABASE FILE from corpus.db, and that is the whole point rather than a
-- packaging preference. Two measured reasons:
--
--  1. ingest.build() begins with `os.remove(db_path)`. corpus.db is destroyed and rebuilt
--     from data/raw/ in ~5 seconds, and the project deliberately treats that as a cheap,
--     routine operation ("重建索引...随便重建"). Any derived claim or conversation stored
--     there would be silently annihilated by a normal rebuild. Source knowledge is
--     REGENERABLE; derived and conversation knowledge is NOT. They cannot share a lifecycle.
--  2. Isolation you can state as a file boundary is checkable. A query against corpus.db
--     cannot return a derived claim because the rows are not in that file at all — no
--     filter to forget, no layer flag to get wrong. Compare the earlier failure where 經 and
--     注 shared one layer value and merge_units fused them (D-008): a distinction that
--     depends on remembering a filter is a distinction that eventually leaks.
--
-- WHAT THIS SCHEMA REFUSES TO DO, and why (this is the D-015 lesson applied in advance):
-- evidence does NOT reference unit(id). Unit ids are assigned by a counter during the build
-- (`uid += 1`), so they are NOT stable across rebuilds — a claim citing unit 1234 would point
-- at a different passage after the next build. Evidence therefore stores the DURABLE citation
-- (work + file + raw offsets + page anchor + canonical address + the quoted text), which is
-- exactly what D-005 established as the identity of a passage. A derived claim stays
-- auditable against data/raw/ even if corpus.db is deleted entirely.

CREATE TABLE IF NOT EXISTS derived (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL,     -- summary | diff | link | answer | refusal
    claim       TEXT NOT NULL,
    method      TEXT NOT NULL,     -- what produced it: module.function / model id + version
    confidence  TEXT,              -- NULL is legitimate: unknown is a first-class value
    thread_id   INTEGER REFERENCES thread(id),
    created_at  TEXT NOT NULL,

    -- A claim that asserts something must rest on evidence; a REFUSAL must not be required
    -- to. This is not a technicality: G7 is 「能承认证据不足」, so 'no evidence supports X'
    -- is itself a legitimate derived output, and the obvious design — a NOT NULL evidence
    -- reference — would have made G7's own output unstorable. That is the same mistake as
    -- writing 卦/爻 as column names (D-015), caught before it was made rather than after.
    CHECK (kind IN ('summary', 'diff', 'link', 'answer', 'refusal'))
);

CREATE TABLE IF NOT EXISTS evidence (
    id          INTEGER PRIMARY KEY,
    derived_id  INTEGER NOT NULL REFERENCES derived(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'supports',   -- supports | contradicts | context

    -- The durable citation. Every field is verifiable in data/raw/ without the index.
    work_id     TEXT NOT NULL,
    file        TEXT NOT NULL,
    raw_start   INTEGER NOT NULL,
    raw_end     INTEGER NOT NULL,
    page_anchor TEXT,
    scheme      TEXT,
    addr1       INTEGER,
    addr2       TEXT,
    quote       TEXT NOT NULL,     -- stored so the claim can be re-checked after a rebuild

    CHECK (role IN ('supports', 'contradicts', 'context'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_derived ON evidence(derived_id);
CREATE INDEX IF NOT EXISTS idx_evidence_addr ON evidence(work_id, scheme, addr1, addr2);

-- Conversation Memory. Also the substrate for G9 (cross-session research threads): a thread
-- is a line of enquiry, and `build_meta` records builds, not enquiries.
CREATE TABLE IF NOT EXISTS thread (
    id          INTEGER PRIMARY KEY,
    topic       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',       -- open | parked | closed
    opened_at   TEXT NOT NULL,
    updated_at  TEXT,
    CHECK (status IN ('open', 'parked', 'closed'))
);

CREATE TABLE IF NOT EXISTS turn (
    id          INTEGER PRIMARY KEY,
    thread_id   INTEGER NOT NULL REFERENCES thread(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    role        TEXT NOT NULL,                      -- user | assistant
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    CHECK (role IN ('user', 'assistant')),
    UNIQUE (thread_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_turn_thread ON turn(thread_id, seq);

-- Full-text over DERIVED claims only, in its own file, so that searching source text and
-- searching derived text are different operations against different indexes. corpus.db's
-- unit_fts contains no derived text and this one contains no source text; probe_g8_isolation
-- asserts both directions.
CREATE VIRTUAL TABLE IF NOT EXISTS derived_fts USING fts5(seg, content='');

CREATE TABLE IF NOT EXISTS kb_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ── 知命产品化扩展（2026-08-19，R002） ──────────────────────
-- 这三张表服务于产品化功能（每日运势、用户偏好、收藏），
-- 与学术研究语料（derived/evidence/thread）在知识上有边界但不冲突。
-- 不修改现有表，只追加。

-- 用户偏好：主题、最近使用的功能模块
CREATE TABLE IF NOT EXISTS user_prefs (
    key         TEXT PRIMARY KEY,    -- theme | recent_modules | font_size
    value       TEXT,                -- JSON 编码的偏好值
    updated_at  TEXT NOT NULL
);

-- 每日运势缓存：避免同一天重复调用 LLM
-- 缓存只存当天，第二天自动失效（按 date 字段判断）
CREATE TABLE IF NOT EXISTS daily_cache (
    date         TEXT PRIMARY KEY,   -- 'YYYY-MM-DD'
    bazi_result  TEXT,               -- JSON: {level, summary, noble, do, dont}
    tarot_result TEXT,               -- JSON: {card, orientation, meaning}
    created_at   TEXT NOT NULL
);

-- 收藏：用户收藏的算命结果、读书笔记、塔罗牌阵
CREATE TABLE IF NOT EXISTS favorites (
    id          INTEGER PRIMARY KEY,
    type        TEXT NOT NULL,       -- bazi | tarot | book | thread
    ref_id      TEXT NOT NULL,       -- 关联的业务 ID
    title       TEXT NOT NULL,       -- 展示标题
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_favorites_type ON favorites(type);
