<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute, onBeforeRouteLeave } from 'vue-router'
import { api } from '@/composables/useApi'
import ContentEditor from '@/components/ContentEditor.vue'
import type { Document, Block, ContentBlock } from '@/types'

const props = defineProps<{ id: string }>()
const router = useRouter()
const route = useRoute()

const doc = ref<Document | null>(null)
const blocks = ref<Block[]>([])
const newBlockTitle = ref('')

// ── 内容块模板（localStorage 持久化，前端本地实现）──
const TEMPLATE_KEY = 'workmark_block_templates'
interface BlockTemplate { name: string; content: string }
const templates = ref<BlockTemplate[]>(loadTemplates())
const pickedTemplate = ref<number | null>(null)

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

function saveBlockAsTemplate(block: Block) {
  const name = prompt('模板名称：', block.title || '未命名模板')
  if (!name) return
  templates.value.push({ name, content: block.content })
  persistTemplates()
}

// ── 数据加载 ──
onMounted(async () => {
  doc.value = await api.get<Document>(`/documents/${props.id}`)
  blocks.value = await api.get<Block[]>(`/blocks/document/${props.id}`)
  // 恢复停留位置：URL ?block= 优先，其次文档 last_position
  const fromQuery = Number(route.query.block) || 0
  const target = fromQuery || parseLastPosition(doc.value.last_position)
  if (target) focusBlock(target)
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
  blocks.value = await api.get<Block[]>(`/blocks/document/${props.id}`)
}

// ── 时间轴：排序模式 + 平铺/折叠视图 + 工作时段分组（FR-04）──
type SortMode = 'doc' | 'created' | 'work_start' | 'work_period'
const sortMode = ref<SortMode>('doc')
const collapsedView = ref(false)
const expandedIds = ref(new Set<number>())

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
    // 未设置时间的块排最后，其余按工作开始时间升序
    const ka = a.work_start_time ?? '9999-12-31'
    const kb = b.work_start_time ?? '9999-12-31'
    return ka.localeCompare(kb) || a.created_at.localeCompare(b.created_at) || a.id - b.id
  }
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

/** 折叠视图卡片摘要：首块类型化描述 + 内容块总数。 */
function summarize(block: Block): string {
  try {
    const items = JSON.parse(block.content) as ContentBlock[]
    if (!Array.isArray(items) || items.length === 0) return '（空）'
    const first = items[0]
    let desc: string
    switch (first.type) {
      case 'text': desc = (first.content || '').trim().slice(0, 60) || '（空文本）'; break
      case 'code': desc = `代码${first.language ? ' · ' + first.language : ''} · ${(first.content || '').split('\n').length} 行`; break
      case 'shell': desc = `命令 · ${(first.content || '').slice(0, 50)}`; break
      case 'output': desc = `输出 · ${(first.content || '').split('\n').length} 行`; break
      case 'todo': {
        const total = first.items?.length ?? 0
        const done = first.items?.filter(i => i.done).length ?? 0
        desc = `待办 ${total} 项（完成 ${done}）`; break
      }
      case 'table': desc = `表格 ${first.rows?.length ?? 0} 行`; break
      case 'image': desc = '[图片]'; break
      default: desc = '（未知类型）'
    }
    return items.length > 1 ? `${desc}　— 共 ${items.length} 个内容块` : desc
  } catch {
    return '（内容不可解析）'
  }
}

/** 时间显示与 datetime-local 输入值互转。 */
function formatDateTime(s: string | null): string {
  return s ? s.replace('T', ' ').slice(0, 16) : ''
}

function toLocalInput(s: string | null): string {
  return s ? s.replace(' ', 'T').slice(0, 16) : ''
}

// ── 块 CRUD ──
async function addBlock() {
  const tpl = pickedTemplate.value !== null ? templates.value[pickedTemplate.value] : null
  const block = await api.post<Block>('/blocks', {
    document_id: Number(props.id),
    title: newBlockTitle.value || undefined,
    content: tpl ? tpl.content : '[]',
  })
  blocks.value.push(block)
  newBlockTitle.value = ''
  pickedTemplate.value = null
}

