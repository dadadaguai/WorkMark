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


def _content_type_label(content: str) -> str:
    """content 行（title 为空）的类型化标题，与编辑器摘要一致。"""
    try:
        arr = json.loads(content or "[]")
        it = arr[0] if isinstance(arr, list) and arr else None
        if isinstance(it, dict):
            return {
                "code": "代码", "shell": "命令", "output": "输出",
                "todo": "待办", "table": "表格", "image": "图片",
            }.get(it.get("type"), "内容块")
    except (ValueError, TypeError):
        pass
    return "内容块"


def _pure_text(title: str, content: str) -> str:
    """块的可搜索纯文本：title + content JSON 中的正文值（不含字段名）。"""
    parts: list[str] = []
    if title:
        parts.append(title)
    try:
        items = json.loads(content or "[]")
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                if it.get("content"):
                    parts.append(str(it["content"]))
                if it.get("rows"):
                    for row in it["rows"]:
                        parts.append(" | ".join(str(c) for c in row))
                if it.get("items"):
                    for i in it["items"]:
                        if isinstance(i, dict) and i.get("text"):
                            parts.append(str(i["text"]))
                if it.get("text"):
                    parts.append(str(it["text"]))
    except (ValueError, TypeError):
        pass
    return "\n".join(p for p in parts if p and str(p).strip())


@bp.get("")
def search():
    """全文搜索：块标题 + 块正文 + 文档名。

    参数：q（关键词，空格分隔多词 AND）、date（YYYY-MM-DD，按创建/工作开始日期过滤）、
    limit / offset（分页）。
    在纯文本上匹配（避免误命中 content JSON 的字段名），全量扫描后分页（本地数据量小，不截断）。
    """
    q = (request.args.get("q") or "").strip()
    date = (request.args.get("date") or "").strip()
    if not q and not date:
        return jsonify({"error": "q 或 date 至少提供一个"}), 400
    terms = [t for t in q.split() if t]

    limit = max(1, min(request.args.get("limit", 200, type=int) or 200, 1000))
    offset = max(0, request.args.get("offset", 0, type=int) or 0)

    # 全量读取并筛出纯文本命中（不截断，正确分页）
    all_rows = g.db.execute(
        "SELECT id, document_id, parent_id, title, content, created_at, work_start_time FROM blocks"
    ).fetchall()
    matched = []
    for r in all_rows:
        if terms:
            text = _pure_text(r["title"], r["content"]).lower()
            if not all(t.lower() in text for t in terms):
                continue
        if date:
            created = r["created_at"] or ""
            work = r["work_start_time"] or ""
            if not (created.startswith(date) or work.startswith(date)):
                continue
        matched.append(r)

    total = len(matched)
    rows = matched[offset:offset + limit]

    doc_names = {
        r["id"]: r["name"]
        for r in g.db.execute("SELECT id, name FROM documents").fetchall()
    }

    results = []
    for r in rows:
        # text 行正文在 title；content 行摘要从 content JSON 提取
        digest = _content_digest(r["content"], terms) if r["content"] not in (None, "", "[]") \
            else _title_digest(r["title"] or "", terms)
        results.append({
            "block_id": r["id"],
            "document_id": r["document_id"],
            "document_name": doc_names.get(r["document_id"], ""),
            "block_title": (r["title"] or "").splitlines()[0][:60] if r["title"] else _content_type_label(r["content"]),
            "is_sub": r["parent_id"] is not None,
            "created_at": r["created_at"],
            "work_start_time": r["work_start_time"],
            "digest": digest,
        })

    # 文档名命中（块未命中的空文档也能被找到），日期条件同样生效
    doc_hits = []
    if terms:
        doc_conds = ["name LIKE ?" for _ in terms]
        doc_params = [f"%{t}%" for t in terms]
        if date:
            doc_conds.append("created_at LIKE ?")
            doc_params.append(f"{date}%")
        docs = g.db.execute(
            f"SELECT id, name, updated_at FROM documents WHERE {' AND '.join(doc_conds)} LIMIT 20",
            doc_params,
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

    return jsonify({"blocks": results, "documents": doc_hits, "total": total})


@bp.get("/last-work")
def last_work():
    """最近访问文档（"继续上次浏览"入口）：按最后访问时间排序，回退到更新时间。"""
    row = g.db.execute(
        "SELECT id, name, last_position, updated_at, last_accessed_at FROM documents "
        "ORDER BY COALESCE(last_accessed_at, updated_at) DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return jsonify({"document": None})
    return jsonify({"document": dict(row)})
