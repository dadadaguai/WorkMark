<script setup lang="ts">
/** 正文流编辑器（飞书式单文本流，每行 = 一个任务段）。
 * 回车 = 正文换行；Ctrl+Enter 或连续两个空行 = 分出新任务；
 * 内容块（代码/表格/图片等）自动断开任务：块上正文一个任务，块下另起一个；
 * Tab / Shift+Tab = 任务段级缩进/提升；斜杠命令 / ``` 在光标处插入内容块。
 */
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute, onBeforeRouteLeave } from 'vue-router'
import { api } from '@/composables/useApi'
import ContentEditor from '@/components/ContentEditor.vue'
import SlashMenu from '@/components/SlashMenu.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import PromptDialog from '@/components/PromptDialog.vue'
import { useDialogFocus } from '@/composables/useDialogFocus'
import type { Document, Block, ContentBlock, SlashItem } from '@/types'

const props = defineProps<{ id: string }>()
const router = useRouter()
const route = useRoute()

const doc = ref<Document | null>(null)
const blocks = ref<Block[]>([])

// ── 内容块模板（localStorage 持久化，前端本地实现）──
const TEMPLATE_KEY = 'workmark_block_templates'
interface BlockTemplate { name: string; content: string }
const templates = ref<BlockTemplate[]>(loadTemplates())

function loadTemplates(): BlockTemplate[] {
  try {
    return JSON.parse(localStorage.getItem(TEMPLATE_KEY) || '[]')
  } catch {
    return []
  }
}

function persistTemplates() {
  localStorage.setItem(TEMPLATE_KEY, JSON.stringify(templates.value))
}

function saveTemplate(block: Block, name: string) {
  // text 行把正文包成 text 项存模板；content 行直接存单块 JSON
  const content = isTextRow(block)
    ? JSON.stringify([{ type: 'text', content: block.title ?? '' }])
    : block.content
  templates.value.push({ name, content })
  persistTemplates()
}

// 保存为模板：统一用 PromptDialog 输入名称（替代原生 prompt）
const templateTarget = ref<Block | null>(null)

function requestSaveTemplate(block: Block) {
  templateTarget.value = block
}

function confirmSaveTemplate(name: string) {
  const block = templateTarget.value
  templateTarget.value = null
  const n = name.trim()
  if (!n || !block) return
  saveTemplate(block, n)
}

// ── 数据加载（空文档自动创建首块，进入即可输入）──
onMounted(async () => {
  doc.value = await api.get<Document>(`/documents/${props.id}`)
  blocks.value = await api.get<Block[]>(`/blocks/document/${props.id}`)
  if (blocks.value.length === 0) {
    const b = await api.post<Block>('/blocks', { document_id: Number(props.id), title: '', content: '[]' })
    blocks.value.push(b)
  }
  // 恢复停留位置：URL ?block= 优先，其次文档 last_position
  const fromQuery = Number(route.query.block) || 0
  const target = fromQuery || parseLastPosition(doc.value.last_position)
  if (target && blocks.value.some(b => b.id === target)) focusBlock(target)
  else if (blocks.value.length) focusRow(blocks.value[0].id, 'end')
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('beforeunload', onBeforeUnload)
  window.addEventListener('mousedown', onDocMouseDown, true)
  window.addEventListener('scroll', onWinScroll, true)
  window.addEventListener('resize', onWinScroll)
})

/** 解析 last_position JSON（容错），返回 block_id 或 0。 */
function parseLastPosition(raw: string | null): number {
  if (!raw) return 0
  try {
    const pos = JSON.parse(raw)
    return Number(pos?.block_id) || 0
  } catch {
    return 0
  }
}

/** 滚动定位到指定块并短暂高亮。 */
function focusBlock(blockId: number) {
  sortMode.value = 'doc'
  collapsedView.value = false
  nextTick(() => {
    const el = document.querySelector(`[data-block-id="${blockId}"]`)
    if (el) {
      el.scrollIntoView({ block: 'center' })
      el.classList.add('block-highlight')
      window.setTimeout(() => el.classList.remove('block-highlight'), 2000)
    }
  })
}

async function reloadBlocks() {
  await awaitPendingCreates()
  const list = await api.get<Block[]>(`/blocks/document/${props.id}`)
  // 合并未落盘的本地编辑（防抖窗口内的输入，含临时负 id 键），防止整表刷新吞字
  for (const [key, pu] of pendingUpdates) {
    const target = list.find(b => b.id === realIdOf(key))
    if (target) Object.assign(target, pu)
  }
  // 保留未同步（创建失败）的本地临时行，避免刷新后丢失用户输入
  for (const tb of blocks.value) {
    if (tb.id < 0 && failedCreates.value.has(tb.id) && !list.some(b => b.id === tb.id)) {
      list.push(tb)
    }
  }
  blocks.value = list
}

// ── 乐观块创建（飞书式）：本地立即成行并聚焦，后台落库 ──
// 临时块用负数 id 且永不改动（充当稳定 Vue key，行不重挂载、焦点不丢），tempToReal 提供真实 id 映射。
let tempIdSeq = -1
const pendingCreates = new Map<number, Promise<void>>() // tempId -> 落库完成信号
const tempToReal = new Map<number, number>()
const failedCreates = ref(new Set<number>()) // 创建失败但保留本地内容的临时块 id

/** 结构/删除/复制/拖拽等操作前调用：等所有临时块落库完成，保证拿到真实 id。 */
async function awaitPendingCreates() {
  while (pendingCreates.size) await Promise.all([...pendingCreates.values()])
}

/** 若块是尚未落库的临时块，等待其落库完成。 */
async function ensureBlockPersisted(block: Block) {
  const p = pendingCreates.get(block.id)
  if (p) await p
}

/** 本地 id → 服务端真实 id（非临时块原样返回）。 */
function realIdOf(id: number): number {
  return tempToReal.get(id) ?? id
}

/** 本地立即创建块并返回（零延迟可输入/聚焦）；后台 POST 落库，失败移除本地行。 */
function createBlockOptimistic(after: Block | null, parentId: number | null, title: string, content = '[]'): Block {
  const tempId = tempIdSeq--
  const temp: Block = {
    id: tempId,
    document_id: Number(props.id),
    parent_id: parentId,
    title,
    content,
    sort_order: after ? after.sort_order + 0.5 : Number.MAX_SAFE_INTEGER / 2,
    work_start_time: null,
    work_end_time: null,
    created_at: new Date().toISOString().slice(0, 19),
    updated_at: '',
  }
  blocks.value.push(temp)
  const p = (async () => {
    try {
      // after 可能是尚未落库的临时块（如连续插入内容块 + 续写行），先等其落库拿到真实 id，否则后端会因 after_id 不存在而拒绝创建
      if (after) await ensureBlockPersisted(after)
      const nb = await api.post<Block>('/blocks', {
        document_id: Number(props.id),
        parent_id: parentId,
        after_id: after ? realIdOf(after.id) : undefined,
        title,
        content,
      })
      tempToReal.set(tempId, nb.id)
      temp.sort_order = nb.sort_order // 仅同步排序；id 保持本地键，避免整行重挂载
    } catch (err) {
      // 创建失败：保留本地行及用户已输入内容，标记未同步，提供重试 / 复制
      console.warn('块创建失败，保留本地内容待重试', err)
      failedCreates.value.add(tempId)
    } finally {
      pendingCreates.delete(tempId)
    }
  })()
  pendingCreates.set(tempId, p)
  return temp
}

/** 未同步块：用最新本地内容重新落库，成功后把 pendingUpdates 映射到真实 id 继续保存。 */
async function retryCreate(tempId: number) {
  const block = blocks.value.find(b => b.id === tempId)
  if (!block) return
  const pu = pendingUpdates.get(tempId) || {}
  const title = pu.title ?? block.title
  const content = pu.content ?? block.content
  try {
    const nb = await api.post<Block>('/blocks', {
      document_id: Number(props.id),
      parent_id: block.parent_id ? realIdOf(block.parent_id) : null,
      title,
      content,
    })
    tempToReal.set(tempId, nb.id)
    block.sort_order = nb.sort_order
    failedCreates.value.delete(tempId)
    if (pendingUpdates.has(tempId)) {
      const data = pendingUpdates.get(tempId)!
      pendingUpdates.delete(tempId)
      pendingUpdates.set(nb.id, data)
    }
    await flushSaves()
  } catch {
    // 保持未同步状态，等待下次重试
  }
}

/** 复制未同步块正文到剪贴板（兜底，避免用户输入丢失）。 */
async function copyUnsynced(tempId: number) {
  const block = blocks.value.find(b => b.id === tempId)
  const text = (block?.title ?? '').trim()
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
}

