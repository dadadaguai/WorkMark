"""收件箱（快速记录）路由（FR-09）。

条目默认 pending（待整理）。整理操作：
- move：内容变成目标文档的顶层任务块，条目标记 moved
- copy：同上但条目保留，标记 copied
- link：仅关联文档保留原记录，标记 linked
内容不做格式识别，统一作为文本内容块保存（保留换行缩进）。
"""

from flask import Blueprint, request, jsonify, g

bp = Blueprint("inbox", __name__)

STATUS_LABELS = {"pending": "待整理", "moved": "已移动", "copied": "已复制", "linked": "已关联"}


def _insert_block(document_id: int, content: str) -> int:
    """在目标文档顶层末尾插入 text 任务段（title 存多行正文），返回块 id。"""
    max_order = g.db.execute(
        "SELECT COALESCE(MAX(sort_order), -1) FROM blocks WHERE document_id = ? AND parent_id IS NULL",
        (document_id,),
    ).fetchone()[0]
    cur = g.db.execute(
        "INSERT INTO blocks (document_id, parent_id, title, content, sort_order) VALUES (?, NULL, ?, '[]', ?)",
        (document_id, content, max_order + 1),
    )
    return cur.lastrowid


def _item_row(item_id: int):
    row = g.db.execute(
        "SELECT i.*, d.name AS target_document_name FROM inbox_items i "
        "LEFT JOIN documents d ON d.id = i.target_document_id WHERE i.id = ?",
        (item_id,),
    ).fetchone()
    return row


@bp.post("")
def create_item():
    """新建收件箱条目。"""
    body = request.get_json(force=True) or {}
    content = (body.get("content") or "").strip()
    if not content:
        return jsonify({"error": "内容不能为空"}), 400
    cur = g.db.execute("INSERT INTO inbox_items (content) VALUES (?)", (content,))
    g.db.commit()
    return jsonify(dict(_item_row(cur.lastrowid))), 201


@bp.get("")
def list_items():
    """收件箱列表（status 过滤，最新在前）。"""
    status = request.args.get("status") or None
    if status:
        rows = g.db.execute(
            "SELECT i.*, d.name AS target_document_name FROM inbox_items i "
            "LEFT JOIN documents d ON d.id = i.target_document_id "
            "WHERE i.status = ? ORDER BY i.id DESC",
            (status,),
        ).fetchall()
    else:
        rows = g.db.execute(
            "SELECT i.*, d.name AS target_document_name FROM inbox_items i "
            "LEFT JOIN documents d ON d.id = i.target_document_id "
            "ORDER BY i.id DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/<int:item_id>/move")
def move_item(item_id):
    """移动到任务文档：创建任务块，条目标记 moved。"""
    row = g.db.execute("SELECT * FROM inbox_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return jsonify({"error": "条目不存在"}), 404
    body = request.get_json(force=True) or {}
    document_id = body.get("document_id")
    doc = g.db.execute("SELECT id FROM documents WHERE id = ?", (document_id,)).fetchone()
    if doc is None:
        return jsonify({"error": "目标文档不存在"}), 404

    block_id = _insert_block(document_id, row["content"])
    g.db.execute(
        "UPDATE inbox_items SET status = 'moved', target_document_id = ? WHERE id = ?",
        (document_id, item_id),
    )
    g.db.commit()
    item = dict(_item_row(item_id))
    item["block_id"] = block_id
    return jsonify(item)


@bp.post("/<int:item_id>/copy")
def copy_item(item_id):
    """复制到任务文档：创建任务块，条目保留并标记 copied。"""
    row = g.db.execute("SELECT * FROM inbox_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return jsonify({"error": "条目不存在"}), 404
    body = request.get_json(force=True) or {}
    document_id = body.get("document_id")
    doc = g.db.execute("SELECT id FROM documents WHERE id = ?", (document_id,)).fetchone()
    if doc is None:
        return jsonify({"error": "目标文档不存在"}), 404

    block_id = _insert_block(document_id, row["content"])
    g.db.execute(
        "UPDATE inbox_items SET status = 'copied', target_document_id = ? WHERE id = ?",
        (document_id, item_id),
    )
    g.db.commit()
    item = dict(_item_row(item_id))
    item["block_id"] = block_id
    return jsonify(item)


@bp.post("/<int:item_id>/link")
def link_item(item_id):
    """关联文档但保留原记录。"""
    row = g.db.execute("SELECT * FROM inbox_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return jsonify({"error": "条目不存在"}), 404
    body = request.get_json(force=True) or {}
    document_id = body.get("document_id")
    doc = g.db.execute("SELECT id FROM documents WHERE id = ?", (document_id,)).fetchone()
    if doc is None:
        return jsonify({"error": "目标文档不存在"}), 404
    g.db.execute(
        "UPDATE inbox_items SET status = 'linked', target_document_id = ? WHERE id = ?",
        (document_id, item_id),
    )
    g.db.commit()
    return jsonify(dict(_item_row(item_id)))


@bp.delete("/<int:item_id>")
def delete_item(item_id):
    """删除收件箱条目（不影响已移动/复制产生的任务块）。"""
    row = g.db.execute("SELECT id FROM inbox_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return jsonify({"error": "条目不存在"}), 404
    g.db.execute("DELETE FROM inbox_items WHERE id = ?", (item_id,))
    g.db.commit()
    return jsonify({"deleted": item_id})