async function addSubBlock(parentId: number) {
  const block = await api.post<Block>('/blocks', {
    document_id: Number(props.id),
    parent_id: parentId,
    title: '补充记录',
    content: '[]',
  })
  blocks.value.push(block)
}

async function deleteBlock(blockId: number) {
  if (!confirm('确认删除此块？包含子块时将一并删除。')) return
  await api.del(`/blocks/${blockId}`)
  await reloadBlocks()
}

async function copyBlock(block: Block) {
  await api.post(`/blocks/${block.id}/copy`)
  await reloadBlocks()
}

// ── 自动保存（防抖）+ 保存状态 + 撤销/重做 ──
type SaveState = 'idle' | 'pending' | 'saving' | 'saved' | 'error'
const saveState = ref<SaveState>('idle')
const SAVE_DELAY = 800
let saveTimer: number | null = null
const pendingUpdates = new Map<number, { title?: string; content?: string; work_start_time?: string | null; work_end_time?: string | null }>()

const saveStateText = computed(() => ({
  idle: '', pending: '有未保存更改', saving: '保存中…', saved: '已保存 ✓', error: '保存失败，请重试',
}[saveState.value]))

function setSaveState(s: SaveState) { saveState.value = s }

function scheduleFlush() {
  setSaveState('pending')
  if (saveTimer !== null) clearTimeout(saveTimer)
  saveTimer = window.setTimeout(flushSaves, SAVE_DELAY)
}

async function flushSaves(): Promise<void> {
  if (saveTimer !== null) { clearTimeout(saveTimer); saveTimer = null }
  if (pendingUpdates.size === 0) return
  const entries = [...pendingUpdates.entries()]
  pendingUpdates.clear()
  setSaveState('saving')
  try {
    for (const [id, data] of entries) {
      await api.put(`/blocks/${id}`, data)
    }
    setSaveState('saved')
  } catch {
    // 失败的更新放回队列，等待下次触发
    for (const [id, data] of entries) {
      pendingUpdates.set(id, { ...(pendingUpdates.get(id) || {}), ...data })
    }
    setSaveState('error')
  }
}

interface UndoPatch { blockId: number; before: string; after: string }
const undoStack = ref<UndoPatch[]>([])
const redoStack = ref<UndoPatch[]>([])
const UNDO_LIMIT = 100
const UNDO_COALESCE_MS = 1000
// 最近一次记录的 patch 引用（用于把连续输入合并为一个撤销步骤）
let lastPatch: (UndoPatch & { at: number }) | null = null

function recordContentChange(blockId: number, before: string, after: string) {
  if (before === after) return
  const now = Date.now()
  if (lastPatch && lastPatch.blockId === blockId && now - lastPatch.at < UNDO_COALESCE_MS) {
    // 同一块的连续输入：合并为单个撤销步骤（撤销粒度 = 输入停顿）
    lastPatch.after = after
    lastPatch.at = now
  } else {
    const patch: UndoPatch & { at: number } = { blockId, before, after, at: now }
    undoStack.value.push(patch)
    lastPatch = patch
    if (undoStack.value.length > UNDO_LIMIT) undoStack.value.shift()
  }
  redoStack.value = []
}

function applyContent(blockId: number, content: string) {
  const block = blocks.value.find(b => b.id === blockId)
  if (!block) return
  block.content = content
  pendingUpdates.set(blockId, { ...(pendingUpdates.get(blockId) || {}), content })
  scheduleFlush()
}

function undo() {
  const p = undoStack.value.pop()
  lastPatch = null
  if (!p) return
  applyContent(p.blockId, p.before)
  redoStack.value.push({ blockId: p.blockId, before: p.before, after: p.after })
}