// ── 时间轴：排序模式 + 平铺/折叠视图 + 工作时段分组（FR-04）──
type SortMode = 'doc' | 'created' | 'work_start' | 'work_period'
const sortMode = ref<SortMode>('doc')
const collapsedView = ref(false)
const expandedIds = ref(new Set<number>())
const SORT_OPTIONS = [
  { value: 'doc', label: '文档顺序' },
  { value: 'created', label: '创建时间' },
  { value: 'work_start', label: '工作开始' },
  { value: 'work_period', label: '工作时段' },
] as const

watch([sortMode, collapsedView], () => { expandedIds.value = new Set() })

function isExpanded(blockId: number): boolean {
  return !collapsedView.value || expandedIds.value.has(blockId)
}

function toggleExpand(blockId: number) {
  const s = new Set(expandedIds.value)
  if (s.has(blockId)) s.delete(blockId)
  else s.add(blockId)
  expandedIds.value = s
}

function expandAll() { expandedIds.value = new Set(blocks.value.map(b => b.id)) }
function collapseAll() { expandedIds.value = new Set() }

/** 排序比较器：只影响展示顺序，不改动 sort_order（文档原始顺序）。 */
function cmpBlocks(a: Block, b: Block): number {
  if (sortMode.value === 'created') {
    return a.created_at.localeCompare(b.created_at) || a.id - b.id
  }
  if (sortMode.value === 'work_start') {
    const ka = a.work_start_time ?? '9999-12-31'
    const kb = b.work_start_time ?? '9999-12-31'
    return ka.localeCompare(kb) || a.created_at.localeCompare(b.created_at) || a.id - b.id
  }
  return a.sort_order - b.sort_order || a.id - b.id
}

/** 文档原始顺序（结构操作 Enter/Tab/拖拽始终按此语义执行）。 */
function byOrder(a: Block, b: Block): number {
  return a.sort_order - b.sort_order || a.id - b.id
}

const topLevelBlocks = computed(() =>
  blocks.value.filter(b => b.parent_id === null).sort(cmpBlocks),
)

function childrenOf(parentId: number): Block[] {
  return blocks.value.filter(b => b.parent_id === parentId).sort(cmpBlocks)
}

/** 按工作时段分组：以工作开始日期分组（最近的日期在前），未设置时间的块单独一组。 */
interface WorkGroup { label: string; blocks: Block[] }
const workGroups = computed<WorkGroup[]>(() => {
  const withTime = blocks.value
    .filter(b => b.parent_id === null && b.work_start_time)
    .sort((a, b) => (a.work_start_time! < b.work_start_time! ? 1 : a.work_start_time! > b.work_start_time! ? -1 : a.id - b.id))
  const map = new Map<string, Block[]>()
  for (const b of withTime) {
    const day = b.work_start_time!.slice(0, 10)
    if (!map.has(day)) map.set(day, [])
    map.get(day)!.push(b)
  }
  const groups: WorkGroup[] = [...map.entries()].map(([label, list]) => ({ label, blocks: list }))
  const noTime = blocks.value.filter(b => b.parent_id === null && !b.work_start_time)
  if (noTime.length) groups.push({ label: '未设置工作时段', blocks: noTime })
  return groups
})

/** 渲染数据源：工作时段模式按分组渲染，其余为单组列表。 */
const displayGroups = computed<WorkGroup[]>(() => {
  if (sortMode.value === 'work_period') return workGroups.value
  return [{ label: '', blocks: topLevelBlocks.value }]
})

// ── 扁平化行模型（文档流渲染）──
type FlatRow =
  | { kind: 'group'; label: string; count: number }
  | { kind: 'block'; block: Block; depth: 0 | 1; index: number }
type BlockRow = Extract<FlatRow, { kind: 'block' }>

const flatRows = computed<FlatRow[]>(() => {
  const rows: FlatRow[] = []
  let i = 0
  for (const g of displayGroups.value) {
    if (g.label) rows.push({ kind: 'group', label: g.label, count: g.blocks.length })
    for (const top of g.blocks) {
      rows.push({ kind: 'block', block: top, depth: 0, index: i++ })
      if (isExpanded(top.id)) {
        for (const c of childrenOf(top.id)) rows.push({ kind: 'block', block: c, depth: 1, index: i++ })
      }
    }
  }
  return rows
})

/** 在 flatRows 中找当前行的前/后一个任务行 id（跳过分组标题行）。 */
function neighborRowId(blockId: number, dir: -1 | 1): number | null {
  const rows = flatRows.value
  const idx = rows.findIndex(r => r.kind === 'block' && r.block.id === blockId)
  if (idx === -1) return null
  for (let j = idx + dir; j >= 0 && j < rows.length; j += dir) {
    const r = rows[j]
    if (r.kind === 'block') return r.block.id
  }
  return null
}

function hasContent(block: Block): boolean {
  return block.content !== '[]' && block.content !== ''
}

/** text 行 = 无内容块（title 存多行正文）；content 行 = 单个内容块。 */
function isTextRow(block: Block): boolean {
  return !hasContent(block)
}

/** 取 content 行的唯一内容块（text 行返回 null）。 */
function contentItemOf(block: Block): ContentBlock | null {
  try {
    const arr = JSON.parse(block.content) as ContentBlock[]
    return Array.isArray(arr) && arr[0] ? arr[0] : null
  } catch {
    return null
  }
}

/** 摘要：text 行取正文首行，content 行取块类型化描述。 */
function summarize(block: Block): string {
  if (isTextRow(block)) {
    const t = (block.title ?? '').trim()
    return t ? t.split('\n')[0].slice(0, 60) : '（空）'
  }
  const first = contentItemOf(block)
  if (!first) return '（空）'
  switch (first.type) {
    case 'code': return `代码${first.language ? ' · ' + first.language : ''} · ${(first.content || '').split('\n').length} 行`
    case 'shell': return `命令 · ${(first.content || '').slice(0, 50)}`
    case 'output': return `输出 · ${(first.content || '').split('\n').length} 行`
    case 'todo': {
      const total = first.items?.length ?? 0
      const done = first.items?.filter(i => i.done).length ?? 0
      return `待办 ${total} 项（完成 ${done}）`
    }
    case 'table': return `表格 ${first.rows?.length ?? 0} 行`
    case 'image': return '[图片]'
    default: return '（未知类型）'
  }
}

/** 时间显示与 datetime-local 输入值互转。 */
function formatDateTime(s: string | null): string {
  return s ? s.replace('T', ' ').slice(0, 16) : ''
}

function toLocalInput(s: string | null): string {
  return s ? s.replace(' ', 'T').slice(0, 16) : ''
}

/** 时间 chip：设了工作时段优先显示，否则显示创建时间。 */
function timeChip(block: Block): { text: string; cls: string; tip: string } {
  if (block.work_start_time) {
    const s = block.work_start_time.slice(5, 16).replace('T', ' ')
    const e = block.work_end_time ? ' ~ ' + block.work_end_time.slice(11, 16) : ' ~'
    return {
      text: s + e, cls: 'chip-work',
      tip: `工作 ${formatDateTime(block.work_start_time)} → ${formatDateTime(block.work_end_time) || '进行中'}`,
    }
  }
  return { text: block.created_at.slice(5, 16), cls: 'chip-created', tip: '创建于 ' + formatDateTime(block.created_at) + '，点击设置工作时段' }
}

// ── 自动保存（防抖）+ 保存状态 + 撤销/重做（title/content 双字段）──
type SaveState = 'idle' | 'pending' | 'saving' | 'saved' | 'error'
const saveState = ref<SaveState>('idle')
const SAVE_DELAY = 800
let saveTimer: number | null = null
const pendingUpdates = new Map<number, { title?: string; content?: string; work_start_time?: string | null; work_end_time?: string | null }>()
const docPending = ref<{ name: string } | null>(null) // 文档标题待保存内容

const saveStateText = computed(() => ({
  idle: '', pending: '有未保存更改', saving: '保存中…', saved: '已保存 ✓', error: '保存失败',
}[saveState.value]))

function setSaveState(s: SaveState) { saveState.value = s }

function scheduleFlush() {
  // 进入待保存态（失败态保留，直到用户重试或继续输入）
  if (saveState.value !== 'error') setSaveState('pending')
  if (saveTimer !== null) clearTimeout(saveTimer)
  saveTimer = window.setTimeout(flushSaves, SAVE_DELAY)
}

// 单一串行保存循环：避免保存顺序交错，失败时不投弃队列、不覆盖用户新输入
let saveBusy = false
let rerunRequested = false
let saveWaiters: (() => void)[] = []

/** 是否存在尚未落库的本地内容（块更新 / 文档标题 / 创建中 / 创建失败）。 */
function hasUnsavedChanges(): boolean {
  return pendingUpdates.size > 0 || docPending.value !== null || pendingCreates.size > 0 || failedCreates.value.size > 0
}

