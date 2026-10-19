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


def _content_error(content):
    """校验 content 为合法 JSON 数组；返回错误消息或 None。"""
    if content is None:
        return None
    try:
        arr = json.loads(content)
    except (ValueError, TypeError):
        return "content 必须是合法的 JSON 数组"
    if not isinstance(arr, list):
        return "content 必须是 JSON 数组"
    return None


def _work_time_error(start, end):
    """校验工作时段：结束时间不能早于开始时间。"""
    if start and end and end < start:
        return "结束时间不能早于开始时间"
    return None


def _touch_document(document_id):
    """块内容变化时同步更新所属文档的 updated_at（内容更新时间）。"""
    g.db.execute(
        "UPDATE documents SET updated_at = datetime('now', 'localtime') WHERE id = ?",
        (document_id,),
    )


def _hierarchy_error(document_id, parent_id, exclude_id=None):
    """统一父子层级校验（两层模型：父块必须是顶层块）。

    返回错误消息字符串；合法时返回 None。
    规则：禁止跨文档、自身引用、循环嵌套、以及把含子块的块降为子块。
    """
    if parent_id is None:
        return None
    if parent_id == exclude_id:
        return "不能把块设为其自身的子块"
    parent = g.db.execute(
        "SELECT id, document_id, parent_id FROM blocks WHERE id = ?", (parent_id,)
    ).fetchone()
    if parent is None:
        return "父块不存在"
    if parent["document_id"] != document_id:
        return "父块不属于该文档"
    if parent["parent_id"] is not None:
        return "父块必须是顶层块（最多两层）"
    if exclude_id is not None:
        n = g.db.execute(
            "SELECT COUNT(*) FROM blocks WHERE parent_id = ?", (exclude_id,)
        ).fetchone()[0]
        if n > 0:
            return "含有子块的块不能设为子块"
    return None


def _attachment_ids_in_content(content):
    """提取 content JSON 中引用到的 attachment_id 集合。"""
    try:
        arr = json.loads(content or "[]")
    except (ValueError, TypeError):
        return set()
    if not isinstance(arr, list):
        return set()
    ids = set()
    for it in arr:
        if isinstance(it, dict) and it.get("attachment_id") is not None:
            try:
                ids.add(int(it["attachment_id"]))
            except (ValueError, TypeError):
                pass
    return ids


def _missing_attachment_ids(content):
    """返回 content 中引用但不存在的 attachment_id（外键未命中会触发 500，改为预检）。"""
    refs = _attachment_ids_in_content(content)
    if not refs:
        return []
    ph = ",".join("?" * len(refs))
    rows = g.db.execute(f"SELECT id FROM attachments WHERE id IN ({ph})", list(refs)).fetchall()
    existing = {r["id"] for r in rows}
    return sorted(refs - existing)


