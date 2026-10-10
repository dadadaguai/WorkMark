# WorkMark 开发进度跟踪

> 本文档跟踪 WorkMark 记录软件的开发进度，对照 PRD 功能需求逐条记录完成状态。

## 项目概况

| 项 | 值 |
|---|---|
| 产品 | WorkMark — 本地工作过程记录软件 |
| 技术栈 | Flask (Python) + SQLite + Vue 3 + TypeScript + Vite |
| PRD 版本 | V1.0 |
| Git 主分支 | master |
| 工作流 | feature/* 分支 → merge to master |

## 启动方式

```bash
# 生产模式（前后端一体）
cd frontend && npm run build
python run.py
# 访问 http://127.0.0.1:8000

# 开发模式（前后端分离热更新）
python run.py              # 后端 http://127.0.0.1:8000
cd frontend && npm run dev # 前端 http://localhost:5173
```

## 已完成

### 基础设施

| 日期 | 分支 | 内容 | 状态 |
|---|---|---|---|
| 2026-10-10 | feature/backend-skeleton | Flask + SQLite 后端骨架：database.py (schema + FTS5)、main.py (Flask app + CORS)、routers/ (folders + documents + blocks CRUD)、run.py 入口 | ✅ 已合并 |
| 2026-10-10 | feature/frontend-skeleton | Vue 3 + TypeScript + Vite + Pinia + Vue Router 前端骨架：HomeView (文件夹侧栏 + 文档列表 + 新建)、EditorView (任务块/子块 CRUD + 基础编辑)、useApi composable、类型定义 | ✅ 已合并 |
| 2026-10-10 | feature/folder-doc-mgmt | FR-01：文件夹/文档重命名（双击+按钮）、移动对话框、删除确认对话框（含影响范围统计）、ConfirmDialog 组件、v-focus 指令、静态资源缓存策略 | ✅ 已合并 |
| 2026-10-10 | feature/block-editing | FR-02：块完整复制（含子块）、POST /blocks/reorder 批量排序、HTML5 拖拽排序（同级+层级调整+落点提示）、内容块模板复用（localStorage） | ✅ 已合并 |
| 2026-10-10 | feature/content-editor | FR-03：ContentEditor 组件七类内容块（文本/代码/命令/输出/待办/表格/图片）、极简 Markdown 渲染、极简语法高亮（行号/折叠/复制）、终端专用样式、长内容折叠 | ✅ 已合并 |

### 数据库 Schema

- [x] folders 表（多层嵌套 + 默认文件夹）
- [x] documents 表（文件夹归属 + 位置恢复 last_position）
- [x] blocks 表（任务块/子块 + 父子关系 + JSON content + 时间字段）
- [x] attachments 表（文件管理 + 引用路径）
- [x] block_attachments 关联表
- [x] inbox_items 表（快速记录收件箱）
- [x] blocks_fts FTS5 全文搜索虚拟表 + 同步触发器

### API 端点

- [x] GET /api/health — 健康检查
- [x] GET /api/folders — 列出文件夹
- [x] POST /api/folders — 创建文件夹
- [x] PUT /api/folders/:id — 更新文件夹
- [x] DELETE /api/folders/:id — 删除文件夹（含影响统计）
- [x] GET /api/documents — 列出文档（可按 folder_id 筛选）
- [x] POST /api/documents — 创建文档（默认文件夹 + 自动命名）
- [x] GET /api/documents/:id — 获取文档
- [x] PUT /api/documents/:id — 更新文档（含 last_position）
- [x] DELETE /api/documents/:id — 删除文档（含块计数）
- [x] GET /api/blocks/document/:id — 列出文档内块
- [x] POST /api/blocks — 创建块/子块（含父子验证）
- [x] GET /api/blocks/:id — 获取块
- [x] PUT /api/blocks/:id — 更新块
- [x] DELETE /api/blocks/:id — 删除块（含子块计数）

### 前端页面

- [x] 首页 HomeView：文件夹侧栏、文档列表、新建文档/文件夹
- [x] 编辑器 EditorView：任务块/子块 CRUD、基础内容编辑、返回首页

## 开发中

无

## 待开发（按 PRD 功能需求）

### FR-01: 文件夹与任务文档管理（P0）

- [x] 创建、重命名、移动文件夹
- [x] 多层嵌套
- [x] 默认文件夹固定显示
- [x] 默认文件夹不可删除/重命名（后端已实现）
- [x] 删除非空文件夹时显示影响范围确认对话框
- [x] 文件夹/文档移动功能（前端菜单）
- [x] 重命名 UI（前端）

### FR-02: 任务块与子块编辑（P0）

- [x] 新增任务块
- [x] 追加子块
- [x] 编辑块标题
- [x] 删除块（含确认）
- [x] 复制任务块
- [x] 完整复制（不复制父子关系）
- [x] 内容块模板复用（localStorage 本地实现）
- [x] 拖拽排序（同级 + 父子层级调整）
- [x] 拖拽落点提示

### FR-03: 内容编辑器（P0）

- [x] 编辑⇄预览双态 + Markdown 兼容（极简渲染器，非实时 WYSIWYG）
- [x] 代码块（等宽字体、语法高亮、行号、折叠、一键复制）
- [x] Shell 命令 / 终端输出专用样式
- [x] 图片插入与预览放大（dataURL ≤2MB，后续迁移附件系统）
- [x] 待办清单
- [x] 表格
- [x] 原文保真：粘贴保留换行缩进、复制不含行号
- [x] 长内容折叠/展开

### FR-04: 时间与排序（P0）

- [x] 数据库时间字段（created_at、updated_at、work_start_time、work_end_time）
- [ ] 时间轴视图（文档顺序 / 创建时间 / 工作开始时间）
- [ ] 按工作时段浏览
- [ ] 平铺 / 折叠视图切换
- [ ] 卡片摘要 + 按需展开
- [ ] 拖拽调整顺序
- [ ] 工作开始/结束时间编辑 UI

### FR-05: 搜索与上下文恢复（P0）

- [x] FTS5 数据库层已就绪
- [ ] 搜索 API 端点
- [ ] 搜索 UI + 结果定位到块
- [ ] 日期浏览
- [ ] 搜索 + 时间轴 + 筛选器联动
- [ ] "继续上次工作"入口
- [ ] 自动恢复上次停留位置（last_position 字段已建）

### FR-06: 保存、撤销与重做（P0）

- [x] 手动保存（更新内容触发 PUT）
- [ ] 自动保存（停止输入后防抖保存）
- [ ] 保存状态提示（保存中 / 已保存 / 保存失败）
- [ ] 撤销 / 重做
- [ ] 切换文档时自动保存
- [ ] 关闭页面时触发保存

### FR-07: 附件管理（P0）

- [ ] 附件上传 API（复制到本地目录）
- [ ] 引用原始路径选项
- [ ] 附件管理页面
- [ ] 附件搜索
- [ ] 删除时引用检查
- [ ] 图片插入内容块

### FR-08: 删除规则与级联（P0）

- [x] 后层级联删除（SQLite ON DELETE CASCADE）
- [x] 默认文件夹不可删除
- [ ] 删除确认对话框（前端）
- [ ] 影响范围展示
- [ ] 删除父块时选择子块是否一并删除

### FR-09: 快速记录 / 收件箱（P0）

- [ ] 收件箱 API
- [ ] 收件箱页面
- [ ] 移动到文档
- [ ] 复制到文档
- [ ] 关联文档但保留原记录
- [ ] 合并到已有任务块（P1 可裁剪）

## 后续版本（不纳入 MVP）

- [ ] Markdown / PDF / HTML 导出
- [ ] 全局快捷键
- [ ] 备份 / 快照 / 恢复中心 / 回收站
- [ ] Git 集成
- [ ] 云同步 / 多人协作
- [ ] 公式编辑
- [ ] 全局待办汇总
- [ ] 手动断点标记

## Git 提交历史

```
* merge: frontend skeleton (Vue 3 + TypeScript + Vite)
| * feat(frontend): Vue 3 + TypeScript + Vite 前端骨架
* merge: backend skeleton (Flask + SQLite)
| * feat(backend): Flask + SQLite 后端骨架
* chore: init git repo with .gitignore
```

## 技术备注

- 因系统 asyncio (_overlapped) 损坏，后端从 FastAPI 切换为 Flask
- Python socket 模块受 WinSock 损坏影响，无法从 Python 发起 HTTP 请求（浏览器不受影响）
- 开发时 npm 需禁用代理：`npm config set proxy null; npm config set https-proxy null`
