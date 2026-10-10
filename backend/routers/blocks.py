"""任务块 / 子块 CRUD 路由。"""

from flask import Blueprint, request, jsonify, g

bp = Blueprint("blocks", __name__)


@bp.get("/document/<int:document_id>")
def list_blocks_by_document(document_id):
    """获取文档内全部块（含子块），按 sort_order 排序。"""
    rows = g.db.execute(
        "SELECT * FROM blocks WHERE document_id = ? ORDER BY sort_order, id", (document_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("")
def create_block():
    body = request.get_json(force=True) or {}
    document_id = body.get("document_id")
    if document_id is None:
        return jsonify({"error": "document_id 不能为空"}), 400

    # 验证 document_id 存在
    doc = g.db.execute("SELECT id FROM documents WHERE id = ?", (document_id,)).fetchone()
    if doc is None:
        return jsonify({"error": "文档不存在"}), 404

    parent_id = body.get("parent_id")
    if parent_id is not None:
        parent = g.db.execute(
            "SELECT document_id FROM blocks WHERE id = ?", (parent_id,)
        ).fetchone()
        if parent is None:
            return jsonify({"error": "父块不存在"}), 404
        if parent["document_id"] != document_id:
            return jsonify({"error": "父块不属于该文档"}), 400

    max_order = g.db.execute(
        "SELECT COALESCE(MAX(sort_order), -1) FROM blocks WHERE document_id = ? AND parent_id IS ?",
        (document_id, parent_id),
    ).fetchone()[0]

    cursor = g.db.execute(
        """INSERT INTO blocks (document_id, parent_id, title, content, sort_order, work_start_time, work_end_time)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (document_id, parent_id, body.get("title"), body.get("content", "[]"),
         max_order + 1, body.get("work_start_time"), body.get("work_end_time")),
    )
    g.db.commit()
    row = g.db.execute("SELECT * FROM blocks WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@bp.get("/<int:block_id>")
def get_block(block_id):
    row = g.db.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()
    if row is None:
        return jsonify({"error": "块不存在"}), 404
    return jsonify(dict(row))


@bp.put("/<int:block_id>")
def update_block(block_id):
    row = g.db.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()
    if row is None:
        return jsonify({"error": "块不存在"}), 404

    body = request.get_json(force=True) or {}
    fields, values = [], []
    for f in ("title", "content", "parent_id", "sort_order", "work_start_time", "work_end_time"):
        v = body.get(f)
        if v is not None:
            fields.append(f"{f} = ?")
            values.append(v)
    if fields:
        fields.append("updated_at = datetime('now', 'localtime')")
        values.append(block_id)
        g.db.execute(f"UPDATE blocks SET {', '.join(fields)} WHERE id = ?", values)
        g.db.commit()

    row = g.db.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()
    return jsonify(dict(row))


@bp.delete("/<int:block_id>")
def delete_block(block_id):
    row = g.db.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()
    if row is None:
        return jsonify({"error": "块不存在"}), 404

    child_count = g.db.execute(
        "SELECT COUNT(*) FROM blocks WHERE parent_id = ?", (block_id,)
    ).fetchone()[0]

    g.db.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
    g.db.commit()
    return jsonify({"deleted": block_id, "affected_children": child_count})