async function flushSaves(): Promise<void> {
  if (saveTimer !== null) { clearTimeout(saveTimer); saveTimer = null }
  if (saveBusy) {
    // 保存进行中：置重新执行标记，等待本轮循环（含重跑）真正结束才返回
    rerunRequested = true
    return new Promise<void>(resolve => saveWaiters.push(resolve))
  }
  saveBusy = true
  let didSave = false
  let failed = false
  try {
    do {
      rerunRequested = false
      await awaitPendingCreates() // 临时块先落库，映射出真实 id 再 PUT

      // 文档标题纳入统一保存流程（此前单独防抖、失败静默忽略）
      if (docPending.value) {
        setSaveState('saving')
        const name = docPending.value.name
        try {
          await api.put(`/documents/${props.id}`, { name })
          if (docPending.value && docPending.value.name === name) docPending.value = null
          didSave = true
        } catch { failed = true }
      }

      if (pendingUpdates.size > 0) {
        setSaveState('saving')
        const snapshot = [...pendingUpdates.entries()]
        for (const [id, data] of snapshot) {
          if (failedCreates.value.has(id)) continue // 待创建重试，交由 retryCreate 处理
          try {
            await api.put(`/blocks/${realIdOf(id)}`, data)
            // 仅当队列里仍是这份快照时才移除；保存期间的新输入保留，下一轮再存
            const cur = pendingUpdates.get(id)
            if (cur && JSON.stringify(cur) === JSON.stringify(data)) pendingUpdates.delete(id)
            didSave = true
          } catch { failed = true }
        }
      }
      if (failed) break

      // 队列里若只剩创建失败的块（无法通过 PUT 保存），退出循环等待 retryCreate，避免死循环
      const savable = [...pendingUpdates.keys()].some(id => !failedCreates.value.has(id))
      if (!savable && !docPending.value) break
    } while (rerunRequested || pendingUpdates.size > 0 || docPending.value)

    if (failed) setSaveState('error')
    else if (failedCreates.value.size > 0) setSaveState('error')
    else if (docPending.value || pendingUpdates.size > 0) setSaveState('pending')
    else if (didSave) setSaveState('saved')
  } finally {
    saveBusy = false
    const ws = saveWaiters
    saveWaiters = []
    ws.forEach(r => r())
  }
}

interface UndoPatch { blockId: number; field: 'title' | 'content'; before: string; after: string }
const undoStack = ref<UndoPatch[]>([])
const redoStack = ref<UndoPatch[]>([])
const UNDO_LIMIT = 100
const UNDO_COALESCE_MS = 1000
let lastPatch: (UndoPatch & { at: number }) | null = null

function recordBlockChange(blockId: number, field: 'title' | 'content', before: string, after: string) {
  if (before === after) return
  const now = Date.now()
  if (lastPatch && lastPatch.blockId === blockId && lastPatch.field === field && now - lastPatch.at < UNDO_COALESCE_MS) {
    // 同一块同一字段的连续输入：合并为单个撤销步骤
    lastPatch.after = after
    lastPatch.at = now
  } else {
    const patch: UndoPatch & { at: number } = { blockId, field, before, after, at: now }
    undoStack.value.push(patch)
    lastPatch = patch
    if (undoStack.value.length > UNDO_LIMIT) undoStack.value.shift()
  }
  redoStack.value = []
}

function applyTitle(blockId: number, title: string) {
  const block = blocks.value.find(b => b.id === blockId)
  if (!block) return
  block.title = title
  lastEditedBlockId.value = blockId
  pendingUpdates.set(blockId, { ...(pendingUpdates.get(blockId) || {}), title })
  scheduleFlush()
}

function applyContent(blockId: number, content: string) {
  const block = blocks.value.find(b => b.id === blockId)
  if (!block) return
  block.content = content
  pendingUpdates.set(blockId, { ...(pendingUpdates.get(blockId) || {}), content })
  scheduleFlush()
}

function applyField(blockId: number, field: 'title' | 'content', value: string) {
  if (field === 'title') applyTitle(blockId, value)
  else applyContent(blockId, value)
}

function undo() {
  const p = undoStack.value.pop()
  lastPatch = null
  if (!p) return
  applyField(p.blockId, p.field, p.before)
  redoStack.value.push({ blockId: p.blockId, field: p.field, before: p.before, after: p.after })
}

function redo() {
  const p = redoStack.value.pop()
  lastPatch = null
  if (!p) return
  applyField(p.blockId, p.field, p.after)
  undoStack.value.push({ blockId: p.blockId, field: p.field, before: p.before, after: p.after })
}

// 全局快捷键：仅在非输入焦点时接管（输入框内由 onRowKeydown 接管）
function onKeydown(e: KeyboardEvent) {
  if (!e.ctrlKey) return
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  const key = e.key.toLowerCase()
  if (key === 'z' && !e.shiftKey) { e.preventDefault(); undo() }
  else if ((key === 'z' && e.shiftKey) || key === 'y') { e.preventDefault(); redo() }
}

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (hasUnsavedChanges()) {
    flushSaves()
    e.preventDefault()
    e.returnValue = ''
  }
}

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('mousedown', onDocMouseDown, true)
  window.removeEventListener('scroll', onWinScroll, true)
  window.removeEventListener('resize', onWinScroll)
  flushSaves()
})

// 切换文档（路由离开）前：flush 保存 + 未保存守卫 + 记录停留位置（last_position）
const lastEditedBlockId = ref<number | null>(null)
const leaveGuard = ref<null | { resolve: (c: 'retry' | 'stay' | 'discard') => void }>(null)
const leaveGuardRoot = ref<HTMLElement | null>(null)
const leaveStayBtn = ref<HTMLButtonElement | null>(null)
const { focusInitial: focusLeaveGuard } = useDialogFocus(leaveGuardRoot, () => answerLeave('stay'))

function askLeave(): Promise<'retry' | 'stay' | 'discard'> {
  return new Promise(resolve => {
    leaveGuard.value = { resolve }
    // 未保存守卫：默认聚焦「留在页面」这一安全选项
    focusLeaveGuard(els => els.find(el => el === leaveStayBtn.value) ?? els[0])
  })
}

function answerLeave(c: 'retry' | 'stay' | 'discard') {
  leaveGuard.value?.resolve(c)
  leaveGuard.value = null
}

onBeforeRouteLeave(async () => {
  await flushSaves()
  // 仍有未保存内容（失败未落库 / 创建失败）→ 提供 重试 / 留在页面 / 放弃 选择，而非静默丢数据
  while (hasUnsavedChanges()) {
    const choice = await askLeave()
    if (choice === 'discard') break
    if (choice === 'stay') return false
    // retry：既重试普通保存，也重试创建失败的临时块
    await Promise.all([...failedCreates.value].map(id => retryCreate(id)))
    await flushSaves()
  }
  if (lastEditedBlockId.value !== null) {
    try {
      await api.put(`/documents/${props.id}`, {
        // 停留位置保存真实块 id（临时负 id 无法匹配数据库中真实记录）
        last_position: JSON.stringify({ block_id: realIdOf(lastEditedBlockId.value) }),
      })
    } catch {
      // last_position 保存失败不阻塞导航
    }
  }
})

/** 更新工作开始/结束时间（传空值即清空，走同一防抖队列）。 */
function updateBlockTime(block: Block, field: 'work_start_time' | 'work_end_time', value: string) {
  const v = value || null
  block[field] = v
  lastEditedBlockId.value = block.id
  pendingUpdates.set(block.id, { ...(pendingUpdates.get(block.id) || {}), [field]: v })
  scheduleFlush()
}

function updateBlockContent(block: Block, content: string) {
  recordBlockChange(block.id, 'content', block.content, content)
  applyContent(block.id, content)
  lastEditedBlockId.value = block.id
}

/** 在 block 之后按序插入任务段行：非 text 项 → content 行；text 项（非空）→ text 行；
 * tail 作为最后一个 text 行（空 tail 也建行，作为内容块后的续写任务），返回该行供聚焦。 */
async function insertRowsAfter(block: Block, items: ContentBlock[], tail: string): Promise<Block> {
  await ensureBlockPersisted(block)
  let after = block
  const parentId = block.parent_id
  for (const it of items) {
    if (it.type === 'text') {
      const c = (it.content || '').replace(/^\n+|\n+$/g, '')
      if (!c.trim()) continue // 空 text 项（模板占位）跳过
      after = createBlockOptimistic(after, parentId, c)
    } else {
      after = createBlockOptimistic(after, parentId, '', JSON.stringify([it]))
    }
  }
  return createBlockOptimistic(after, parentId, tail)
}

function makeDefaultContent(type: ContentBlock['type']): ContentBlock {
  const base: ContentBlock = { type }
  if (type === 'text' || type === 'shell' || type === 'output' || type === 'image') base.content = ''
  if (type === 'code') { base.content = ''; base.language = 'python' }
  if (type === 'todo') base.items = [{ text: '', done: false }]
  if (type === 'table') base.rows = [['列1', '列2'], ['', '']]
  return base
}