function redo() {
  const p = redoStack.value.pop()
  lastPatch = null
  if (!p) return
  applyContent(p.blockId, p.after)
  undoStack.value.push({ blockId: p.blockId, before: p.before, after: p.after })
}

// 键盘快捷键：仅在非输入焦点时接管（输入框内保留原生撤销）
function onKeydown(e: KeyboardEvent) {
  if (!e.ctrlKey) return
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  const key = e.key.toLowerCase()
  if (key === 'z' && !e.shiftKey) { e.preventDefault(); undo() }
  else if ((key === 'z' && e.shiftKey) || key === 'y') { e.preventDefault(); redo() }
}

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (pendingUpdates.size > 0) {
    flushSaves()
    e.preventDefault()
    e.returnValue = ''
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('beforeunload', onBeforeUnload)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('beforeunload', onBeforeUnload)
  flushSaves()
})

// 切换文档（路由离开）前：flush 保存 + 记录停留位置（last_position）
const lastEditedBlockId = ref<number | null>(null)

onBeforeRouteLeave(async () => {
  await flushSaves()
  if (lastEditedBlockId.value !== null) {
    try {
      await api.put(`/documents/${props.id}`, {
        last_position: JSON.stringify({ block_id: lastEditedBlockId.value }),
      })
    } catch {
      // last_position 保存失败不阻塞导航
    }
  }
})

async function updateBlockTitle(block: Block, title: string) {
  block.title = title
  lastEditedBlockId.value = block.id
  pendingUpdates.set(block.id, { ...(pendingUpdates.get(block.id) || {}), title })
  scheduleFlush()
}

/** 更新工作开始/结束时间（传空值即清空，走同一防抖队列）。 */
function updateBlockTime(block: Block, field: 'work_start_time' | 'work_end_time', value: string) {
  const v = value || null
  block[field] = v
  lastEditedBlockId.value = block.id
  pendingUpdates.set(block.id, { ...(pendingUpdates.get(block.id) || {}), [field]: v })
  scheduleFlush()
}

function updateBlockContent(block: Block, content: string) {
  recordContentChange(block.id, block.content, content)
  applyContent(block.id, content)
  lastEditedBlockId.value = block.id
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
  // 顶层块只与其他顶层块交互（避免把自己变成自己的子块）
  if (dragged.parent_id === null && block.parent_id !== null) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'

  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const y = e.clientY - rect.top
  const h = rect.height
  let zone: DropZone = y < h * 0.25 ? 'before' : y > h * 0.75 ? 'after' : 'child'
  // 子块不能容纳子级：child 落点转为 after（仅顶层目标才会保留 child）
  if (zone === 'child' && block.parent_id !== null) zone = 'after'
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

  type Upd = { id: number; parent_id: number | null; sort_order: number }
  const updates: Upd[] = []
  const byOrder = (a: Block, b: Block) => a.sort_order - b.sort_order || a.id - b.id

  if (hint.zone === 'child') {
    // 顶层块 → 另一顶层块的子块（追加到末尾）
    const oldTop = blocks.value.filter(b => b.parent_id === null && b.id !== dragged.id).sort(byOrder)
    oldTop.forEach((b, i) => updates.push({ id: b.id, parent_id: null, sort_order: i }))
    const newChildren = blocks.value.filter(b => b.parent_id === block.id).sort(byOrder)
    newChildren.forEach((c, i) => updates.push({ id: c.id, parent_id: block.id, sort_order: i }))
    updates.push({ id: dragged.id, parent_id: block.id, sort_order: newChildren.length })
  } else {
    const newParent = block.parent_id
    if (dragged.parent_id !== newParent) {
      // 跨父级移动：原父级剩余块重排
      const oldSiblings = blocks.value
        .filter(b => b.parent_id === dragged.parent_id && b.id !== dragged.id)
        .sort(byOrder)
      oldSiblings.forEach((b, i) => updates.push({ id: b.id, parent_id: dragged.parent_id, sort_order: i }))
    }
    // 目标序列中插入到目标块前/后
    const seq = blocks.value
      .filter(b => b.parent_id === newParent && b.id !== dragged.id)
      .sort(byOrder)
    const idx = seq.findIndex(b => b.id === block.id)
    if (idx === -1) return
    seq.splice(hint.zone === 'before' ? idx : idx + 1, 0, dragged)
    seq.forEach((b, i) => updates.push({ id: b.id, parent_id: newParent, sort_order: i }))
  }

  await api.post('/blocks/reorder', { updates })
  await reloadBlocks()
}
</script>

