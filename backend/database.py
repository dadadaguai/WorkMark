"""SQLite 数据库连接与 schema 初始化。"""

import json
import shutil
import sqlite3
from pathlib import Path

# 本地数据目录
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "workmark.db"

SCHEMA_SQL = """
-- 文件夹（可多层嵌套，parent_id 为空表示根级；is_default=1 为默认文件夹）
CREATE TABLE IF NOT EXISTS folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    parent_id   INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_default  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 任务文档
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id     INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    name          TEXT    NOT NULL DEFAULT '新建文档',
    sort_order    INTEGER NOT NULL DEFAULT 0,
    last_position TEXT,   -- JSON，记录上次停留位置（block_id, scroll 等）
    last_accessed_at TEXT, -- 最后访问时间（与内容 updated_at 分离）
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 任务块 / 子块（parent_id 为空表示顶层任务块，非空表示子块）
CREATE TABLE IF NOT EXISTS blocks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    parent_id       INTEGER REFERENCES blocks(id) ON DELETE CASCADE,
    title           TEXT,
    content         TEXT    NOT NULL DEFAULT '[]',  -- JSON 数组，存储内容块
    sort_order      INTEGER NOT NULL DEFAULT 0,
    work_start_time TEXT,
    work_end_time   TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_blocks_document ON blocks(document_id);
CREATE INDEX IF NOT EXISTS idx_blocks_parent   ON blocks(parent_id);

-- 附件
CREATE TABLE IF NOT EXISTS attachments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name    TEXT    NOT NULL,
    stored_path  TEXT    NOT NULL,   -- 本地管理路径或原始引用路径
    file_size    INTEGER,
    file_type    TEXT,
    is_reference INTEGER NOT NULL DEFAULT 0,  -- 1 = 引用原始路径
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 块-附件引用关系
CREATE TABLE IF NOT EXISTS block_attachments (
    block_id      INTEGER NOT NULL REFERENCES blocks(id)      ON DELETE CASCADE,
    attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
    PRIMARY KEY (block_id, attachment_id)
);

-- 收件箱（快速记录）
CREATE TABLE IF NOT EXISTS inbox_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    content             TEXT    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'pending',  -- pending / moved / copied / linked
    target_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 全文搜索（FTS5）
CREATE VIRTUAL TABLE IF NOT EXISTS blocks_fts USING fts5(
    title, content, content=blocks, content_rowid=id
);

-- FTS 同步触发器
CREATE TRIGGER IF NOT EXISTS blocks_fts_ai AFTER INSERT ON blocks BEGIN
    INSERT INTO blocks_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END;
CREATE TRIGGER IF NOT EXISTS blocks_fts_ad AFTER DELETE ON blocks BEGIN
    INSERT INTO blocks_fts(blocks_fts, rowid, title, content) VALUES ('delete', old.id, old.title, old.content);
END;
CREATE TRIGGER IF NOT EXISTS blocks_fts_au AFTER UPDATE ON blocks BEGIN
    INSERT INTO blocks_fts(blocks_fts, rowid, title, content) VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO blocks_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END;
"""


def get_connection() -> sqlite3.Connection:
    """获取 SQLite 连接，启用外键和 WAL 模式。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _ensure_document_columns(conn):
    """为已有库补齐新增列（幂等）。"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "last_accessed_at" not in cols:
        conn.execute("ALTER TABLE documents ADD COLUMN last_accessed_at TEXT")


def init_db():
    """初始化数据库 schema 和默认数据。"""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        _ensure_document_columns(conn)
        # 插入默认文件夹（如果不存在）
        row = conn.execute("SELECT id FROM folders WHERE is_default = 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO folders (name, parent_id, sort_order, is_default) VALUES ('默认文件夹', NULL, 0, 1)"
            )
        conn.commit()
        # 正文流数据迁移（旧混合行 → text/content 单块行），自动备份，幂等
        if _needs_textflow_migration(conn):
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            shutil.copy(str(DB_PATH), str(DB_PATH) + ".bak-textflow")
            _migrate_textflow(conn)
            conn.commit()
    finally:
        conn.close()


