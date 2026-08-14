-- Book Research Infrastructure: 古籍 index schema.
--
-- Two address columns per unit, not one. Measured reason (DECISIONS.md D-005): page
-- anchors are edition-local -- the three 周易 editions use incompatible juan numbering
-- (1-69 / 1-10 / 0-41) and the same passage occurs a different number of times in each --
-- so <pb:> can cite but cannot align. The canonical address (卦 + 爻位) aligns but does
-- not point at a physical leaf. Both are needed and they are not interchangeable.

CREATE TABLE work (
    id            TEXT PRIMARY KEY,   -- e.g. KR1a0006
    title         TEXT,
    genre         TEXT,               -- 卜筮 / 三式 / 命理 / 相術 / 堪輿 / 占候 / 擬易 / 易類
    edition       TEXT,               -- BASEEDITION: tls / SBCK / WYG
    attribution   TEXT,               -- 王弼 / 孔穎達 / 程頤 / 朱熹 ...
    n_files       INTEGER,
    n_chars       INTEGER,
    source_url    TEXT,
    zip_sha256    TEXT,
    licence       TEXT,               -- 'none-stated' for every Kanripo repo: measured
    fetched_at    TEXT
);

CREATE TABLE unit (
    id            INTEGER PRIMARY KEY,
    work_id       TEXT NOT NULL REFERENCES work(id),
    file          TEXT NOT NULL,      -- source file, so a citation is reproducible
    raw_start     INTEGER NOT NULL,   -- offset into the concatenated work body
    raw_end       INTEGER NOT NULL,

    -- citation address: edition-local, verifiable by string match in the source file
    page_anchor   TEXT,               -- e.g. KR1a0006_SBCK_001-1a

    -- canonical address: cross-edition join key. NULL is a first-class value and means
    -- "not confidently attributable", never "probably this one".
    --
    -- Scheme-agnostic on purpose (D-015/D-016). The previous version declared `gua`,
    -- `gua_name`, `yao` as literal columns, so 周易's address scheme WAS the schema and a
    -- second one could not be stored at all -- measured against three Bible translations,
    -- which need book/chapter/verse. 周易 is now one scheme among others:
    --
    --   scheme     addr_name      addr1            addr2
    --   zhouyi     卦名 乾         卦號 1..64        爻位 九三 / 用九
    --   bcv        book Genesis   chapter          verse
    --   play       play name      act              scene
    --
    -- addr1 is INTEGER because ordering and range queries are needed; addr2 is TEXT
    -- because 周易's 爻位 are labels, not ordinals -- 用九 and 用六 are real addressable
    -- units with no numeric position. That constraint is stricter than the Bible's, so
    -- picking TEXT here is what keeps the general shape honest.
    scheme        TEXT,
    addr_name     TEXT,
    addr1         INTEGER,
    addr2         TEXT,

    layer         TEXT NOT NULL,      -- 經 / 注 / 疏 / 圖 / 十翼 / 正文
    text          TEXT NOT NULL,

    -- Citation DISCLOSURE (X-10). 0 means `text` is a contiguous substring of
    -- raw_start..raw_end; N > 0 means merge_units joined same-address runs and skipped N
    -- raw characters that sit between them, so the range is an ENVELOPE, not a quotation.
    --
    -- Measured over every unit (probes/probe_disclosure.py), not sampled:
    --   contiguous 3,953 (45.9%) · subsequence 4,658 (54.1%) · neither 0
    --   skipped chars: median 62, p90 571, max 7,388
    -- The quotation is honest either way (`neither` is 0, which is what G6 asserts), but a
    -- reader given 「經文」 with 62 characters of 注 silently removed from the middle cannot
    -- tell. Storing the COUNT rather than a boolean because "some material was omitted" and
    -- "7,388 characters were omitted" are different disclosures; `contiguous` is then just
    -- skipped_chars = 0.
    skipped_chars INTEGER NOT NULL DEFAULT 0,

    -- Corpus-damage warning (X-11). NULL = no known problem; otherwise the verdict from
    -- the cross-edition quality gate (text-damage / span-degenerate-B / span-overextended-A
    -- …) for the address this unit sits at. Populated from data/catalog/quality_report.json,
    -- which is produced by scripts/check_quality.py against data/raw/ — so the flag is a
    -- measurement, never a guess, and its provenance is recorded in build_meta.
    -- Marks 20 of 8,611 units (0.23%). Without it, a search can return OCR-damaged text
    -- (KR1a0006 卦61 上九翰青登于天 for 翰音登于天) with no warning at all.
    suspect       TEXT
);

CREATE INDEX idx_unit_addr  ON unit(scheme, addr1, addr2);
CREATE INDEX idx_unit_name  ON unit(scheme, addr_name);
CREATE INDEX idx_unit_work  ON unit(work_id);
CREATE INDEX idx_unit_layer ON unit(layer);

-- Convenience view so 周易 queries stay readable. A view, not columns: the moment the
-- address scheme is a column name, adding a second scheme becomes a migration (D-015).
CREATE VIEW unit_zhouyi AS
SELECT id, work_id, file, raw_start, raw_end, page_anchor,
       addr1 AS gua, addr_name AS gua_name, addr2 AS yao, layer, text,
       skipped_chars, suspect
FROM unit WHERE scheme = 'zhouyi';

-- Contentless FTS5: `text` lives in `unit`, only the char-segmented form is indexed.
-- Segmentation is mandatory, not an optimisation -- the default unicode61 tokeniser
-- silently returns nothing for 1-2 character CJK queries (D-004).
CREATE VIRTUAL TABLE unit_fts USING fts5(seg, content='');

-- Provenance for the run itself, so a stale index is detectable.
-- Source-to-source links (G4). These are relations PRINTED IN THE ORIGINAL, not inferred:
-- 焦氏易林 annotates cells with 「A之B」 meaning "this 林辭 also stands at that cell". Extracting
-- them is reading, not deriving, so they are Source knowledge and belong in this file — a
-- similarity-based link would be Derived and would belong in knowledge.db instead (D-023).
--
-- unit ids ARE used here, unlike in knowledge.db's evidence table, and the difference is
-- lifecycle rather than taste: this table is dropped and rebuilt together with `unit` in the
-- same transaction, so the ids cannot go stale. knowledge.db outlives the build, so it cannot
-- use them.
CREATE TABLE link (
    id        INTEGER PRIMARY KEY,
    kind      TEXT NOT NULL,        -- cross-reference
    src_unit  INTEGER NOT NULL REFERENCES unit(id),
    dst_unit  INTEGER NOT NULL REFERENCES unit(id),
    note      TEXT                  -- the printed text the link was read from
);

CREATE INDEX idx_link_src ON link(src_unit);
CREATE INDEX idx_link_dst ON link(dst_unit);

CREATE TABLE build_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