<template>
  <div class="editor" v-if="doc">
    <header class="editor-header">
      <button @click="router.push('/')">← 返回</button>
      <h2>{{ doc.name }}</h2>
      <span class="ce-spacer"></span>
      <button class="icon-btn" title="撤销 (Ctrl+Z)" :disabled="undoStack.length === 0" @click="undo">↶ 撤销</button>
      <button class="icon-btn" title="重做 (Ctrl+Y)" :disabled="redoStack.length === 0" @click="redo">↷ 重做</button>
      <span v-if="saveStateText" class="save-status" :class="saveState">{{ saveStateText }}</span>
    </header>

    <div class="editor-body">
      <div class="add-block-bar">
        <input v-model="newBlockTitle" placeholder="任务块标题（可选）" @keyup.enter="addBlock" />
        <select v-if="templates.length" v-model="pickedTemplate" class="tpl-select" title="从模板创建">
          <option :value="null">模板（可选）</option>
          <option v-for="(t, i) in templates" :key="i" :value="i">{{ t.name }}</option>
        </select>
        <button class="primary" @click="addBlock">+ 添加任务块</button>
      </div>

      <div class="timeline-toolbar">
        <label class="tl-field">排序
          <select v-model="sortMode">
            <option value="doc">文档顺序</option>
            <option value="created">创建时间</option>
            <option value="work_start">工作开始时间</option>
            <option value="work_period">工作时段（按日分组）</option>
          </select>
        </label>
        <button class="tl-btn" @click="collapsedView = !collapsedView">{{ collapsedView ? '⊞ 平铺视图' : '⊟ 折叠视图' }}</button>
        <template v-if="collapsedView">
          <button class="tl-btn" @click="expandAll">全部展开</button>
          <button class="tl-btn" @click="collapseAll">全部收起</button>
        </template>
        <span v-if="sortMode !== 'doc'" class="tl-hint">排序视图仅调整展示顺序；拖拽调整顺序请切换回文档顺序视图</span>
      </div>

      <div v-if="topLevelBlocks.length === 0" class="empty">
        暂无任务块，添加第一个开始记录。
      </div>

      <template v-for="group in displayGroups" :key="group.label || '__all__'">
        <h3 v-if="group.label" class="work-group-title">
          {{ group.label }}<small>{{ group.blocks.length }} 块</small>
        </h3>
        <template v-for="top in group.blocks" :key="top.id">
          <!-- 顶层任务块 -->
          <div
            class="block-card"
            :class="dropClass(top)"
            :data-block-id="top.id"
            :draggable="sortMode === 'doc'"
            @dragstart="onDragStart(top, $event)"
            @dragend="onDragEnd"
            @dragover="onDragOver(top, $event)"
            @drop="onDrop(top, $event)"
          >
            <div class="block-header">
              <span v-if="sortMode === 'doc'" class="drag-handle" title="拖拽排序">⋮⋮</span>
              <input
                :value="top.title ?? ''"
                class="block-title"
                placeholder="无标题"
                @change="updateBlockTitle(top, ($event.target as HTMLInputElement).value)"
              />
              <span class="block-time" :title="'创建时间 ' + formatDateTime(top.created_at)">{{ formatDateTime(top.created_at) }}</span>
              <button v-if="collapsedView" class="icon-btn" @click="toggleExpand(top.id)">{{ isExpanded(top.id) ? '收起' : '展开' }}</button>
              <button class="icon-btn" title="完整复制（含子块）" @click="copyBlock(top)">⧉ 复制</button>
              <button class="icon-btn" title="内容存为模板" @click="saveBlockAsTemplate(top)">存为模板</button>
              <button class="icon-btn danger" title="删除" @click="deleteBlock(top.id)">删除</button>
            </div>
            <div class="block-time-edit">
              <label>开始
                <input
                  type="datetime-local"
                  :value="toLocalInput(top.work_start_time)"
                  @change="updateBlockTime(top, 'work_start_time', ($event.target as HTMLInputElement).value)"
                />
              </label>
              <label>结束
                <input
                  type="datetime-local"
                  :value="toLocalInput(top.work_end_time)"
                  @change="updateBlockTime(top, 'work_end_time', ($event.target as HTMLInputElement).value)"
                />
              </label>
            </div>
            <div v-if="isExpanded(top.id)" class="block-content">
              <ContentEditor
                :model-value="top.content"
                @update:model-value="updateBlockContent(top, $event)"
              />
            </div>
            <div v-else class="block-summary" title="点击展开" @click="toggleExpand(top.id)">
              {{ summarize(top) }}
            </div>
            <div v-if="isExpanded(top.id)" class="block-actions">
              <button @click="addSubBlock(top.id)">+ 添加子块</button>
            </div>
          </div>

          <!-- 子块 -->
          <div
            v-for="child in childrenOf(top.id)"
            :key="child.id"
            class="block-card sub-block"
            :class="dropClass(child)"
            :data-block-id="child.id"
            :draggable="sortMode === 'doc'"
            @dragstart="onDragStart(child, $event)"
            @dragend="onDragEnd"
            @dragover="onDragOver(child, $event)"
            @drop="onDrop(child, $event)"
          >
            <div class="block-header">
              <span v-if="sortMode === 'doc'" class="drag-handle" title="拖拽排序">⋮⋮</span>
              <input
                :value="child.title ?? ''"
                class="block-title"
                placeholder="无标题"
                @change="updateBlockTitle(child, ($event.target as HTMLInputElement).value)"
              />
              <span class="block-time" :title="'创建时间 ' + formatDateTime(child.created_at)">{{ formatDateTime(child.created_at) }}</span>
              <button v-if="collapsedView" class="icon-btn" @click="toggleExpand(child.id)">{{ isExpanded(child.id) ? '收起' : '展开' }}</button>
              <button class="icon-btn danger" title="删除" @click="deleteBlock(child.id)">删除</button>
            </div>
            <div class="block-time-edit">
              <label>开始
                <input
                  type="datetime-local"
                  :value="toLocalInput(child.work_start_time)"
                  @change="updateBlockTime(child, 'work_start_time', ($event.target as HTMLInputElement).value)"
                />
              </label>
              <label>结束
                <input
                  type="datetime-local"
                  :value="toLocalInput(child.work_end_time)"
                  @change="updateBlockTime(child, 'work_end_time', ($event.target as HTMLInputElement).value)"
                />
              </label>
            </div>
            <div v-if="isExpanded(child.id)" class="block-content">
              <ContentEditor
                :model-value="child.content"
                @update:model-value="updateBlockContent(child, $event)"
              />
            </div>
            <div v-else class="block-summary" title="点击展开" @click="toggleExpand(child.id)">
              {{ summarize(child) }}
            </div>
          </div>
        </template>
      </template>
    </div>
  </div>
  <div v-else class="loading">加载中...</div>