// ── 文档标题（正文顶部可编辑大标题）──
const docTitleEl = ref<HTMLTextAreaElement | null>(null)

function onDocTitleInput(e: Event) {
  const ta = e.target as HTMLTextAreaElement
  autoResize(ta)
  if (!doc.value) return
  doc.value.name = ta.value
  docPending.value = { name: ta.value }
  scheduleFlush()
}

// ── textarea 自动增高（field-sizing 兜底）──
function autoResize(el: HTMLTextAreaElement | null | undefined) {
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

watch(flatRows, () => {
  nextTick(() => {
    document.querySelectorAll<HTMLTextAreaElement>('textarea.row-input').forEach(autoResize)
  })
})

// ── 焦点管理 ──
function focusRow(blockId: number, pos: 'start' | 'end' | number = 'end') {
  nextTick(() => {
    // text 行聚焦正文 textarea；content 行聚焦块内第一个可编辑元素
    const el = document.querySelector<HTMLTextAreaElement>(
      `[data-block-id="${blockId}"] textarea.row-input, [data-block-id="${blockId}"] .row-rich textarea, [data-block-id="${blockId}"] .row-rich input`,
    )
    if (!el) return // 行被折叠隐藏时静默跳过
    el.focus()
    if (el instanceof HTMLTextAreaElement) {
      const end = el.value.length
      const idx = pos === 'start' ? 0 : pos === 'end' ? end : Math.min(pos as number, end)
      el.setSelectionRange(idx, idx)
      autoResize(el)
    }
  })
}

// ── 行输入：标题更新 + 斜杠菜单触发 + ``` 检测 ──
const slashMenu = ref<{ blockId: number; slashPos: number; pos: number; anchor: DOMRect } | null>(null)
const slashHi = ref(0)

function closeSlash() { slashMenu.value = null }

const slashItems = computed<SlashItem[]>(() => {
  const base: SlashItem[] = [
    { key: 'text', label: '文本', desc: '正文段落，支持 Markdown', icon: '¶', type: 'text' },
    { key: 'code', label: '代码', desc: '带高亮的代码块', icon: '{}', type: 'code' },
    { key: 'shell', label: '命令', desc: '终端命令', icon: '>_', type: 'shell' },
    { key: 'output', label: '输出', desc: '粘贴终端输出', icon: '≣', type: 'output' },
    { key: 'todo', label: '待办', desc: '可勾选清单', icon: '☑', type: 'todo' },
    { key: 'table', label: '表格', desc: '简单表格', icon: '▦', type: 'table' },
    { key: 'image', label: '图片', desc: '上传图片', icon: '🖼', type: 'image' },
  ]
  templates.value.forEach((t, i) =>
    base.push({ key: 'tpl-' + i, label: t.name, desc: '插入模板内容', icon: '▤', tplIndex: i }),
  )
  // 按 '/' 后输入的文字过滤（查询词到空白为止——中间插入时后文不粘在命令上；
  // 匹配 key / label / desc，不区分大小写），回车即选中匹配项
  const m = slashMenu.value
  if (m) {
    const block = blocks.value.find(b => b.id === m.blockId)
    const query = ((block?.title ?? '').slice(m.slashPos + 1).match(/^\S+/)?.[0] ?? '').toLowerCase()
    if (query) {
      return base.filter(it =>
        it.key.toLowerCase().includes(query) ||
        it.label.toLowerCase().includes(query) ||
        (it.desc ?? '').toLowerCase().includes(query))
    }
  }
  return base
})

// 过滤后列表变短时，高亮索引回落在有效范围内
watch(slashItems, list => {
  if (slashHi.value >= list.length) slashHi.value = Math.max(0, list.length - 1)
})

function onRowInput(row: BlockRow, e: Event) {
  const ta = e.target as HTMLTextAreaElement
  const block = row.block
  const now = ta.value
  const pos = ta.selectionStart ?? 0

  recordBlockChange(block.id, 'title', block.title ?? '', now)
  applyTitle(block.id, now)
  autoResize(ta)

  // 正文中间敲 ``` → 就地插入代码块：``` 前正文留当前行，后文归块下新任务
  if (now.slice(0, pos).endsWith('```')) {
    const head = now.slice(0, pos - 3)
    const tail = now.slice(pos)
    recordBlockChange(block.id, 'title', now, head)
    applyTitle(block.id, head)
    closeSlash()
    void insertRowsAfter(block, [{ type: 'code', content: '', language: 'python' }], tail)
      .then(nb => focusRow(nb.id, 'start'))
    return
  }

  // 连续两个空行 → 分出新任务：空行前正文留当前行，后文移入新行
  const gap = /\n[ \t]*\n[ \t]*\n/.exec(now)
  if (gap) {
    const head = now.slice(0, gap.index)
    const tail = now.slice(gap.index + gap[0].length)
    if (head.trim() || tail.trim()) {
      recordBlockChange(block.id, 'title', now, head)
      applyTitle(block.id, head)
      closeSlash()
      void (async () => {
        await ensureBlockPersisted(block)
        if (!blocks.value.some(b => b.id === block.id)) return
        const nb = createBlockOptimistic(block, block.parent_id, tail)
        focusRow(nb.id, 'start')
      })()
      return
    }
  }

  // 斜杠菜单打开中：光标退回 slashPos 之前或 '/' 被删 → 关闭；否则记录光标（选中时消费 '/命令' 到此处）
  if (slashMenu.value && slashMenu.value.blockId === block.id) {
    if (pos <= slashMenu.value.slashPos || now[slashMenu.value.slashPos] !== '/') closeSlash()
    else slashMenu.value.pos = pos
  }
  // 触发斜杠菜单：行首或空白后输入 '/'
  if (!slashMenu.value || slashMenu.value.blockId !== block.id) {
    const prev = now[pos - 1]
    if (prev === '/' && (pos === 1 || /\s/.test(now[pos - 2] ?? ' '))) {
      slashMenu.value = { blockId: block.id, slashPos: pos - 1, pos, anchor: ta.getBoundingClientRect() }
      slashHi.value = 0
    }
  }
}

function onSlashSelect(item: SlashItem) {
  const m = slashMenu.value
  if (!m) return
  closeSlash()
  const block = blocks.value.find(b => b.id === m.blockId)
  if (!block) return
  const text = block.title ?? ''
  // 消费 '/查询词'（查询词到空白为止；光标提前则只消费到光标），后文完整保留
  const q = text.slice(m.slashPos + 1).match(/^\S+/)?.[0] ?? ''
  const cutEnd = Math.min(m.pos, m.slashPos + 1 + q.length)
  const head = text.slice(0, m.slashPos) // '/' 前正文：留在当前任务行
  const tail = text.slice(cutEnd)        // 命令后正文：移到插入块下方新任务行
  const inserted: ContentBlock[] = item.tplIndex !== undefined
    ? (() => { try { return JSON.parse(templates.value[item.tplIndex!].content) as ContentBlock[] } catch { return [] } })()
    : item.type && item.type !== 'text'
      ? [makeDefaultContent(item.type)]
      : []
  if (inserted.length === 0) {
    // 选「文本」= 只消费命令，前后文合并留在当前行，光标落断点处
    recordBlockChange(block.id, 'title', text, head + tail)
    applyTitle(block.id, head + tail)
    focusRow(block.id, head.length)
    return
  }
  recordBlockChange(block.id, 'title', text, head)
  applyTitle(block.id, head)
  void insertRowsAfter(block, inserted, tail).then(nb => focusRow(nb.id, 'start'))
}

// ── 行键盘行为 ──
function onRowKeydown(row: BlockRow, e: KeyboardEvent) {
  // 中文输入法组合期不拦截任何键
  if (e.isComposing || e.keyCode === 229) return
  const block = row.block
  const ta = e.target as HTMLTextAreaElement

  // 斜杠菜单键盘导航
  if (slashMenu.value && slashMenu.value.blockId === block.id && slashItems.value.length) {
    if (e.key === 'ArrowDown') { e.preventDefault(); slashHi.value = (slashHi.value + 1) % slashItems.value.length; return }
    if (e.key === 'ArrowUp') { e.preventDefault(); slashHi.value = (slashHi.value - 1 + slashItems.value.length) % slashItems.value.length; return }
    if (e.key === 'Enter') {
      e.preventDefault()
      onSlashSelect(slashItems.value[Math.min(slashHi.value, slashItems.value.length - 1)])
      return
    }
    if (e.key === 'Escape') { e.preventDefault(); closeSlash(); return }
    if (e.key === ' ') { closeSlash() } // 空格关闭菜单，空格本身照常输入
  }

  // 行内撤销/重做（自建栈：跨块结构操作原生栈无法覆盖）
  if (e.ctrlKey || e.metaKey) {
    const key = e.key.toLowerCase()
    if (key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); return }
    if ((key === 'z' && e.shiftKey) || key === 'y') { e.preventDefault(); redo(); return }
  }

  // 回车 = 正文换行（textarea 原生行为，不拦截）；Ctrl+Enter = 光标处分出新任务
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); splitRowAtCursor(row, ta); return }
  if (e.key === 'Tab') { e.preventDefault(); e.shiftKey ? outdentBlock(row) : indentBlock(row); return }
  if (e.key === 'Backspace' && ta.selectionStart === 0 && ta.selectionEnd === 0) { mergeOrDeleteAtRowStart(row, e); return }
  if (e.key === 'ArrowUp' && ta.selectionStart === 0 && ta.selectionEnd === 0) {
    const prev = neighborRowId(block.id, -1)
    if (prev !== null) { e.preventDefault(); focusRow(prev, 'end') }
    return
  }
  if (e.key === 'ArrowDown' && ta.selectionStart === ta.value.length && ta.selectionEnd === ta.value.length) {
    const next = neighborRowId(block.id, 1)
    if (next !== null) { e.preventDefault(); focusRow(next, 'start') }
    return
  }
}

