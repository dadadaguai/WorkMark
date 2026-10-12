"""任务块 / 子块 CRUD 路由。"""

import json

from flask import Blueprint, request, jsonify, g

bp = Blueprint("blocks", __name__)


def normalize_content(content):
    """规范化 content JSON 为紧凑格式，保证前后端字符串一致（避免格式差异触发幽灵保存）。"""
    if content is None:
        return None
    try:
        return json.dumps(json.loads(content), ensure_ascii=False, separators=(",", ":"))
    except (ValueError, TypeError):
        return content


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
        (document_id, parent_id, body.get("title"),
         normalize_content(body.get("content", "[]")) or "[]",
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
    if "content" in body:
        body["content"] = normalize_content(body["content"])
    fields, values = [], []
    for f in ("title", "content", "parent_id", "sort_order", "work_start_time", "work_end_time"):
        if f not in body:
            continue
        v = body[f]
        # 时间字段允许显式传 null 清空；其余字段忽略 null
        if f in ("work_start_time", "work_end_time") or v is not None:
            fields.append(f"{f} = ?")
            values.append(v)
    if fields:
        fields.append("updated_at = datetime('now', 'localtime')")
        values.append(block_id)
        g.db.execute(f"UPDATE blocks SET {', '.join(fields)} WHERE id = ?", values)
        g.db.commit()

    row = g.db.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()
    return jsonify(dict(row))


@bp.post("/reorder")
def reorder_blocks():
    """批量更新块的父级与排序（拖拽排序用）。

    body: { "updates": [{ "id": 1, "parent_id": null, "sort_order": 0 }, ...] }
    """
    body = request.get_json(force=True) or {}
    updates = body.get("updates") or []
    if not updates:
        return jsonify({"error": "updates 不能为空"}), 400

    for u in updates:
        row = g.db.execute("SELECT id, document_id FROM blocks WHERE id = ?", (u["id"],)).fetchone()
        if row is None:
            return jsonify({"error": f"块 {u['id']} 不存在"}), 404
        pid = u.get("parent_id")
        if pid is not None:
            parent = g.db.execute(
                "SELECT document_id, parent_id FROM blocks WHERE id = ?", (pid,)
            ).fetchone()
            if parent is None or parent["parent_id"] is not None:
                return jsonify({"error": f"父块 {pid} 无效（必须是顶层块）"}), 400
            if parent["document_id"] != row["document_id"]:
                return jsonify({"error": "父子块不属于同一文档"}), 400

    for u in updates:
        g.db.execute(
            "UPDATE blocks SET parent_id = ?, sort_order = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (u.get("parent_id"), u.get("sort_order", 0), u["id"]),
        )
    g.db.commit()
    return jsonify({"updated": len(updates)})


@bp.post("/<int:block_id>/copy")
def copy_block(block_id):
    """完整复制块（顶层块连同其子块一起复制，副本独立、不保留与原块的父子关联）。"""
    row = g.db.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()
    if row is None:
        return jsonify({"error": "块不存在"}), 404

    def insert_copy(src, parent_id, sort_order):
        cursor = g.db.execute(
            """INSERT INTO blocks (document_id, parent_id, title, content, sort_order, work_start_time, work_end_time)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (src["document_id"], parent_id, src["title"], src["content"], sort_order,
             src["work_start_time"], src["work_end_time"]),
        )
        return cursor.lastrowid

    if row["parent_id"] is None:
        # 顶层块：原块之后插入，同级后续块 sort_order 顺延
        siblings = g.db.execute(
            "SELECT id FROM blocks WHERE document_id = ? AND parent_id IS NULL AND sort_order > ? ORDER BY sort_order",
            (row["document_id"], row["sort_order"]),
        ).fetchall()
        for s in siblings:
            g.db.execute("UPDATE blocks SET sort_order = sort_order + 1 WHERE id = ?", (s["id"],))
        new_id = insert_copy(row, None, row["sort_order"] + 1)
        children = g.db.execute(
            "SELECT * FROM blocks WHERE parent_id = ? ORDER BY sort_order, id", (block_id,)
        ).fetchall()
        for i, c in enumerate(children):
            insert_copy(c, new_id, i)
    else:
        # 子块：复制到同一父块末尾
        max_order = g.db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM blocks WHERE parent_id = ?", (row["parent_id"],)
        ).fetchone()[0]
        new_id = insert_copy(row, row["parent_id"], max_order + 1)

    g.db.commit()
    new_row = g.db.execute("SELECT * FROM blocks WHERE id = ?", (new_id,)).fetchone()
    return jsonify(dict(new_row)), 201


@bp.delete("/<int:block_id>")
def delete_block(block_id):
    """删除块。

    查询参数 keep_children=1 时保留直接子块：子块提升到被删块原位置
    （parent_id 改为被删块的父级，sort_order 依次排在原位置之后），后代随之跟随。
    默认级联删除全部后代（SQLite ON DELETE CASCADE）。
    """
    row = g.db.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()
    if row is None:
        return jsonify({"error": "块不存在"}), 404

    child_count = g.db.execute(
        "SELECT COUNT(*) FROM blocks WHERE parent_id = ?", (block_id,)
    ).fetchone()[0]

    keep_children = request.args.get("keep_children") == "1"
    if keep_children and child_count > 0:
        parent_id = row["parent_id"]
        pos = row["sort_order"]
        kids = g.db.execute(
            "SELECT id FROM blocks WHERE parent_id = ? ORDER BY sort_order, id", (block_id,)
        ).fetchall()
        n = len(kids)
        # 同父级中位于被删块之后的兄弟块整体后移，腾出插入空间
        g.db.execute(
            "UPDATE blocks SET sort_order = sort_order + ? WHERE parent_id IS ? AND sort_order > ?",
            (n, parent_id, pos),
        )
        for i, k in enumerate(kids):
            g.db.execute(
                "UPDATE blocks SET parent_id = ?, sort_order = ? WHERE id = ?",
                (parent_id, pos + 1 + i, k["id"]),
            )
        g.db.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
        g.db.commit()
        return jsonify({"deleted": block_id, "affected_children": child_count, "kept_children": n})

    g.db.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
    g.db.commit()
    return jsonify({"deleted": block_id, "affected_children": child_count})
