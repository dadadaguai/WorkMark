"""附件管理路由（FR-07）。

存储规则：文件默认复制到 data/attachments/（managed，stored_path 存文件名）；
大文件可引用原始路径（is_reference=1，stored_path 存原始绝对路径）。
删除附件前检查 block_attachments 引用关系，仅无引用时删除记录与物理文件。
"""

from pathlib import Path
import uuid

from flask import Blueprint, request, jsonify, g, send_file

from backend.database import DATA_DIR

bp = Blueprint("attachments", __name__)

ATTACH_DIR = DATA_DIR / "attachments"


def _uuid_hex() -> str:
    return uuid.uuid4().hex[:12]


def _file_path(row) -> Path:
    """根据附件记录解析实际文件路径。"""
    if row["is_reference"]:
        return Path(row["stored_path"])
    return ATTACH_DIR / Path(row["stored_path"]).name


@bp.post("")
def upload_attachment():
    """上传附件（multipart/form-data）。

    字段：file（文件）或 original_path（引用模式原始路径）、
    block_id（可选，建立块关联）、is_reference（"1" = 引用原始路径不复制）。
    """
    f = request.files.get("file")
    block_id = request.form.get("block_id") or None
    is_reference = request.form.get("is_reference") == "1"

    if block_id is not None:
        blk = g.db.execute("SELECT id FROM blocks WHERE id = ?", (block_id,)).fetchone()
        if blk is None:
            return jsonify({"error": "块不存在"}), 404

    if is_reference:
        original_path = (request.form.get("original_path") or "").strip()
        if not original_path:
            return jsonify({"error": "缺少 original_path"}), 400
        p = Path(original_path)
        if not p.is_file():
            return jsonify({"error": "原始路径不存在或不可读"}), 400
        stored_path = original_path
        file_name = f.filename if f else p.name
        size = p.stat().st_size
        mime = f.mimetype if f else (p.suffix.lstrip(".") or "application/octet-stream")
    else:
        if f is None:
            return jsonify({"error": "缺少文件"}), 400
        ATTACH_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = f"{_uuid_hex()}_{Path(f.filename).name}"
        dest = ATTACH_DIR / safe_name
        f.save(str(dest))
        stored_path = safe_name
        file_name = f.filename
        size = dest.stat().st_size
        mime = f.mimetype

    cur = g.db.execute(
        "INSERT INTO attachments (file_name, stored_path, file_size, file_type, is_reference) "
        "VALUES (?, ?, ?, ?, ?)",
        (file_name, stored_path, size, mime, 1 if is_reference else 0),
    )
    att_id = cur.lastrowid
    if block_id is not None:
        g.db.execute(
            "INSERT OR IGNORE INTO block_attachments (block_id, attachment_id) VALUES (?, ?)",
            (block_id, att_id),
        )
    g.db.commit()
    row = g.db.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
    return jsonify(dict(row)), 201


@bp.get("")
def list_attachments():
    """附件列表（q 按文件名搜索），含引用计数、引用路径有效性、所属记录。"""
    q = (request.args.get("q") or "").strip()
    sql = (
        "SELECT a.*, (SELECT COUNT(*) FROM block_attachments ba WHERE ba.attachment_id = a.id) AS ref_count "
        "FROM attachments a"
    )
    params: list = []
    if q:
        sql += " WHERE a.file_name LIKE ?"
        params.append(f"%{q}%")
    sql += " ORDER BY a.id DESC LIMIT 200"

    rows = []
    for r in g.db.execute(sql, params).fetchall():
        item = dict(r)
        if item["is_reference"]:
            # 引用模式：检查原始路径是否仍有效
            item["path_exists"] = Path(item["stored_path"]).is_file()
        else:
            item["path_exists"] = None
        refs = g.db.execute(
            "SELECT b.id AS block_id, b.title, b.document_id, d.name AS document_name "
            "FROM block_attachments ba "
            "JOIN blocks b ON b.id = ba.block_id "
            "JOIN documents d ON d.id = b.document_id "
            "WHERE ba.attachment_id = ? LIMIT 5",
            (item["id"],),
        ).fetchall()
        item["used_by"] = [dict(x) for x in refs]
        rows.append(item)
    return jsonify(rows)


@bp.get("/<int:att_id>/file")
def get_attachment_file(att_id):
    """获取附件文件内容（用于打开/预览）。"""
    row = g.db.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
    if row is None:
        return jsonify({"error": "附件不存在"}), 404
    p = _file_path(row)
    if row["is_reference"] and not p.is_file():
        return jsonify({"error": "引用路径失效"}), 410
    if not p.is_file():
        return jsonify({"error": "附件文件丢失"}), 410
    return send_file(str(p), download_name=row["file_name"])


@bp.delete("/<int:att_id>")
def delete_attachment(att_id):
    """删除附件：仅当不再被任何记录引用时删除记录与物理文件。"""
    row = g.db.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
    if row is None:
        return jsonify({"error": "附件不存在"}), 404

    ref_count = g.db.execute(
        "SELECT COUNT(*) FROM block_attachments WHERE attachment_id = ?", (att_id,)
    ).fetchone()[0]
    if ref_count > 0:
        return jsonify({"error": f"仍被 {ref_count} 条记录引用，无法删除", "ref_count": ref_count}), 409

    g.db.execute("DELETE FROM attachments WHERE id = ?", (att_id,))
    g.db.commit()

    # 物理删除仅针对托管文件；引用模式不删除用户原始文件
    if not row["is_reference"]:
        p = _file_path(row)
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    return jsonify({"deleted": att_id})