def sync_block_attachments(block_id, content):
    """根据块内容统一维护 block_attachments 关联（创建/更新/复制后调用）。"""
    refs = _attachment_ids_in_content(content)
    existing = {
        r["attachment_id"]
        for r in g.db.execute(
            "SELECT attachment_id FROM block_attachments WHERE block_id = ?", (block_id,)
        ).fetchall()
    }
    for aid in refs - existing:
        g.db.execute(
            "INSERT OR IGNORE INTO block_attachments (block_id, attachment_id) VALUES (?, ?)",
            (block_id, aid),
        )
    for aid in existing - refs:
        g.db.execute(
            "DELETE FROM block_attachments WHERE block_id = ? AND attachment_id = ?",
            (block_id, aid),
        )


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
        err = _hierarchy_error(document_id, parent_id)
        if err:
            return jsonify({"error": err}), 400

    # 可选 after_id：插入到同父级指定块之后（后续兄弟顺延）；不传则追加到末尾
    after_id = body.get("after_id")
    if after_id is not None:
        ref = g.db.execute(
            "SELECT document_id, parent_id, sort_order FROM blocks WHERE id = ?", (after_id,)
        ).fetchone()
        if ref is None:
            return jsonify({"error": "插入位置块不存在"}), 400
        if ref["document_id"] != document_id:
            return jsonify({"error": "插入位置块不属于该文档"}), 400
        if (ref["parent_id"] or None) != (parent_id or None):
            return jsonify({"error": "插入位置块与目标父级不一致"}), 400
        g.db.execute(
            "UPDATE blocks SET sort_order = sort_order + 1 "
            "WHERE document_id = ? AND parent_id IS ? AND sort_order > ?",
            (document_id, parent_id, ref["sort_order"]),
        )
        sort_order = ref["sort_order"] + 1
    else:
        max_order = g.db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM blocks WHERE document_id = ? AND parent_id IS ?",
            (document_id, parent_id),
        ).fetchone()[0]
        sort_order = max_order + 1

    # 内容结构 / 工作时段 / 附件引用预检（明确 400，而非外键 500）
    raw_content = body.get("content", "[]")
    err = _content_error(raw_content)
    if err:
        return jsonify({"error": err}), 400
    ws = body.get("work_start_time")
    we = body.get("work_end_time")
    err = _work_time_error(ws, we)
    if err:
        return jsonify({"error": err}), 400
    content = normalize_content(raw_content) or "[]"
    missing = _missing_attachment_ids(content)
    if missing:
        return jsonify({"error": f"引用的附件不存在：{missing}"}), 400

    cursor = g.db.execute(
        """INSERT INTO blocks (document_id, parent_id, title, content, sort_order, work_start_time, work_end_time)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (document_id, parent_id, body.get("title"),
         content,
         sort_order, ws, we),
    )
    sync_block_attachments(cursor.lastrowid, content)
    _touch_document(document_id)
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
        err = _content_error(body["content"])
        if err:
            return jsonify({"error": err}), 400
        body["content"] = normalize_content(body["content"])

    # 父子层级统一校验（普通更新允许改 parent_id）
    if body.get("parent_id") is not None:
        err = _hierarchy_error(row["document_id"], body["parent_id"], exclude_id=block_id)
        if err:
            return jsonify({"error": err}), 400

    # 工作时段合并校验：结束时间不能早于开始时间（显式传 null 表示清空）
    if "work_start_time" in body or "work_end_time" in body:
        start = body.get("work_start_time", row["work_start_time"])
        end = body.get("work_end_time", row["work_end_time"])
        err = _work_time_error(start, end)
        if err:
            return jsonify({"error": err}), 400

    # 附件引用预检
    if "content" in body:
        missing = _missing_attachment_ids(body["content"])
        if missing:
            return jsonify({"error": f"引用的附件不存在：{missing}"}), 400

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
        if "content" in body:
            sync_block_attachments(block_id, body["content"])
        _touch_document(row["document_id"])
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

    # 先取全部块信息（id → 文档/当前父级），用于统一校验最终结构
    ids = [u["id"] for u in updates]
    ph = ",".join("?" * len(ids))
    rows = g.db.execute(
        f"SELECT id, document_id, parent_id FROM blocks WHERE id IN ({ph})", ids
    ).fetchall()
    if len(rows) != len(ids):
        return jsonify({"error": "存在不存在的块"}), 404
    meta = {r["id"]: r for r in rows}
    new_parent = {u["id"]: u.get("parent_id") for u in updates}

    def final_parent_of(bid):
        """块最终的父级：本次更新则取新值，否则取数据库当前值。"""
        if bid in new_parent:
            return new_parent[bid]
        m = meta.get(bid)
        if m is not None:
            return m["parent_id"]
        row = g.db.execute("SELECT parent_id FROM blocks WHERE id = ?", (bid,)).fetchone()
        return row["parent_id"] if row else None

    # 统一校验：两层模型——最终父块必须是顶层块；禁止自引用/循环/跨文档/降级含子块的块
    for u in updates:
        bid = u["id"]
        pid = new_parent.get(bid)
        if pid is None:
            continue
        if pid == bid:
            return jsonify({"error": f"块 {bid} 不能作为自身的子块"}), 400
        doc_id = meta[bid]["document_id"]
        # 父块可能不在本次 updates 中，需查库取得其文档归属（此前只查 updates 内块导致真实父块误判为不存在）
        pmeta = meta.get(pid)
        if pmeta is None:
            pmeta = g.db.execute(
                "SELECT id, document_id, parent_id FROM blocks WHERE id = ?", (pid,)
            ).fetchone()
        if pmeta is None:
            return jsonify({"error": f"父块 {pid} 不存在"}), 404
        if pmeta["document_id"] != doc_id:
            return jsonify({"error": f"块 {bid} 与父块 {pid} 不属于同一文档"}), 400
        # 父块的“最终父级”：若本次也更新了它的 parent_id 则取新值，否则取其当前值
        if final_parent_of(pid) is not None:
            return jsonify({"error": f"父块 {pid} 最终不是顶层块，不能作为 {bid} 的父块"}), 400
        n = g.db.execute(
            "SELECT COUNT(*) FROM blocks WHERE parent_id = ?", (bid,)
        ).fetchone()[0]
        if n > 0:
            return jsonify({"error": f"块 {bid} 含有子块，不能设为子块"}), 400

    doc_ids = {meta[u["id"]]["document_id"] for u in updates}
    for u in updates:
        g.db.execute(
            "UPDATE blocks SET parent_id = ?, sort_order = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (u.get("parent_id"), u.get("sort_order", 0), u["id"]),
        )
    for d in doc_ids:
        _touch_document(d)
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
        sync_block_attachments(cursor.lastrowid, src["content"])
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

    _touch_document(row["document_id"])
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
        # 明确限定 document_id + 父级，避免顶层块（parent_id 全为 NULL）跨文档误更新排序
        g.db.execute(
            "UPDATE blocks SET sort_order = sort_order + ? "
            "WHERE document_id = ? AND parent_id IS ? AND sort_order > ?",
            (n, row["document_id"], parent_id, pos),
        )
        for i, k in enumerate(kids):
            g.db.execute(
                "UPDATE blocks SET parent_id = ?, sort_order = ? WHERE id = ?",
                (parent_id, pos + 1 + i, k["id"]),
            )
        g.db.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
        _touch_document(row["document_id"])
        g.db.commit()
        return jsonify({"deleted": block_id, "affected_children": child_count, "kept_children": n})

    g.db.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
    _touch_document(row["document_id"])
    g.db.commit()
    return jsonify({"deleted": block_id, "affected_children": child_count})