/** Ctrl+Enter：光标处拆分任务，tail 移入新任务段（乐观插入：本地立即成行，后台落库）。 */
async function splitRowAtCursor(row: BlockRow, ta: HTMLTextAreaElement) {
  const block = row.block
  // 当前块若为临时块（极快连续回车），先落库保证 after_id / 拆分语义正确
  await ensureBlockPersisted(block)
  if (!blocks.value.some(b => b.id === block.id)) return // 落库失败行已移除
  const pos = ta.selectionStart ?? 0
  const text = block.title ?? ''
  const head = text.slice(0, pos)
  const tail = text.slice(pos)

  // 空行防堆块：当前行与 tail 全空且下方还有行 → 只聚焦下一行
  if (!head.trim() && !tail) {
    const next = neighborRowId(block.id, 1)
    if (next !== null) { focusRow(next, 'start'); return }
  }

  recordBlockChange(block.id, 'title', text, head)
  applyTitle(block.id, head)
  const nb = createBlockOptimistic(block, block.parent_id, tail)
  focusRow(nb.id, 'start')
}

/** 在当前块之后新建同级空任务块并聚焦（乐观插入，零延迟可输入）。 */
async function addBlockAfter(block: Block) {
  await ensureBlockPersisted(block)
  if (!blocks.value.some(b => b.id === block.id)) return // 落库失败行已移除
  const nb = createBlockOptimistic(block, block.parent_id, '')
  focusRow(nb.id, 'start')
}

/** 为当前块新建一个子块（parent_id = 当前块）并聚焦。 */
async function addChildBlock(block: Block) {
  if (block.parent_id !== null) return // 仅顶层块可作为父
  await ensureBlockPersisted(block)
  if (!blocks.value.some(b => b.id === block.id)) return
  const nb = createBlockOptimistic(null, realIdOf(block.id), '') // parent 需服务端真实 id
  if (!expandedIds.value.has(block.id)) toggleExpand(block.id)
  focusRow(nb.id, 'start')
}

/** Tab：顶层块变为前一个顶层兄弟的子块（排其子块末尾）。 */
async function indentBlock(row: BlockRow) {
  await awaitPendingCreates() // reorder 需要服务端真实 id
  const block = row.block
  if (row.depth !== 0) return
  const tops = blocks.value.filter(b => b.parent_id === null).sort(byOrder)
  const idx = tops.findIndex(b => b.id === block.id)
  if (idx <= 0) return // 无前一个兄弟
  if (childrenOf(block.id).length > 0) return // 自身有子块：后端要求父级必须是顶层块
  const target = tops[idx - 1]
  const updates: { id: number; parent_id: number | null; sort_order: number }[] = []
  tops.filter(b => b.id !== block.id).forEach((b, i) => updates.push({ id: realIdOf(b.id), parent_id: null, sort_order: i }))
  const sibs = blocks.value.filter(b => b.parent_id === target.id).sort(byOrder)
  sibs.forEach((c, i) => updates.push({ id: realIdOf(c.id), parent_id: realIdOf(target.id), sort_order: i }))
  updates.push({ id: realIdOf(block.id), parent_id: realIdOf(target.id), sort_order: sibs.length })
  await api.post('/blocks/reorder', { updates })
  await reloadBlocks()
  focusRow(block.id, 'end')
}

/** Shift+Tab：子块升回顶层，插到父块之后。 */
async function outdentBlock(row: BlockRow) {
  await awaitPendingCreates()
  const block = row.block
  if (row.depth !== 1 || block.parent_id === null) return
  const parent = blocks.value.find(b => b.id === block.parent_id)
  if (!parent) return
  const updates: { id: number; parent_id: number | null; sort_order: number }[] = []
  const sibs = blocks.value.filter(b => b.parent_id === parent.id && b.id !== block.id).sort(byOrder)
  sibs.forEach((c, i) => updates.push({ id: realIdOf(c.id), parent_id: realIdOf(parent.id), sort_order: i }))
  const tops = blocks.value.filter(b => b.parent_id === null && b.id !== block.id).sort(byOrder)
  const pIdx = tops.findIndex(b => b.id === parent.id)
  if (pIdx === -1) return
  tops.splice(pIdx + 1, 0, block)
  tops.forEach((b, i) => updates.push({ id: realIdOf(b.id), parent_id: null, sort_order: i }))
  await api.post('/blocks/reorder', { updates })
  await reloadBlocks()
  focusRow(block.id, 'end')
}

/** Backspace 行首：空行且无子块 → 删除并聚焦上一行；
 * 非空 text 行且上一行也是 text 行 → 正文合并进上一行（连续文档流），光标落合并点。 */
async function mergeOrDeleteAtRowStart(row: BlockRow, e: KeyboardEvent) {
  const block = row.block
  if (childrenOf(block.id).length > 0) return // 有子块不删不并
  const prevId = neighborRowId(block.id, -1)
  const prev = prevId !== null ? blocks.value.find(b => b.id === prevId) : null

  // 非空行：仅在上一行也是 text 行时合并，否则不拦（行首 Backspace 原生无效果）
  if (block.title) {
    if (!prev || !isTextRow(prev)) return
    e.preventDefault()
    const mergePos = (prev.title ?? '').length
    recordBlockChange(prev.id, 'title', prev.title ?? '', (prev.title ?? '') + block.title)
    applyTitle(prev.id, (prev.title ?? '') + block.title)
    await ensureBlockPersisted(block)
    pendingUpdates.delete(block.id)
    try {
      await api.del(`/blocks/${realIdOf(block.id)}`)
    } catch {
      return
    }
    blocks.value = blocks.value.filter(b => b.id !== block.id)
    focusRow(prev.id, mergePos)
    return
  }

  // 空行：删除并聚焦上一行
  e.preventDefault()
  await ensureBlockPersisted(block) // 临时块先落库，删除才能打到服务端真实块
  pendingUpdates.delete(block.id) // 防止队列残留更新打到已删块
  try {
    await api.del(`/blocks/${realIdOf(block.id)}`)
  } catch {
    return
  }
  blocks.value = blocks.value.filter(b => b.id !== block.id)
  if (blocks.value.length === 0) {
    const nb = await api.post<Block>('/blocks', { document_id: Number(props.id), title: '', content: '[]' })
    blocks.value.push(nb)
    focusRow(nb.id, 'end')
    return
  }
  if (prevId !== null) focusRow(prevId, 'end')
}

// ── 块删除确认对话框（FR-08：影响范围 + 子块保留选项）──
const deleteTarget = ref<{ block: Block; direct: number; descendants: number } | null>(null)
const keepChildren = ref(false)

const deleteDetails = computed(() => {
  if (!deleteTarget.value) return []
  const t = deleteTarget.value
  if (t.direct === 0) return []
  return [
    { label: '直接子块', value: `${t.direct} 个` },
    { label: '后代子块（含孙级）', value: `${t.descendants} 个` },
  ]
})

function deleteBlock(blockId: number) {
  const block = blocks.value.find(b => b.id === blockId)
  if (!block) return
  const direct = childrenOf(blockId).length
  let descendants = 0
  const walk = (pid: number) => {
    for (const c of childrenOf(pid)) { descendants++; walk(c.id) }
  }
  walk(blockId)
  deleteTarget.value = { block, direct, descendants }
  keepChildren.value = false
}