</template>

<style scoped>
.editor-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border);
}
.editor-header h2 { font-size: 1.2rem; }
.editor-header .ce-spacer { flex: 1; }
.save-status { font-size: 0.8rem; color: var(--muted); }
.save-status.saved { color: #4caf50; }
.save-status.saving, .save-status.pending { color: var(--accent); }
.save-status.error { color: var(--danger); }
.icon-btn:disabled { opacity: 0.4; cursor: default; }
.icon-btn:disabled:hover { background: transparent; color: var(--muted); }
.editor-body { padding: 24px; max-width: 800px; margin: 0 auto; }
.add-block-bar { display: flex; gap: 8px; margin-bottom: 20px; }
.add-block-bar input { flex: 1; }
.tpl-select { max-width: 180px; }
.empty { color: var(--muted); text-align: center; padding: 40px; }
.block-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 12px;
  padding: 16px;
  background: var(--bg);
}
.block-card[draggable='true'] { cursor: grab; }
.block-card.sub-block { margin-left: 32px; border-left: 3px solid var(--accent); }
.block-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.drag-handle { color: var(--muted); cursor: grab; font-size: 0.8rem; user-select: none; }
.block-title { border: none; font-weight: 600; font-size: 1rem; flex: 1; background: transparent; min-width: 0; }
.block-title:focus { border: 1px solid var(--border); }
.block-time { color: var(--muted); font-size: 0.8rem; white-space: nowrap; }
.icon-btn {
  border: none; background: transparent; cursor: pointer;
  padding: 2px 6px; font-size: 0.8rem; border-radius: 3px;
  color: var(--muted); white-space: nowrap;
}
.icon-btn:hover { background: var(--border); color: var(--text); }
.icon-btn.danger:hover { color: var(--danger); }
.block-content { margin-bottom: 8px; }
.content-area {
  width: 100%;
  min-height: 60px;
  font-family: 'Cascadia Code', Consolas, monospace;
  font-size: 0.88rem;
  resize: vertical;
}
.block-actions { margin-top: 8px; }
.loading { padding: 40px; text-align: center; color: var(--muted); }

