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
| 2026-10-10 | feature/auto-save | FR-06：防抖自动保存（输入即生效，停止 800ms 保存）、保存状态指示、基于内容补丁的撤销/重做（连续输入合并 + Ctrl+Z/Ctrl+Y）、路由切换/关闭页面自动保存、空文本块占位符、textarea 自动聚焦、后端 content JSON 规范化 | ✅ 已合并 |
| 2026-10-10 | feature/time-sorting | FR-04：时间轴排序切换（文档顺序/创建时间/工作开始时间）、按工作时段分组浏览、平铺/折叠视图切换、卡片类型化摘要+按需展开、工作开始/结束时间编辑（datetime-local）、后端时间字段允许显式清空 | ✅ 已合并 |
| 2026-10-10 | feature/search-context | FR-05：全文搜索 API（LIKE 多关键词 AND，文档名+块标题+内容）、搜索 UI（关键词高亮 mark、文档/块命中分组）、日期浏览（创建/工作开始日期，可与关键词组合）、块命中跳转定位高亮、编辑器停留位置记录（last_position）、首页"继续上次工作"入口 | ✅ 已合并 |

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
- [x] POST /api/blocks/reorder — 批量更新块父级与排序（拖拽排序）
- [x] POST /api/blocks/:id/copy — 完整复制块（顶层块含子块）
- [x] GET /api/search?q=&date= — 全文搜索（多关键词 AND + 日期过滤，可组合）
- [x] GET /api/search/last-work — 最近工作上下文（"继续上次工作"）

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
- [x] 时间轴视图（文档顺序 / 创建时间 / 工作开始时间）
- [x] 按工作时段浏览（按工作开始日期分组，最近日期在前，未设置时间单独一组）
- [x] 平铺 / 折叠视图切换（折叠模式支持单卡展开/收起 + 全部展开/收起）
- [x] 卡片摘要 + 按需展开（首块类型化摘要：文本/代码/命令/输出/待办/表格/图片）
- [x] 拖拽调整顺序（文档顺序视图下，同级 + 层级调整；排序视图仅展示顺序，禁用拖拽）
- [x] 工作开始/结束时间编辑 UI（datetime-local，防抖保存，支持清空）

### FR-05: 搜索与上下文恢复（P0）

- [x] FTS5 数据库层已就绪
- [x] 搜索 API 端点（LIKE 子串匹配，FTS5 trigram 因 3 字符下限不适合中文短词而弃用）
- [x] 搜索 UI + 结果定位到块（摘要命中片段 mark 高亮，点击跳转 ?block= 滚动定位+闪烁）
- [x] 日期浏览（date 输入，按创建/工作开始日期过滤）
- [x] 搜索 + 日期组合筛选（关键词与日期 AND 组合）
- [x] "继续上次工作"入口（最近更新文档 + last_position）
- [x] 自动恢复上次停留位置（路由离开时记录最后编辑块，进入文档时恢复定位）

### FR-06: 保存、撤销与重做（P0）

- [x] 手动保存（更新内容触发 PUT）
- [x] 自动保存（输入即生效，停止输入 800ms 后防抖保存）
- [x] 保存状态提示（有未保存更改 / 保存中… / 已保存 ✓ / 保存失败）
- [x] 撤销 / 重做（内容补丁栈，同块 1 秒内连续输入合并为一步；Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y，输入框内保留原生撤销）
- [x] 切换文档时自动保存（onBeforeRouteLeave flush）
- [x] 关闭页面时触发保存（beforeunload）

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
* docs: 更新开发日志（FR-05 完成状态）
* merge: FR-05 搜索与上下文恢复
| * feat(fr-05): 全文搜索/日期浏览/结果定位/继续上次工作
* docs: 更新开发日志（FR-04 完成状态）
* merge: FR-04 时间与排序（时间轴/分组/折叠/工作时间）
| * feat(fr-04): 时间轴排序/工作时段分组/折叠视图/工作时间编辑
* docs: 更新开发日志（FR-06 完成状态）
* merge: FR-06 自动保存 + 撤销/重做
| * feat(fr-06): 防抖自动保存/保存状态/撤销重做/内容JSON规范化
* docs: 更新开发日志（FR-03 完成状态）
* merge: FR-03 内容编辑器（多类型内容块）
* feat(fr-03): 内容编辑器 — 多类型内容块
* docs: 更新开发日志（FR-01/FR-02 完成状态）
* merge: FR-02 任务块复制/拖拽排序/模板复用
* feat(fr-02): 任务块复制/拖拽排序/内容块模板复用
* merge: FR-01 文件夹与文档管理（重命名/移动/删除确认）
* feat(fr-01): 文件夹与文档管理 — 重命名/移动/删除确认
* docs: 创建开发进度跟踪文档
* merge: frontend skeleton (Vue 3 + TypeScript + Vite)
* feat(frontend): Vue 3 + TypeScript + Vite 前端骨架
* merge: backend skeleton (Flask + SQLite)
* feat(backend): Flask + SQLite 后端骨架
* chore: init git repo with .gitignore
```

## 技术备注

- 因系统 asyncio (_overlapped) 损坏，后端从 FastAPI 切换为 Flask
- Python socket 模块受 WinSock 损坏影响，无法从 Python 发起 HTTP 请求（浏览器不受影响）
- 开发时 npm 需禁用代理：`npm config set proxy null; npm config set https-proxy null`
- 测试浏览器（CDP 自动化）限制：无法向 textarea 插入文本、blur/change 事件不触发、组合键不可用。E2E 测试用「设置 value + 派发 input 事件」模拟键入（与真实键盘在 v-model 层面等价），焦点/失焦用真实点击
- 浏览器 evaluate 异步限制：evaluate 工具不等待 Promise（async IIFE 返回 undefined）。需异步验证时，脚本内把结果写入 window 变量（如 window.__r），用第二次 evaluate 读取；按钮点击与轮询断言必须在同一次 evaluate 内完成，否则工具调度延迟会错过 2 秒级瞬态 UI（如高亮动画）
- browser_navigate 是整页刷新，不触发 Vue Router 的 onBeforeRouteLeave；测试路由离开钩子（如 last_position 保存）必须用页面内真实点击导航
- 内容块文本输入采用 @input 即时 emit（非 blur），保证失焦前关闭页面不丢内容
- last_position 仅在 SPA 路由离开（onBeforeRouteLeave）时写入；整页刷新/关闭场景内容已由防抖保存，仅停留位置不更新（可接受的取舍）
