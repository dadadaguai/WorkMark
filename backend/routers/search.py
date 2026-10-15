"""搜索与上下文恢复路由（FR-05）。

搜索采用 LIKE 子串匹配（本地数据量小，无分词问题）；
多关键词空格分隔，块标题与内容同时命中（AND 语义）。
"""

import json

from flask import Blueprint, request, jsonify, g

bp = Blueprint("search", __name__)


def _content_digest(content: str, terms: list[str], max_len: int = 120) -> str:
    """从 content JSON 提取纯文本摘要：优先返回首个关键词命中片段，否则取开头。"""
    try:
        items = json.loads(content)
    except (ValueError, TypeError):
        items = []
    if not isinstance(items, list):
        items = []
    parts: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("content"):
            parts.append(str(it["content"]))
        elif it.get("rows"):
            for row in it["rows"]:
                parts.append(" | ".join(str(c) for c in row))
        elif it.get("items"):
            parts.extend(str(i.get("text", "")) for i in it["items"])
    text = " ¶ ".join(p.strip() for p in parts if p and p.strip())
    low = text.lower()
    if terms:
        for t in terms:
            idx = low.find(t.lower())
            if idx != -1:
                start = max(0, idx - 30)
                frag = text[start:start + max_len].replace("\n", " ")
                return ("…" if start > 0 else "") + frag
    return (text[:max_len].replace("\n", " ")) or "（无文本内容）"


def _title_digest(title: str, terms: list[str], max_len: int = 120) -> str:
    """text 行正文摘要：优先返回首个关键词命中片段，否则取开头。"""
    text = " ¶ ".join(ln.strip() for ln in title.splitlines() if ln.strip())
    low = text.lower()
    if terms:
        for t in terms:
            idx = low.find(t.lower())
            if idx != -1:
                start = max(0, idx - 30)
                frag = text[start:start + max_len]
                return ("…" if start > 0 else "") + frag
    return text[:max_len] or "（空）"


def _match_all(haystacks: list, terms: list[str]) -> bool:
    """所有关键词至少命中任一字段（大小写无关）。"""
    lowers = [str(h).lower() for h in haystacks if h]
    return all(any(t.lower() in h for h in lowers) for t in terms)


@bp.get("")
def search():
    """全文搜索：块标题 + 块内容 + 文档名。

    参数：q（关键词，空格分隔多词）、date（YYYY-MM-DD，按创建/工作开始日期过滤），可组合。
    """
    q = (request.args.get("q") or "").strip()
    date = (request.args.get("date") or "").strip()
    if not q and not date:
        return jsonify({"error": "q 或 date 至少提供一个"}), 400
    terms = [t for t in q.split() if t]

    sql = "SELECT * FROM blocks"
    conds, params = [], []
    if date:
        conds.append("(created_at LIKE ? OR work_start_time LIKE ?)")
        params += [f"{date}%", f"{date}%"]
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    rows = g.db.execute(sql + " ORDER BY document_id, sort_order, id LIMIT 500", params).fetchall()

    doc_names = {
        r["id"]: r["name"]
        for r in g.db.execute("SELECT id, name FROM documents").fetchall()
    }

    results = []
    for r in rows:
        if terms and not _match_all([r["title"], r["content"]], terms):
            continue
        # text 行正文在 title；content 行摘要从 content JSON 提取
        digest = _content_digest(r["content"], terms) if r["content"] not in (None, "", "[]") \
            else _title_digest(r["title"] or "", terms)
        results.append({
            "block_id": r["id"],
            "document_id": r["document_id"],
            "document_name": doc_names.get(r["document_id"], ""),
            "block_title": (r["title"] or "").splitlines()[0][:60] if r["title"] else "内容块",
            "is_sub": r["parent_id"] is not None,
            "created_at": r["created_at"],
            "work_start_time": r["work_start_time"],
            "digest": digest,
        })
        if len(results) >= 100:
            break

    # 文档名命中（块未命中的空文档也能被找到）
    doc_hits = []
    if terms:
        cond = " AND ".join("name LIKE ?" for _ in terms)
        docs = g.db.execute(
            f"SELECT id, name, updated_at FROM documents WHERE {cond} LIMIT 20",
            [f"%{t}%" for t in terms],
        ).fetchall()
        for d in docs:
            cnt = g.db.execute(
                "SELECT COUNT(*) FROM blocks WHERE document_id = ?", (d["id"],)
            ).fetchone()[0]
            doc_hits.append({
                "document_id": d["id"],
                "document_name": d["name"],
                "updated_at": d["updated_at"],
                "block_count": cnt,
            })

    return jsonify({"blocks": results, "documents": doc_hits, "total": len(results)})


@bp.get("/last-work")
def last_work():
    """最近工作上下文：最近更新的文档及其停留位置（"继续上次工作"入口）。"""
    row = g.db.execute(
        "SELECT id, name, last_position, updated_at FROM documents "
        "ORDER BY updated_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return jsonify({"document": None})
    return jsonify({"document": dict(row)})