# ── 正文流迁移（2026-10：每行=一个任务段；text 行 title 存多行正文，content 行存单个内容块）──
# 旧模型：title=任务文本 + content=[多个内容块（可含 text 续写项）]
# 新模型：title 并入正文 text 段；每个非 text 内容块拆为独立行（独享时间戳）

def _split_segments(title, content_json):
    """把旧行的 title + content JSON 拆成任务段序列：[(kind, title, item)]。
    kind='text' → title 为正文；kind='content' → item 为单个内容块。相邻 text 合并。"""
    items = []
    if title and title.strip():
        items.append({"type": "text", "content": title})
    try:
        arr = json.loads(content_json or "[]")
        if isinstance(arr, list):
            items.extend(x for x in arr if isinstance(x, dict))
    except ValueError:
        pass
    merged = []
    for it in items:
        if it.get("type") == "text":
            c = (it.get("content") or "").strip("\n")
            if not c.strip():
                continue  # 空 text 项（旧续写占位）丢弃
            if merged and merged[-1][0] == "text":
                merged[-1][1] += "\n" + c
            else:
                merged.append(["text", c, None])
        else:
            merged.append(["content", "", it])
    if not merged:
        merged.append(["text", "", None])
    return [(k, t, i) for k, t, i in merged]


def _needs_textflow_migration(conn) -> bool:
    """存在旧混合行（多块 / text 项 / 有正文 title 又有内容块）才需要迁移。"""
    for r in conn.execute("SELECT title, content FROM blocks").fetchall():
        try:
            arr = json.loads(r["content"] or "[]")
        except ValueError:
            continue
        if not isinstance(arr, list) or not arr:
            continue  # 纯 text 行，已是新模型
        if len(arr) > 1 or arr[0].get("type") == "text" or (r["title"] or "").strip():
            return True
    return False


def _migrate_textflow(conn):
    """按文档 + 父级分组拆分旧行并重排 sort_order；首段复用原行，其余段 INSERT 新行。"""
    doc_ids = [r["id"] for r in conn.execute("SELECT id FROM documents").fetchall()]
    for doc_id in doc_ids:
        pids = [r["parent_id"] for r in conn.execute(
            "SELECT DISTINCT parent_id FROM blocks WHERE document_id = ?", (doc_id,)).fetchall()]
        for pid in pids:
            rows = conn.execute(
                "SELECT * FROM blocks WHERE document_id = ? AND parent_id IS ? ORDER BY sort_order, id",
                (doc_id, pid)).fetchall()
            seq = []  # [(seg, src_row, reuse)]
            for r in rows:
                for i, seg in enumerate(_split_segments(r["title"], r["content"])):
                    seq.append((seg, r, i == 0))
            for order, ((kind, title, item), src, reuse) in enumerate(seq):
                content = "[]" if item is None else json.dumps([item], ensure_ascii=False, separators=(",", ":"))
                if reuse:
                    conn.execute(
                        "UPDATE blocks SET title = ?, content = ?, sort_order = ? WHERE id = ?",
                        (title, content, order, src["id"]))
                else:
                    cur = conn.execute(
                        """INSERT INTO blocks
                           (document_id, parent_id, title, content, sort_order,
                            work_start_time, work_end_time, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (doc_id, pid, title, content, order,
                         src["work_start_time"], src["work_end_time"],
                         src["created_at"], src["updated_at"]))
                    # 附件引用关系随图片块迁移到新行
                    if item and item.get("attachment_id"):
                        conn.execute(
                            "UPDATE block_attachments SET block_id = ? WHERE block_id = ? AND attachment_id = ?",
                            (cur.lastrowid, src["id"], item["attachment_id"]))
