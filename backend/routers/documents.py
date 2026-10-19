"""任务文档 CRUD 路由。"""

import json

from flask import Blueprint, request, jsonify, g

bp = Blueprint("documents", __name__)


def _block_summary(title, content):
    """文档列表摘要：text 行取首行正文；content 行取类型化标签。"""
    if title:
        first = next((ln.strip() for ln in title.splitlines() if ln.strip()), "")
        return first[:80]
    try:
        arr = json.loads(content or "[]")
        it = arr[0] if isinstance(arr, list) and arr else None
        if isinstance(it, dict):
            label = {"code": "代码", "shell": "命令", "output": "输出",
                     "todo": "待办", "table": "表格", "image": "图片"}.get(it.get("type"), "内容块")
            return f"[{label}]"
    except (ValueError, TypeError):
        pass
    return ""


def _document_summaries():
    """每个文档首个顶层块摘要（text 行正文 / content 行类型标签）。"""
    out = {}
    rows = g.db.execute(
        "SELECT b.document_id, b.title, b.content FROM blocks b "
        "WHERE b.parent_id IS NULL AND b.id = ("
        "  SELECT MIN(id) FROM blocks WHERE parent_id IS NULL AND document_id = b.document_id"
        ")"
    ).fetchall()
    for r in rows:
        out[r["document_id"]] = _block_summary(r["title"], r["content"])
    return out


@bp.get("")
def list_documents():
    folder_id = request.args.get("folder_id", type=int)
    if folder_id is not None:
        rows = g.db.execute(
            "SELECT * FROM documents WHERE folder_id = ? ORDER BY sort_order DESC, id DESC", (folder_id,)
        ).fetchall()
    else:
        rows = g.db.execute("SELECT * FROM documents ORDER BY updated_at DESC").fetchall()
    summaries = _document_summaries()
    result = [dict(r) | {"summary": summaries.get(r["id"], "")} for r in rows]
    return jsonify(result)


@bp.post("")
def create_document():
    body = request.get_json(force=True) or {}
    fid = body.get("folder_id")

    # folder_id 为空时使用默认文件夹
    if fid is None:
        row = g.db.execute("SELECT id FROM folders WHERE is_default = 1").fetchone()
        if row is None:
            return jsonify({"error": "默认文件夹不存在"}), 500
        fid = row["id"]
    else:
        # 指定的文件夹必须存在（否则外键约束触发 500，改为明确 404）
        row = g.db.execute("SELECT id FROM folders WHERE id = ?", (fid,)).fetchone()
        if row is None:
            return jsonify({"error": "文件夹不存在"}), 404

    name = body.get("name")
    if not name:
        count = g.db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        name = f"新建文档 {count + 1}"

    max_order = g.db.execute(
        "SELECT COALESCE(MAX(sort_order), -1) FROM documents WHERE folder_id = ?", (fid,)
    ).fetchone()[0]
    cursor = g.db.execute(
        "INSERT INTO documents (folder_id, name, sort_order) VALUES (?, ?, ?)",
        (fid, name, max_order + 1),
    )
    g.db.commit()
    row = g.db.execute("SELECT * FROM documents WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@bp.get("/<int:document_id>")
def get_document(document_id):
    row = g.db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        return jsonify({"error": "文档不存在"}), 404
    return jsonify(dict(row))


@bp.put("/<int:document_id>")
def update_document(document_id):
    row = g.db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        return jsonify({"error": "文档不存在"}), 404

    body = request.get_json(force=True) or {}
    changed = False

    # 内容性更新（名称/位置/排序）→ 更新 updated_at（内容修改时间）
    content_fields, content_values = [], []
    for f in ("name", "folder_id", "sort_order"):
        if f in body and body[f] is not None:
            content_fields.append(f"{f} = ?")
            content_values.append(body[f])
    if content_fields:
        content_fields.append("updated_at = datetime('now', 'localtime')")
        content_values.append(document_id)
        g.db.execute(f"UPDATE documents SET {', '.join(content_fields)} WHERE id = ?", content_values)
        changed = True

    # 停留位置 → 更新 last_accessed_at（访问时间，与内容更新时间分离）
    if "last_position" in body and body["last_position"] is not None:
        g.db.execute(
            "UPDATE documents SET last_position = ?, last_accessed_at = datetime('now', 'localtime') WHERE id = ?",
            (body["last_position"], document_id),
        )
        changed = True

    if changed:
        g.db.commit()

    row = g.db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    return jsonify(dict(row))


@bp.delete("/<int:document_id>")
def delete_document(document_id):
    row = g.db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        return jsonify({"error": "文档不存在"}), 404
    block_count = g.db.execute(
        "SELECT COUNT(*) FROM blocks WHERE document_id = ?", (document_id,)
    ).fetchone()[0]
    g.db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    g.db.commit()
    return jsonify({"deleted": document_id, "affected_blocks": block_count})
