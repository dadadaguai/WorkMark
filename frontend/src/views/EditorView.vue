<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/composables/useApi'
import type { Document, Block } from '@/types'

const props = defineProps<{ id: string }>()
const router = useRouter()

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
})

async function reloadBlocks() {
  blocks.value = await api.get<Block[]>(`/blocks/document/${props.id}`)
}

const topLevelBlocks = computed(() =>
  blocks.value
    .filter(b => b.parent_id === null)
    .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
)

function childrenOf(parentId: number): Block[] {
  return blocks.value
    .filter(b => b.parent_id === parentId)
    .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
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

async function updateBlockTitle(block: Block, title: string) {
  await api.put(`/blocks/${block.id}`, { title })
  block.title = title
}

async function updateBlockContent(block: Block, content: string) {
  await api.put(`/blocks/${block.id}`, { content })
  block.content = content
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

      <div v-if="topLevelBlocks.length === 0" class="empty">
        暂无任务块，添加第一个开始记录。
      </div>

      <template v-for="top in topLevelBlocks" :key="top.id">
        <!-- 顶层任务块 -->
        <div
          class="block-card"
          :class="dropClass(top)"
          draggable="true"
          @dragstart="onDragStart(top, $event)"
          @dragend="onDragEnd"
          @dragover="onDragOver(top, $event)"
          @drop="onDrop(top, $event)"
        >
          <div class="block-header">
            <span class="drag-handle" title="拖拽排序">⋮⋮</span>
            <input
              :value="top.title ?? ''"
              class="block-title"
              placeholder="无标题"
              @change="updateBlockTitle(top, ($event.target as HTMLInputElement).value)"
            />
            <span class="block-time">{{ top.created_at }}</span>
            <button class="icon-btn" title="完整复制（含子块）" @click="copyBlock(top)">⧉ 复制</button>
            <button class="icon-btn" title="内容存为模板" @click="saveBlockAsTemplate(top)">存为模板</button>
            <button class="icon-btn danger" title="删除" @click="deleteBlock(top.id)">删除</button>
          </div>
          <div class="block-content">
            <textarea
              :value="top.content"
              @change="updateBlockContent(top, ($event.target as HTMLTextAreaElement).value)"
              placeholder="输入内容..."
              class="content-area"
            ></textarea>
          </div>
          <div class="block-actions">
            <button @click="addSubBlock(top.id)">+ 添加子块</button>
          </div>
        </div>

        <!-- 子块 -->
        <div
          v-for="child in childrenOf(top.id)"
          :key="child.id"
          class="block-card sub-block"
          :class="dropClass(child)"
          draggable="true"
          @dragstart="onDragStart(child, $event)"
          @dragend="onDragEnd"
          @dragover="onDragOver(child, $event)"
          @drop="onDrop(child, $event)"
        >
          <div class="block-header">
            <span class="drag-handle" title="拖拽排序">⋮⋮</span>
            <input
              :value="child.title ?? ''"
              class="block-title"
              placeholder="无标题"
              @change="updateBlockTitle(child, ($event.target as HTMLInputElement).value)"
            />
            <span class="block-time">{{ child.created_at }}</span>
            <button class="icon-btn danger" title="删除" @click="deleteBlock(child.id)">删除</button>
          </div>
          <div class="block-content">
            <textarea
              :value="child.content"
              @change="updateBlockContent(child, ($event.target as HTMLTextAreaElement).value)"
              placeholder="输入内容..."
              class="content-area"
            ></textarea>
          </div>
        </div>
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
</style>
