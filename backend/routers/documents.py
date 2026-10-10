"""任务文档 CRUD 路由。"""

from flask import Blueprint, request, jsonify, g

bp = Blueprint("documents", __name__)


@bp.get("")
def list_documents():
    folder_id = request.args.get("folder_id", type=int)
    if folder_id is not None:
        rows = g.db.execute(
            "SELECT * FROM documents WHERE folder_id = ? ORDER BY sort_order, id", (folder_id,)
        ).fetchall()
    else:
        rows = g.db.execute("SELECT * FROM documents ORDER BY updated_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])


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
    fields, values = [], []
    for f in ("name", "folder_id", "sort_order", "last_position"):
        v = body.get(f)
        if v is not None:
            fields.append(f"{f} = ?")
            values.append(v)
    if fields:
        fields.append("updated_at = datetime('now', 'localtime')")
        values.append(document_id)
        g.db.execute(f"UPDATE documents SET {', '.join(fields)} WHERE id = ?", values)
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