async function confirmDeleteBlock() {
  if (!deleteTarget.value) return
  const { block } = deleteTarget.value
  deleteTarget.value = null
  // 焦点落点：保留子块 → 第一个子块（它会上移到被删位置）；否则跳过被删块及其后代取下一行，再退回上一行
  const kidsIds = new Set(childrenOf(block.id).map(k => k.id))
  let target: number | null = keepChildren.value && kidsIds.size ? [...kidsIds][0] : null
  if (target === null) {
    const rows = flatRows.value
    const idx = rows.findIndex(r => r.kind === 'block' && r.block.id === block.id)
    for (let j = idx + 1; j < rows.length; j++) {
      const r = rows[j]
      if (r.kind === 'block' && !kidsIds.has(r.block.id)) { target = r.block.id; break }
    }
    if (target === null) {
      for (let j = idx - 1; j >= 0; j--) {
        const r = rows[j]
        if (r.kind === 'block') { target = r.block.id; break }
      }
    }
  }
  await api.del(`/blocks/${realIdOf(block.id)}${keepChildren.value ? '?keep_children=1' : ''}`)
  await reloadBlocks()
  if (target !== null) focusRow(target, 'end')
}

async function copyBlock(block: Block) {
  await api.post(`/blocks/${realIdOf(block.id)}/copy`)
  await reloadBlocks()
}

// ── 浮层管理：时间 popover / 更多菜单 / 斜杠菜单 / 视图菜单 ──
const timePopoverId = ref<number | null>(null)
const moreMenuId = ref<number | null>(null)
const viewMenuOpen = ref(false)

function toggleTimePopover(id: number) {
  timePopoverId.value = timePopoverId.value === id ? null : id
  moreMenuId.value = null
  viewMenuOpen.value = false
  closeSlash()
}

function toggleMoreMenu(id: number) {
  moreMenuId.value = moreMenuId.value === id ? null : id
  timePopoverId.value = null
  viewMenuOpen.value = false
  closeSlash()
}

function toggleViewMenu() {
  viewMenuOpen.value = !viewMenuOpen.value
  closeFloats()
  closeSlash()
}

function closeFloats() {
  timePopoverId.value = null
  moreMenuId.value = null
}

function onDocMouseDown(e: MouseEvent) {
  const t = e.target as HTMLElement
  if (!t.closest('.row-popover') && !t.closest('.row-time') && !t.closest('.row-more')) closeFloats()
  if (!t.closest('.slash-menu')) closeSlash()
  if (!t.closest('.view-menu-wrap')) viewMenuOpen.value = false
}

function onWinScroll() {
  closeFloats()
  closeSlash()
}

// ── 拖拽排序（同级重排 + 父子层级调整 + 落点提示）──
type DropZone = 'before' | 'after' | 'child'
const dragBlockId = ref<number | null>(null)
const dropHint = ref<{ id: number; zone: DropZone } | null>(null)

function onDragStart(block: Block, e: DragEvent) {
  dragBlockId.value = block.id
  e.dataTransfer?.setData('text/plain', String(block.id))
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}

function onDragEnd() {
  dragBlockId.value = null
  dropHint.value = null
}

function onDragOver(block: Block, e: DragEvent) {
  if (dragBlockId.value === null) return
  const dragged = blocks.value.find(b => b.id === dragBlockId.value)
  if (!dragged) return
  // 顶层块只与其他顶层块交互（避免把自己变成别人的子块）
  if (dragged.parent_id === null && block.parent_id !== null) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'

  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const y = e.clientY - rect.top
  const h = rect.height
  let zone: DropZone = y < h * 0.25 ? 'before' : y > h * 0.75 ? 'after' : 'child'
  // 子块不能容纳子级 / 被拖块自身有子块（后端要求父级为顶层）：child 落点转为 after
  if (zone === 'child' && (block.parent_id !== null || childrenOf(dragged.id).length > 0)) zone = 'after'
  dropHint.value = { id: block.id, zone }
}

function dropClass(block: Block): Record<string, boolean> {
  if (!dropHint.value || dropHint.value.id !== block.id) return {}
  return { [`drop-${dropHint.value.zone}`]: true }
}

async function onDrop(block: Block, e: DragEvent) {
  e.preventDefault()
  const dragged = blocks.value.find(b => b.id === dragBlockId.value)
  const hint = dropHint.value
  onDragEnd()
  if (!dragged || !hint || hint.id !== block.id) return
  if (dragged.id === block.id) return
  if (dragged.parent_id === null && block.parent_id !== null) return
  if (hint.zone === 'child' && childrenOf(dragged.id).length > 0) return
  await awaitPendingCreates() // reorder 需要服务端真实 id

  type Upd = { id: number; parent_id: number | null; sort_order: number }
  const updates: Upd[] = []

  if (hint.zone === 'child') {
    // 顶层块 → 另一顶层块的子块（追加到末尾）
    const oldTop = blocks.value.filter(b => b.parent_id === null && b.id !== dragged.id).sort(byOrder)
    oldTop.forEach((b, i) => updates.push({ id: realIdOf(b.id), parent_id: null, sort_order: i }))
    const newChildren = blocks.value.filter(b => b.parent_id === block.id).sort(byOrder)
    newChildren.forEach((c, i) => updates.push({ id: realIdOf(c.id), parent_id: realIdOf(block.id), sort_order: i }))
    updates.push({ id: realIdOf(dragged.id), parent_id: realIdOf(block.id), sort_order: newChildren.length })
  } else {
    const newParent = block.parent_id
    if (dragged.parent_id !== newParent) {
      // 跨父级移动：原父级剩余块重排
      const oldSiblings = blocks.value
        .filter(b => b.parent_id === dragged.parent_id && b.id !== dragged.id)
        .sort(byOrder)
      oldSiblings.forEach((b, i) => updates.push({ id: realIdOf(b.id), parent_id: dragged.parent_id, sort_order: i }))
    }
    // 目标序列中插入到目标块前/后
    const seq = blocks.value
      .filter(b => b.parent_id === newParent && b.id !== dragged.id)
      .sort(byOrder)
    const idx = seq.findIndex(b => b.id === block.id)
    if (idx === -1) return
    seq.splice(hint.zone === 'before' ? idx : idx + 1, 0, dragged)
    seq.forEach((b, i) => updates.push({ id: realIdOf(b.id), parent_id: newParent, sort_order: i }))
  }

  await api.post('/blocks/reorder', { updates })
  await reloadBlocks()
}
</script>

