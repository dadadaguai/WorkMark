"""启动入口：运行 Flask 服务。

开发模式：
  python run.py              → 后端 http://127.0.0.1:8000
  cd frontend && npm run dev → 前端 http://localhost:5173

生产模式（前端构建后）：
  cd frontend && npm run build
  python run.py              → http://127.0.0.1:8000 （前后端一体）
"""

from backend.main import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
