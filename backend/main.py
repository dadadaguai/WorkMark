"""Flask 应用入口。"""

from pathlib import Path
import sqlite3
from contextlib import contextmanager

from flask import Flask, jsonify, g
from flask_cors import CORS

from backend.database import init_db, get_connection, DATA_DIR

# 前端构建产物目录
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = Flask(__name__, static_folder=None)

# 开发阶段允许跨域（Vite dev server 运行在 5173）
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])


@contextmanager
def get_db():
    """请求级数据库连接上下文。"""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


@app.before_request
def before_request():
    """每个请求开始时获取数据库连接。"""
    g.db = get_connection()


@app.teardown_request
def teardown_request(exc):
    """请求结束时关闭数据库连接。"""
    db = getattr(g, "db", None)
    if db is not None:
        db.close()


# 注册 Blueprint 路由
from backend.routers import folders, documents, blocks, search, attachments  # noqa: E402

app.register_blueprint(folders.bp, url_prefix="/api/folders")
app.register_blueprint(documents.bp, url_prefix="/api/documents")
app.register_blueprint(blocks.bp, url_prefix="/api/blocks")
app.register_blueprint(search.bp, url_prefix="/api/search")
app.register_blueprint(attachments.bp, url_prefix="/api/attachments")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


# 前端静态文件（生产模式：构建产物由 Flask 直接提供）
if FRONTEND_DIST.exists():
    from flask import send_from_directory, make_response

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        full = FRONTEND_DIST / path
        if path and full.is_file():
            resp = make_response(send_from_directory(str(FRONTEND_DIST), path))
            # 带 hash 的静态资源可长期缓存
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp
        # index.html 不缓存，确保浏览器始终加载最新版本
        resp = make_response(send_from_directory(str(FRONTEND_DIST), "index.html"))
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp


# 启动时初始化数据库
init_db()