<template>
  <div class="editor" v-if="doc">
    <header class="editor-header">
      <button class="icon-btn" @click="router.push('/')">← 返回</button>
      <span class="ce-spacer"></span>
      <button class="icon-btn" title="撤销 (Ctrl+Z)" :disabled="undoStack.length === 0" @click="undo">↶ 撤销</button>
      <button class="icon-btn" title="重做 (Ctrl+Y)" :disabled="redoStack.length === 0" @click="redo">↷ 重做</button>
      <span v-if="saveStateText" class="save-status" :class="saveState">{{ saveStateText }}</span>
      <button v-if="saveState === 'error'" class="icon-btn save-retry" title="立即重试保存" @click="flushSaves">重试保存</button>
      <div class="view-menu-wrap">
        <button class="icon-btn" :class="{ on: viewMenuOpen }" title="视图选项" @click="toggleViewMenu">☰ 视图</button>
        <div v-if="viewMenuOpen" class="view-menu" @mousedown.stop>
          <div class="vm-label">排序方式</div>
          <button
            v-for="m in SORT_OPTIONS"
            :key="m.value"
            class="vm-item"
            :class="{ on: sortMode === m.value }"
            @click="sortMode = m.value; viewMenuOpen = false"
          ><span class="vm-check"></span>{{ m.label }}</button>
          <div class="vm-divider"></div>
          <button class="vm-item" @click="collapsedView = !collapsedView">
            <span class="vm-check"></span>{{ collapsedView ? '⊞ 平铺视图' : '⊟ 折叠视图' }}
          </button>
          <template v-if="collapsedView">
            <button class="vm-item vm-indent" @click="expandAll">全部展开</button>
            <button class="vm-item vm-indent" @click="collapseAll">全部收起</button>
          </template>
          <div v-if="sortMode !== 'doc'" class="vm-hint">排序仅影响展示；Enter / Tab / 拖拽按文档顺序执行</div>
        </div>
      </div>
    </header>

    <div class="editor-body">
      <!-- 文档标题 -->
      <textarea
        ref="docTitleEl"
        class="doc-title"
        rows="1"
        :value="doc.name"
        placeholder="无标题文档"
        @input="onDocTitleInput"
        @keydown.enter.prevent="($event.target as HTMLTextAreaElement).blur()"
      ></textarea>

      <!-- 文档流行列表 -->
      <template v-for="row in flatRows" :key="row.kind === 'group' ? 'g:' + row.label : 'b:' + row.block.id">
        <h3 v-if="row.kind === 'group'" class="work-group-title">
          {{ row.label }}<small>{{ row.count }} 块</small>
        </h3>

        <div
          v-else
          class="doc-row"
          :class="[row.depth === 1 ? 'depth-1' : 'depth-0', dropClass(row.block)]"
          :data-block-id="row.block.id"
          :draggable="sortMode === 'doc'"
          @dragstart="onDragStart(row.block, $event)"
          @dragend="onDragEnd"
          @dragover="onDragOver(row.block, $event)"
          @drop="onDrop(row.block, $event)"
          @focusin="lastEditedBlockId = row.block.id"
        >
          <div class="row-main">
            <span v-if="sortMode === 'doc'" class="row-handle" title="拖拽排序">⠿</span>
            <button
              v-if="sortMode === 'doc' && row.depth === 0"
              class="row-add-child"
              title="添加子块（Tab）"
              @click.stop="addChildBlock(row.block)"
            >＋</button>
            <!-- text 行：多行正文 textarea（回车=换行，Ctrl+Enter/双空行分任务） -->
            <textarea
              v-if="isTextRow(row.block)"
              class="row-input"
              rows="1"
              :value="row.block.title ?? ''"
              placeholder="输入正文，回车换行；Ctrl+Enter 或两个空行分任务，'/' 插入内容"
              @input="onRowInput(row, $event)"
              @keydown="onRowKeydown(row, $event)"
              @blur="flushSaves()"
            ></textarea>
            <!-- content 行：单个内容块（删除/复制走 ⋯ 菜单；Tab 缩进/拖拽排序与 text 行一致） -->
            <ContentEditor
              v-else-if="isExpanded(row.block.id)"
              class="row-rich"
              :model-value="row.block.content"
              :block-id="row.block.id"
              @update:model-value="updateBlockContent(row.block, $event)"
            />
            <button
              v-if="collapsedView"
              class="row-more"
              :title="isExpanded(row.block.id) ? '收起' : '展开'"
              @click.stop="toggleExpand(row.block.id)"
            >{{ isExpanded(row.block.id) ? '⊟' : '⊞' }}</button>
            <button
              class="row-time"
              :class="timeChip(row.block).cls"
              :title="timeChip(row.block).tip"
              @click.stop="toggleTimePopover(row.block.id)"
            >{{ timeChip(row.block).text }}</button>
            <button class="row-more" title="更多操作" @click.stop="toggleMoreMenu(row.block.id)">⋯</button>
            <span v-if="failedCreates.has(row.block.id)" class="row-unsynced" @click.stop>
              <span class="unsynced-tag">未同步</span>
              <button class="unsynced-op" title="重新创建此块" @click="retryCreate(row.block.id)">重试</button>
              <button class="unsynced-op" title="复制正文到剪贴板" @click="copyUnsynced(row.block.id)">复制</button>
            </span>
          </div>

          <!-- 工作时段 popover -->
          <div v-if="timePopoverId === row.block.id" class="row-popover" @mousedown.stop>
            <label>开始
              <input
                type="datetime-local"
                :value="toLocalInput(row.block.work_start_time)"
                @change="updateBlockTime(row.block, 'work_start_time', ($event.target as HTMLInputElement).value)"
              />
            </label>
            <label>结束
              <input
                type="datetime-local"
                :value="toLocalInput(row.block.work_end_time)"
                @change="updateBlockTime(row.block, 'work_end_time', ($event.target as HTMLInputElement).value)"
              />
            </label>
            <button
              class="pop-clear"
              @click="updateBlockTime(row.block, 'work_start_time', ''); updateBlockTime(row.block, 'work_end_time', ''); timePopoverId = null"
            >清除时间</button>
          </div>

          <!-- 更多菜单 -->
          <div v-if="moreMenuId === row.block.id" class="row-popover row-more-menu" @mousedown.stop>
            <button class="menu-item" @click="copyBlock(row.block); moreMenuId = null">⧉ 完整复制（含子块）</button>
            <button class="menu-item" @click="requestSaveTemplate(row.block); moreMenuId = null">▤ 内容存为模板</button>
            <button class="menu-item danger" @click="moreMenuId = null; deleteBlock(row.block.id)">✕ 删除…</button>
          </div>

          <!-- 折叠视图：任务段摘要（text 行取首行，content 行取类型化描述） -->
          <div
            v-if="!isExpanded(row.block.id)"
            class="row-summary"
            title="点击展开"
            @click="toggleExpand(row.block.id)"
          >{{ summarize(row.block) }}</div>

          <!-- 内容块下方：手动另起任务入口（内容块天然断开任务，这是补充手势） -->
          <button
            v-if="!isTextRow(row.block) && isExpanded(row.block.id)"
            class="row-add-after"
            @click.stop="addBlockAfter(row.block)"
          >＋ 在此后新建任务</button>
        </div>
      </template>
    </div>

    <!-- 斜杠命令菜单 -->
    <SlashMenu
      v-if="slashMenu && slashItems.length"
      :anchor="slashMenu.anchor"
      :items="slashItems"
      :hi="slashHi"
      @select="onSlashSelect"
      @hover="slashHi = $event"
    />

    <!-- 删除块确认对话框（FR-08：影响范围展示 + 子块是否一并删除） -->
    <ConfirmDialog
      v-if="deleteTarget"
      :title="`确认删除任务段「${summarize(deleteTarget.block)}」？`"
      :message="deleteTarget.direct > 0 ? '默认删除时子块将一并删除，且不可恢复。' : '删除后不可恢复。'"
      :details="deleteDetails"
      confirmText="删除"
      :danger="true"
      @confirm="confirmDeleteBlock"
      @cancel="deleteTarget = null"
    >
      <label v-if="deleteTarget.direct > 0" class="keep-children-option">
        <input type="checkbox" v-model="keepChildren" />
        保留子块（提升为{{ deleteTarget.block.parent_id ? '上一级' : '独立' }}任务块）
      </label>
    </ConfirmDialog>

    <!-- 保存为模板名称输入 -->
    <PromptDialog
      v-if="templateTarget"
      title="内容存为模板"
      message="为该内容块模板命名："
      placeholder="模板名称"
      :initial-value="summarize(templateTarget)"
      confirm-text="保存"
      @confirm="confirmSaveTemplate"
      @cancel="templateTarget = null"
    />

    <!-- 离页未保存守卫：重试 / 留在页面 / 放弃 -->
    <div v-if="leaveGuard" ref="leaveGuardRoot" class="dialog-overlay">
      <div class="dialog" role="alertdialog" aria-modal="true" aria-labelledby="leave-guard-title">
        <h3 id="leave-guard-title" class="dialog-title">有未保存的更改</h3>
        <p class="dialog-message">部分更改尚未成功保存。你可以重试保存，或放弃这些更改并离开。</p>
        <div class="dialog-actions">
          <button class="danger" @click="answerLeave('discard')">放弃更改并离开</button>
          <button ref="leaveStayBtn" @click="answerLeave('stay')">留在页面</button>
          <button class="primary" @click="answerLeave('retry')">重试保存</button>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="loading">加载中...</div>
</template>

<style scoped>
.editor { min-height: 100vh; }

