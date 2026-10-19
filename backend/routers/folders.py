"""文件夹 CRUD 路由。"""

from flask import Blueprint, request, jsonify, g

bp = Blueprint("folders", __name__)


@bp.get("")
def list_folders():
    rows = g.db.execute("SELECT * FROM folders ORDER BY sort_order, id").fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("")
def create_folder():
    body = request.get_json(force=True)
    name = body.get("name")
    if not name:
        return jsonify({"error": "name 不能为空"}), 400
    parent_id = body.get("parent_id")

    max_order = g.db.execute(
        "SELECT COALESCE(MAX(sort_order), -1) FROM folders WHERE parent_id IS ?", (parent_id,)
    ).fetchone()[0]
    cursor = g.db.execute(
        "INSERT INTO folders (name, parent_id, sort_order) VALUES (?, ?, ?)",
        (name, parent_id, max_order + 1),
    )
    g.db.commit()
    row = g.db.execute("SELECT * FROM folders WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


def _descendant_folder_ids(folder_id) -> set:
    """返回 folder_id 的所有后代文件夹 id（含自身），用于循环引用校验。"""
    ids = {folder_id}
    frontier = [folder_id]
    while frontier:
        nxt = []
        for pid in frontier:
            for r in g.db.execute("SELECT id FROM folders WHERE parent_id = ?", (pid,)).fetchall():
                if r["id"] not in ids:
                    ids.add(r["id"])
                    nxt.append(r["id"])
        frontier = nxt
    return ids


@bp.put("/<int:folder_id>")
def update_folder(folder_id):
    row = g.db.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
    if row is None:
        return jsonify({"error": "文件夹不存在"}), 404

    body = request.get_json(force=True)
    if row["is_default"] and body.get("name"):
        return jsonify({"error": "默认文件夹不可重命名"}), 400

    # 移动前校验目标父文件夹：不能是自身或其子孙（否则形成循环嵌套）
    if "parent_id" in body and body["parent_id"] is not None:
        pid = body["parent_id"]
        if pid == folder_id:
            return jsonify({"error": "文件夹不能移动到自身"}), 400
        parent = g.db.execute("SELECT id FROM folders WHERE id = ?", (pid,)).fetchone()
        if parent is None:
            return jsonify({"error": "目标父文件夹不存在"}), 404
        if pid in _descendant_folder_ids(folder_id):
            return jsonify({"error": "不能移动到自身或子孙文件夹下"}), 400

    fields, values = [], []
    for f in ("name", "parent_id", "sort_order"):
        if f not in body:
            continue
        v = body[f]
        # parent_id 允许显式传 null（移回根目录）；其余字段忽略 null
        if f == "parent_id" or v is not None:
            fields.append(f"{f} = ?")
            values.append(v)
    if fields:
        fields.append("updated_at = datetime('now', 'localtime')")
        values.append(folder_id)
        g.db.execute(f"UPDATE folders SET {', '.join(fields)} WHERE id = ?", values)
        g.db.commit()

    row = g.db.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
    return jsonify(dict(row))


@bp.delete("/<int:folder_id>")
def delete_folder(folder_id):
    row = g.db.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
    if row is None:
        return jsonify({"error": "文件夹不存在"}), 404
    if row["is_default"]:
        return jsonify({"error": "默认文件夹不可删除"}), 400

    children = g.db.execute(
        "SELECT COUNT(*) FROM documents WHERE folder_id = ?", (folder_id,)
    ).fetchone()[0]
    subfolders = g.db.execute(
        "SELECT COUNT(*) FROM folders WHERE parent_id = ?", (folder_id,)
    ).fetchone()[0]

    g.db.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    g.db.commit()
    return jsonify({
        "deleted": folder_id,
        "affected_documents": children,
        "affected_subfolders": subfolders,
    })
