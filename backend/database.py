"""SQLite 数据库连接与 schema 初始化。"""

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


def init_db():
    """初始化数据库 schema 和默认数据。"""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        # 插入默认文件夹（如果不存在）
        row = conn.execute("SELECT id FROM folders WHERE is_default = 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO folders (name, parent_id, sort_order, is_default) VALUES ('默认文件夹', NULL, 0, 1)"
            )
        conn.commit()
    finally:
        conn.close()