/* 拖拽落点提示 */
.block-card.drop-before { box-shadow: 0 -3px 0 0 var(--accent); }
.block-card.drop-after { box-shadow: 0 3px 0 0 var(--accent); }
.block-card.drop-child { outline: 2px dashed var(--accent); outline-offset: 2px; }

/* 时间轴工具栏（FR-04） */
.timeline-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 0.85rem;
}
.tl-field { color: var(--muted); display: inline-flex; align-items: center; gap: 4px; }
.tl-btn {
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  padding: 2px 10px;
  font-size: 0.8rem;
  border-radius: 3px;
  color: var(--muted);
}
.tl-btn:hover { background: var(--border); color: var(--fg); }
.tl-hint { color: var(--muted); margin-left: auto; font-size: 0.78rem; }

/* 工作时段分组标题 */
.work-group-title {
  font-size: 0.95rem;
  color: var(--accent);
  margin: 20px 0 10px;
  padding-bottom: 4px;
  border-bottom: 1px dashed var(--border);
}
.work-group-title small { color: var(--muted); font-weight: normal; margin-left: 8px; font-size: 0.8rem; }

/* 工作时间编辑行 */
.block-time-edit {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 0.8rem;
  color: var(--muted);
}
.block-time-edit label { display: inline-flex; align-items: center; gap: 4px; }
.block-time-edit input[type='datetime-local'] {
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 4px;
  font-size: 0.8rem;
  color: var(--fg);
  background: var(--bg);
}

/* 折叠视图卡片摘要 */
.block-summary {
  color: var(--muted);
  font-size: 0.85rem;
  cursor: pointer;
  padding: 4px 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.block-summary:hover { color: var(--fg); background: var(--border); border-radius: 3px; }

/* 块定位高亮（搜索跳转/位置恢复） */
.block-card.block-highlight {
  animation: block-flash 2s ease-out;
}
@keyframes block-flash {
  0%, 50% { outline: 2px solid var(--accent); outline-offset: 2px; background: var(--accent-light); }
  100% { outline: none; background: var(--bg); }
}
</style>