/* 顶栏：白底 sticky + hairline，右侧操作 */
.editor-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 24px;
  border-bottom: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 50;
}
.icon-btn {
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted);
  padding: 4px 10px;
  border-radius: var(--radius);
  font-size: 0.85rem;
}
.icon-btn:hover { border-color: transparent; color: var(--fg); background: var(--bg-alt); }
.icon-btn:disabled { opacity: 0.35; cursor: default; }
.icon-btn:disabled:hover { background: transparent; color: var(--muted); }
.ce-spacer { flex: 1; }
.save-status { font-size: 0.78rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.save-status.saved { color: var(--ok); }
.save-status.saving, .save-status.pending { color: var(--accent); }
.save-status.error { color: var(--danger); }
.save-retry { color: var(--danger); border-color: rgba(197, 50, 43, 0.32); font-weight: 600; }
.save-retry:hover { background: var(--danger); color: #fff; }

/* 居中主栏：以 vw 动态占屏，上限 1500px 保证超宽屏阅读舒适 */
.editor-body { max-width: min(1500px, 93vw); margin: 0 auto; padding: 48px 56px 32vh; }

.doc-title {
  font-size: 34px;
  font-weight: 600;
  letter-spacing: 0.01em;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  padding: 0 0 10px;
  margin-bottom: 28px;
  width: 100%;
  overflow: hidden;
  line-height: 1.35;
  border-radius: 0;
}
.doc-title:focus { border: none; box-shadow: none; }
.doc-title::placeholder { color: #c9cdd1; }

/* 视图菜单：排序/折叠收拢进 header 下拉，正文为主 */
.view-menu-wrap { position: relative; }
.view-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 200;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 6px;
  min-width: 200px;
  animation: wm-pop 0.16s ease-out;
}
.icon-btn.on { color: var(--fg); background: var(--bg-alt); }
.vm-label { font-size: 11px; color: var(--faint); padding: 6px 10px 4px; letter-spacing: 0.04em; }
.vm-item {
  display: flex; align-items: center; gap: 8px;
  width: 100%; text-align: left;
  border: none; background: transparent;
  padding: 6px 10px; font-size: 13px; color: var(--fg);
  border-radius: var(--radius);
}
.vm-item:hover { background: var(--bg-hover); }
.vm-check {
  flex-shrink: 0; width: 8px; height: 8px; border-radius: 50%;
  border: 1px solid var(--border); opacity: 0.6;
}
.vm-item.on .vm-check { background: var(--accent); border-color: var(--accent); opacity: 1; }
.vm-item.on { font-weight: 600; }
.vm-divider { height: 1px; background: var(--border); margin: 4px 8px; }
.vm-indent { padding-left: 26px; color: var(--muted); }
.vm-hint { font-size: 11px; color: var(--faint); padding: 6px 10px 2px; line-height: 1.5; }

/* 任务行：干净行式布局（飞书块式），hover 轻灰、聚焦更轻 */
.doc-row {
  position: relative;
  padding: 2px 8px 2px 4px;
  border-radius: var(--radius);
  animation: wm-fade-up 0.24s both;
}
.doc-row:nth-child(2) { animation-delay: 0.01s; }
.doc-row:nth-child(3) { animation-delay: 0.02s; }
.doc-row:nth-child(4) { animation-delay: 0.03s; }
.doc-row:nth-child(5) { animation-delay: 0.04s; }
.doc-row:nth-child(6) { animation-delay: 0.05s; }
.doc-row:nth-child(7) { animation-delay: 0.06s; }
.doc-row:nth-child(8) { animation-delay: 0.07s; }
.doc-row:hover { background: var(--bg-hover); }
.doc-row:focus-within { background: rgba(38, 40, 44, 0.025); }
.doc-row[draggable='true'] { cursor: grab; }
.doc-row.depth-1 { margin-left: 22px; }
.doc-row.depth-1::before {
  content: '';
  position: absolute;
  left: -11px;
  top: 2px;
  bottom: 2px;
  width: 2px;
  border-radius: 1px;
  background: var(--border-strong);
}
.doc-row.depth-1:hover::before { background: var(--accent-line); }

.row-main { display: flex; align-items: flex-start; gap: 6px; }
.row-handle {
  color: var(--faint); cursor: grab; font-size: 13px;
  padding: 8px 1px 0; opacity: 0; transition: opacity 0.15s, color 0.15s;
  user-select: none; width: 18px; flex-shrink: 0;
}
.doc-row:hover .row-handle { opacity: 0.8; }
.row-handle:hover { color: var(--accent); opacity: 1; }
.row-add-child {
  border: none;
  background: transparent;
  color: var(--faint);
  font-size: 14px;
  width: 18px;
  height: 22px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
  flex-shrink: 0;
  margin-top: 3px;
}
.doc-row:hover .row-add-child { opacity: 1; }
.row-add-child:hover { color: var(--accent); background: var(--accent-light); }

.row-input {
  border: none; outline: none; resize: none; background: transparent;
  flex: 1; min-width: 0; font-family: inherit; color: var(--fg);
  font-size: 15px; line-height: 1.75; padding: 5px 2px; overflow: hidden; border-radius: 4px;
  field-sizing: content;
}
.row-input:focus { border: none; box-shadow: none; }
.row-input::placeholder { color: #c9cdd1; }

/* 时间 chip：行尾弱化元信息，hover 才浮出（不再挤占输入区） */
.row-time {
  border: 1px solid transparent;
  background: transparent;
  padding: 2px 6px;
  margin-top: 5px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--faint);
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, border-color 0.15s, background 0.15s;
}
.doc-row:hover .row-time, .doc-row:focus-within .row-time { opacity: 1; }
.row-time:hover { border-color: var(--border); color: var(--fg); background: var(--bg-alt); }
.row-time.chip-work {
  color: var(--accent);
  opacity: 1;
}
.row-time.chip-work::before { content: '●'; font-size: 6px; margin-right: 4px; vertical-align: 2px; }
.row-more {
  border: none; background: transparent; color: var(--muted);
  font-size: 14px; padding: 4px 6px; border-radius: 4px;
  opacity: 0; transition: opacity 0.15s, background 0.15s; flex-shrink: 0;
}
.doc-row:hover .row-more, .doc-row:focus-within .row-more { opacity: 1; }
.row-more:hover { background: var(--bg-alt); color: var(--fg); }

/* 触屏 / 无悬停设备：行操作常显，保证可发现 */
@media (hover: none) {
  .row-time, .row-more { opacity: 1; }
}

/* 浮层：时间 popover / 更多菜单 */
.row-popover {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 100;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 250px;
  animation: wm-pop 0.16s ease-out;
}
.row-popover label { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
.row-popover input[type='datetime-local'] {
  border: 1px solid var(--border); border-radius: 4px;
  padding: 3px 6px; font-size: 12px; width: auto; background: var(--bg);
  font-variant-numeric: tabular-nums;
}
.pop-clear {
  border: 1px solid var(--border); background: var(--bg);
  font-size: 12px; padding: 3px 10px; border-radius: 4px; color: var(--muted); align-self: flex-start;
}
.pop-clear:hover { color: var(--accent); border-color: var(--accent-line); background: var(--accent-light); }
.menu-item {
  display: block; width: 100%; text-align: left; border: none;
  background: transparent; padding: 6px 10px; font-size: 13px; border-radius: var(--radius); color: var(--fg);
}
.menu-item:hover { background: var(--accent-light); color: var(--accent); }
.menu-item.danger { color: var(--danger); }
.menu-item.danger:hover { background: rgba(163, 51, 39, 0.08); color: var(--danger); }

/* 内容块在行内占满剩余宽度（与正文左对齐，随窗口缩放） */
.row-rich { flex: 1; min-width: 0; margin: 3px 0; overflow: visible; }
.row-summary {
  color: var(--muted);
  font-size: 0.85rem;
  cursor: pointer;
  padding: 4px 2px 4px 50px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.15s;
}
.row-summary:hover { color: var(--accent); }

/* 富内容下方：新建任务入口（hover 浮现，静音处理） */
.row-add-after {
  display: block;
  margin: 2px 0 0 50px;
  border: none;
  background: transparent;
  color: var(--faint);
  font-size: 0.82rem;
  padding: 4px 10px;
  border-radius: var(--radius);
  cursor: pointer;
  width: fit-content;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
}
.doc-row:hover .row-add-after, .doc-row:focus-within .row-add-after { opacity: 1; }
.row-add-after:hover { color: var(--accent); background: var(--accent-light); }

/* 工作时段分组标题 */
.work-group-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--fg);
  margin: 28px 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.work-group-title::before {
  content: '';
  width: 3px;
  height: 14px;
  background: var(--accent);
  border-radius: 2px;
  align-self: center;
  flex-shrink: 0;
}
.work-group-title small {
  color: var(--faint);
  font-weight: normal;
  margin-left: auto;
  font-size: 0.75rem;
  font-family: var(--font-body);
  font-variant-numeric: tabular-nums;
}

/* 拖拽落点提示 */
.doc-row.drop-before { box-shadow: 0 -2px 0 0 var(--accent); }
.doc-row.drop-after { box-shadow: 0 2px 0 0 var(--accent); }
.doc-row.drop-child { outline: 2px dashed var(--accent-line); outline-offset: 2px; }

/* 块定位高亮（搜索跳转/位置恢复） */
.doc-row.block-highlight { animation: block-flash 2s ease-out; }
@keyframes block-flash {
  0%, 45% { background: var(--accent-light); box-shadow: inset 2px 0 0 var(--accent); }
  100% { background: transparent; box-shadow: none; }
}

.loading { padding: 60px; text-align: center; color: var(--muted); font-family: var(--font-serif); letter-spacing: 0.1em; }

/* 删除确认对话框：子块保留选项 */
.keep-children-option {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.88rem;
  color: var(--fg);
  cursor: pointer;
  padding: 8px 12px;
  background: var(--bg-alt);
  border-radius: var(--radius);
}

/* 离页未保存守卫对话框（本组件内联实现，复用统一样式） */
.dialog-overlay {
  position: fixed; inset: 0;
  background: rgba(35, 39, 43, 0.38);
  backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.dialog {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 26px;
  width: min(480px, calc(100vw - 32px));
  box-shadow: var(--shadow-lg);
  animation: wm-pop 0.18s ease-out;
}
.dialog-title { font-family: var(--font-serif); font-size: 1.15rem; font-weight: 700; margin-bottom: 8px; }
.dialog-message { color: var(--muted); margin-bottom: 12px; font-size: 0.9rem; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }

/* 未同步块标记 */
.row-unsynced {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 5px;
  flex-shrink: 0;
}
.unsynced-tag {
  font-size: 11px;
  color: var(--danger);
  border: 1px solid rgba(197, 50, 43, 0.35);
  border-radius: 999px;
  padding: 0 8px;
  line-height: 1.6;
  white-space: nowrap;
}
.unsynced-op {
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  line-height: 1.6;
}
.unsynced-op:hover { color: var(--accent); background: var(--bg-alt); }
</style>
