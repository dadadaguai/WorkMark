<script setup lang="ts">
/** 块内容编辑器：渲染并编辑 ContentBlock[]（text/code/shell/output/todo/table/image）。
 * v-model 传 JSON 字符串（block.content），任何修改立即 emit 保存。
 * 交互对齐飞书/语雀：一体化块头部栏（非浮动胶囊，杜绝裁切）；文本块展示态无边框段落化。
 */
import { ref, watch } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { highlight } from '@/utils/highlight'
import { api } from '@/composables/useApi'
import type { ContentBlock } from '@/types'

const props = defineProps<{ modelValue: string; blockId?: number }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()

const items = ref<ContentBlock[]>(parse(props.modelValue))

function parse(s: string): ContentBlock[] {
  try {
    const arr = JSON.parse(s || '[]')
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

function flush() {
  emit('update:modelValue', JSON.stringify(items.value))
}

watch(
  () => props.modelValue,
  v => {
    if (v !== JSON.stringify(items.value)) items.value = parse(v)
  },
)

// ── 内容块增删移动 ──
const TYPE_LABEL: Record<string, string> = {
  text: '文本', code: '代码', shell: '命令', output: '输出', todo: '待办', table: '表格', image: '图片',
}

function removeItem(i: number) {
  items.value.splice(i, 1)
  flush()
}

function moveItem(i: number, dir: -1 | 1) {
  const j = i + dir
  if (j < 0 || j >= items.value.length) return
  const [it] = items.value.splice(i, 1)
  items.value.splice(j, 0, it)
  flush()
}

// ── 编辑/预览状态（code/shell/output 双态；text 点击预览进入编辑）──
const mode = ref<Record<number, 'edit' | 'view'>>({})

function modeOf(i: number, def: 'edit' | 'view') {
  return mode.value[i] ?? def
}

function setMode(i: number, m: 'edit' | 'view') {
  // 仅切换 UI 状态；mode 不持久化到 content，不触发 emit（避免无变更的幽灵保存）
  mode.value[i] = m
}

// ── 折叠/展开（预览态长内容）──
const expanded = ref<Record<number, boolean>>({})

// ── 一键复制（复制原文，不含行号）──
const copied = ref<Record<number, boolean>>({})

async function copyText(i: number, text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // 剪贴板 API 不可用时退化为选区复制
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
  copied.value[i] = true
  setTimeout(() => { copied.value[i] = false }, 1200)
}

// ── 待办清单 ──
function addTodo(item: ContentBlock) {
  if (!item.items) item.items = []
  item.items.push({ text: '', done: false })
  flush()
}

// ── 表格 ──
function addRow(item: ContentBlock) {
  if (!item.rows) item.rows = [[]]
  const cols = item.rows[0]?.length || 2
  item.rows.push(Array(cols).fill(''))
  flush()
}

function addCol(item: ContentBlock) {
  if (!item.rows) item.rows = [['']]
  item.rows.forEach(r => r.push(''))
  flush()
}

function removeRow(item: ContentBlock, ri: number) {
  item.rows?.splice(ri, 1)
  flush()
}

// ── 图片（附件系统：上传后引用 attachment_id；旧 dataURL 内容保持兼容）──
const zoomSrc = ref<string | null>(null)
const imageUploading = ref(false)

function imageUrl(item: ContentBlock): string | null {
  if (item.attachment_id) return `/api/attachments/${item.attachment_id}/file`
  return item.content || null
}

async function onImagePick(item: ContentBlock, e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!f) return
  if (imageUploading.value) return
  imageUploading.value = true
  try {
    const form = new FormData()
    form.append('file', f)
    if (props.blockId !== undefined) form.append('block_id', String(props.blockId))
    const att = await api.upload<{ id: number }>('/attachments', form)
    item.attachment_id = att.id
    item.content = ''
    flush()
  } catch (err) {
    alert(`图片上传失败：${err instanceof Error ? err.message : err}`)
  } finally {
    imageUploading.value = false
  }
}

// ── 行号列 ──
function lineNumbers(text: string): string {
  const n = text.split('\n').length
  return Array.from({ length: n }, (_, i) => i + 1).join('\n')
}
</script>

<template>
  <div class="content-editor">
    <div v-if="items.length === 0" class="ce-empty">空内容块，从下方添加。</div>

    <div
      v-for="(item, i) in items"
      :key="i"
      class="ce-item"
      :class="[`ce-${item.type}`, { 'ce-plain': item.type === 'text' && modeOf(i, 'view') === 'view' }]"
    >
      <!-- ── 文本块：展示态无边框段落（如飞书文本块），点击进入编辑 ── -->
      <template v-if="item.type === 'text'">
        <div v-if="modeOf(i, 'view') === 'view'" class="ce-text-view">
          <div
            v-if="item.content"
            class="ce-preview md-render"
            :class="{ collapsed: !expanded[i] }"
            v-html="renderMarkdown(item.content)"
            @click="setMode(i, 'edit')"
          ></div>
          <div v-else class="ce-placeholder" @click="setMode(i, 'edit')">（空，点击输入文本，支持 Markdown）</div>
          <!-- hover 悬浮操作（在块内部，不外溢不裁切） -->
          <div class="ce-text-ops" @mousedown.prevent>
            <button class="ce-op" :title="copied[i] ? '已复制' : '复制'" @click="copyText(i, item.content || '')">⧉</button>
            <button class="ce-op" title="上移" @click="moveItem(i, -1)">↑</button>
            <button class="ce-op" title="下移" @click="moveItem(i, 1)">↓</button>
            <button class="ce-op danger" title="删除" @click="removeItem(i)">✕</button>
          </div>
          <button v-if="item.content && !expanded[i]" class="ce-expand" @click="expanded[i] = true">展开 ▾</button>
          <button v-else-if="item.content" class="ce-expand" @click="expanded[i] = false">收起 ▴</button>
        </div>
        <div v-else class="ce-text-edit">
          <textarea
            v-model="item.content"
            v-focus
            class="ce-input ce-textarea"
            placeholder="输入文本，支持 Markdown（# 标题、**粗体**、`代码`、- 列表）..."
            @input="flush"
            @blur="flush(); setMode(i, 'view')"
          ></textarea>
          <div class="ce-edit-hint">失焦自动切回预览 · 支持 Markdown</div>
        </div>
      </template>

      <!-- ── 代码 / 命令 / 输出：一体化头部栏 + 主体 ── -->
      <template v-else-if="item.type === 'code' || item.type === 'shell' || item.type === 'output'">
        <div class="ce-head">
          <span class="ce-type" :class="'ce-type-' + item.type"><span class="ce-dot"></span>{{ TYPE_LABEL[item.type] }}</span>
          <input
            v-if="item.type === 'code'"
            v-model="item.language"
            class="ce-lang"
            placeholder="语言"
            @change="flush"
          />
          <span class="ce-spacer"></span>
          <div class="ce-seg">
            <button class="ce-op" :class="{ on: modeOf(i, 'edit') === 'edit' }" @click="setMode(i, 'edit')">编辑</button>
            <button class="ce-op" :class="{ on: modeOf(i, 'view') === 'view' }" @click="setMode(i, 'view')">预览</button>
          </div>
          <button class="ce-op copy-btn" @click="copyText(i, item.content || '')">{{ copied[i] ? '已复制 ✓' : '复制' }}</button>
          <button class="ce-op" title="上移" @click="moveItem(i, -1)">↑</button>
          <button class="ce-op" title="下移" @click="moveItem(i, 1)">↓</button>
          <button class="ce-op danger" title="删除" @click="removeItem(i)">✕</button>
        </div>
        <textarea
          v-if="modeOf(i, 'edit') === 'edit'"
          v-model="item.content"
          class="ce-input ce-textarea mono"
          :class="{ 'shell-input': item.type === 'shell' }"
          :placeholder="item.type === 'shell' ? '输入命令...' : item.type === 'output' ? '粘贴终端输出...' : '输入代码...'"
          @input="flush"
          @blur="flush"
        ></textarea>
        <div v-else class="ce-preview-wrap">
          <div class="ce-code-view" :class="{ collapsed: !expanded[i] }">
            <pre class="ce-ln">{{ lineNumbers(item.content || '') }}</pre>
            <pre class="ce-code" v-html="highlight(item.content || '', item.language)"></pre>
          </div>
          <button v-if="!expanded[i]" class="ce-expand" @click="expanded[i] = true">展开 ▾</button>
          <button v-else class="ce-expand" @click="expanded[i] = false">收起 ▴</button>
        </div>
      </template>

      <!-- ── 待办清单 ── -->
      <template v-else-if="item.type === 'todo'">
        <div class="ce-head">
          <span class="ce-type ce-type-todo"><span class="ce-dot"></span>待办</span>
          <span class="ce-spacer"></span>
          <button class="ce-op" title="上移" @click="moveItem(i, -1)">↑</button>
          <button class="ce-op" title="下移" @click="moveItem(i, 1)">↓</button>
          <button class="ce-op danger" title="删除" @click="removeItem(i)">✕</button>
        </div>
        <div class="ce-body">
          <div v-for="(t, ti) in item.items" :key="ti" class="ce-todo-row">
            <input v-model="t.done" type="checkbox" @change="flush" />
            <input v-model="t.text" class="ce-input ce-todo-text" :class="{ done: t.done }" placeholder="待办内容..." @change="flush" />
            <button class="ce-op danger ce-todo-del" title="删除此项" @click="item.items?.splice(ti, 1); flush()">✕</button>
          </div>
          <button class="ce-add" @click="addTodo(item)">＋ 添加待办</button>
        </div>
      </template>

      <!-- ── 表格 ── -->
      <template v-else-if="item.type === 'table'">
        <div class="ce-head">
          <span class="ce-type ce-type-table"><span class="ce-dot"></span>表格</span>
          <span class="ce-spacer"></span>
          <button class="ce-op" title="上移" @click="moveItem(i, -1)">↑</button>
          <button class="ce-op" title="下移" @click="moveItem(i, 1)">↓</button>
          <button class="ce-op danger" title="删除" @click="removeItem(i)">✕</button>
        </div>
        <div class="ce-body">
          <table class="ce-table">
            <tbody>
              <tr v-for="(row, ri) in item.rows" :key="ri" :class="{ head: ri === 0 }">
                <td v-for="(_, ci) in row" :key="ci">
                  <input v-model="row[ci]" class="ce-input ce-cell" @change="flush" />
                </td>
                <td class="ce-row-op"><button class="ce-op danger" title="删行" @click="removeRow(item, ri)">✕</button></td>
              </tr>
            </tbody>
          </table>
          <div class="ce-table-ops">
            <button class="ce-add" @click="addRow(item)">＋ 行</button>
            <button class="ce-add" @click="addCol(item)">＋ 列</button>
          </div>
        </div>
      </template>

      <!-- ── 图片 ── -->
      <template v-else-if="item.type === 'image'">
        <div class="ce-head">
          <span class="ce-type ce-type-image"><span class="ce-dot"></span>图片</span>
          <span class="ce-spacer"></span>
          <button class="ce-op" title="上移" @click="moveItem(i, -1)">↑</button>
          <button class="ce-op" title="下移" @click="moveItem(i, 1)">↓</button>
          <button class="ce-op danger" title="删除" @click="removeItem(i)">✕</button>
        </div>
        <div class="ce-body ce-image-body">
          <template v-if="imageUrl(item)">
            <img :src="imageUrl(item)!" class="ce-image" @click="zoomSrc = imageUrl(item)" title="点击放大" />
            <label class="ce-replace" :class="{ disabled: imageUploading }">
              {{ imageUploading ? '上传中…' : '更换图片' }}
              <input type="file" accept="image/*" :disabled="imageUploading" @change="onImagePick(item, $event)" />
            </label>
          </template>
          <label v-else class="ce-upload" :class="{ disabled: imageUploading }">
            <span class="ce-upload-icon">🖼</span>
            <span>{{ imageUploading ? '上传中…' : '点击上传图片' }}</span>
            <input type="file" accept="image/*" :disabled="imageUploading" @change="onImagePick(item, $event)" />
          </label>
        </div>
      </template>
    </div>

    <!-- 图片放大遮罩 -->
    <div v-if="zoomSrc" class="ce-zoom" @click="zoomSrc = null">
      <img :src="zoomSrc" />
    </div>
  </div>
</template>

<style scoped>
.content-editor { display: flex; flex-direction: column; gap: 10px; }
.ce-empty { color: var(--muted); font-size: 0.85rem; padding: 8px; }

/* ── 块容器：卡片式 + 一体化头部栏（无浮动元素，彻底告别裁切）── */
.ce-item {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── 头部栏：类型标识 + 语言 + 操作（飞书代码块式）── */
.ce-head {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  min-height: 34px;
  border-bottom: 1px solid var(--border);
  background: rgba(38, 40, 44, 0.025);
}
.ce-type {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  letter-spacing: 0.04em;
}
.ce-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.ce-type-text .ce-dot { background: #8a8f98; }
.ce-type-code .ce-dot { background: #4a5d8f; }
.ce-type-shell .ce-dot { background: #b07916; }
.ce-type-output .ce-dot { background: #2e7d51; }
.ce-type-todo .ce-dot { background: #3a6fd8; }
.ce-type-table .ce-dot { background: #8f6db4; }
.ce-type-image .ce-dot { background: #2e8b77; }
.ce-lang {
  width: 76px;
  font-size: 12px;
  padding: 2px 6px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--muted);
}
.ce-lang:hover { border-color: var(--border); }
.ce-lang:focus { border-color: var(--accent-line); box-shadow: none; }
.ce-spacer { flex: 1; }

/* 幽灵操作按钮 */
.ce-op {
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 3px 8px;
  font-size: 12px;
  border-radius: 4px;
  color: var(--muted);
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}
.ce-op:hover { background: rgba(38, 40, 44, 0.07); color: var(--fg); }
.ce-op.danger:hover { background: rgba(197, 50, 43, 0.09); color: var(--danger); }

/* 编辑/预览迷你分段 */
.ce-seg {
  display: inline-flex;
  gap: 2px;
  background: rgba(38, 40, 44, 0.06);
  border-radius: 6px;
  padding: 2px;
}
.ce-seg .ce-op { padding: 2px 10px; border-radius: 4px; }
.ce-seg .ce-op.on { background: #fff; color: var(--fg); box-shadow: 0 1px 2px rgba(38, 40, 44, 0.1); }
.copy-btn { white-space: nowrap; }

/* ── 输入区 ── */
.ce-input {
  border: none;
  border-radius: 0;
  padding: 10px 12px;
  font-size: 0.88rem;
  background: var(--bg);
  width: 100%;
}
.ce-input:focus { box-shadow: none; }
.ce-textarea { width: 100%; min-height: 70px; resize: vertical; box-sizing: border-box; }
.mono { font-family: var(--font-mono); font-size: 0.84rem; }
.shell-input { background: #1f232a; color: #9ece6a; }

/* ── 文本块：展示态完全无边框（段落式），hover 轻灰 ── */
.ce-item.ce-plain { border: none; background: transparent; }
.ce-text-view { position: relative; border-radius: var(--radius); }
.ce-text-view:hover { background: var(--bg-hover); }
.ce-preview { cursor: text; min-height: 24px; padding: 4px 8px; border-radius: var(--radius); }
.ce-placeholder {
  color: var(--faint); font-size: 0.85rem; cursor: text;
  padding: 8px 8px; min-height: 24px; border-radius: var(--radius);
}
.ce-preview.collapsed { max-height: 300px; overflow: hidden; }

/* 文本块 hover 悬浮操作：块内部右上角，不外溢 */
.ce-text-ops {
  position: absolute;
  top: 2px;
  right: 2px;
  display: inline-flex;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 1px 2px;
  box-shadow: var(--shadow);
  opacity: 0;
  transition: opacity 0.15s;
  z-index: 2;
}
.ce-text-view:hover .ce-text-ops { opacity: 1; }
.ce-text-ops .ce-op { padding: 2px 7px; }

/* 文本块编辑态：朱砂细环聚焦框 */
.ce-text-edit {
  border: 1px solid var(--accent-line);
  border-radius: var(--radius-lg);
  background: var(--bg);
  box-shadow: 0 0 0 3px rgba(181, 68, 44, 0.06);
  overflow: hidden;
}
.ce-edit-hint { font-size: 11px; color: var(--faint); padding: 0 12px 8px; }

/* Markdown 渲染 */
.md-render :deep(p) { margin: 4px 0; white-space: pre-wrap; word-break: break-word; }
.md-render :deep(p.md-gap) { height: 0.5em; }
.md-render :deep(h2), .md-render :deep(h3), .md-render :deep(h4) { margin: 10px 0 4px; }
.md-render :deep(pre.md-pre) {
  background: var(--bg-alt); border: 1px solid var(--border); padding: 10px 12px; border-radius: var(--radius); overflow-x: auto;
  font-family: var(--font-mono); font-size: 0.84rem; white-space: pre-wrap;
}
.md-render :deep(code) { font-family: var(--font-mono); }
.md-render :deep(ul), .md-render :deep(ol) { margin: 4px 0; padding-left: 24px; }

/* 展开/收起：幽灵分隔线按钮 */
.ce-expand {
  display: block;
  width: 100%;
  border: none;
  border-top: 1px dashed var(--border);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 0.78rem;
  padding: 4px;
}
.ce-expand:hover { color: var(--fg); background: var(--bg-hover); }
.ce-plain .ce-expand { border: none; width: auto; align-self: center; font-size: 11px; color: var(--faint); padding: 2px 10px; }
.ce-plain .ce-expand:hover { color: var(--accent); background: var(--accent-light); }

/* ── 代码预览：深色 + 行号 ── */
.ce-preview-wrap { position: relative; }
.ce-code-view {
  display: flex; background: #1f232a; color: #c8ccd8;
  font-family: var(--font-mono);
  overflow: hidden auto;
}
.ce-code-view.collapsed { max-height: 300px; }
.ce-code-view pre { margin: 0; padding: 10px 12px; font-size: 0.84rem; line-height: 1.6; }
.ce-ln { color: #4d5361; text-align: right; user-select: none; min-width: 36px; border-right: 1px solid rgba(255, 255, 255, 0.06); }
.ce-code { flex: 1; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }
.ce-code :deep(.hl-comment) { color: #5d6575; font-style: italic; }
.ce-code :deep(.hl-string) { color: #9ece6a; }
.ce-code :deep(.hl-number) { color: #ff9e64; }
.ce-code :deep(.hl-keyword) { color: #b48ead; }

/* ── 主体留白容器（todo/表格/图片）── */
.ce-body { padding: 8px 12px; display: flex; flex-direction: column; gap: 6px; }

/* 待办 */
.ce-todo-row { display: flex; align-items: center; gap: 8px; }
.ce-todo-row input[type='checkbox'] { width: auto; accent-color: var(--accent); }
.ce-todo-text { flex: 1; padding: 4px 8px; }
.ce-todo-text.done { text-decoration: line-through; color: var(--muted); }
.ce-todo-del { opacity: 0; transition: opacity 0.15s; }
.ce-todo-row:hover .ce-todo-del { opacity: 1; }
.ce-add {
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 4px;
  width: fit-content;
  cursor: pointer;
}
.ce-add:hover { color: var(--accent); background: var(--accent-light); }

/* 表格 */
.ce-table { border-collapse: collapse; width: 100%; }
.ce-table td { border: 1px solid var(--border); padding: 2px; }
.ce-table tr.head td { background: var(--bg-alt); }
.ce-cell { border: none; width: 100%; min-width: 80px; font-size: 0.85rem; padding: 4px 8px; }
.ce-cell:focus { box-shadow: none; }
.ce-row-op { border: none !important; width: 30px; text-align: center; }
.ce-table-ops { display: flex; gap: 6px; }

/* 图片 */
.ce-image-body { align-items: flex-start; }
.ce-image { max-width: 100%; max-height: 300px; cursor: zoom-in; border-radius: var(--radius); display: block; border: 1px solid var(--border); }
.ce-replace {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 3px 12px;
  cursor: pointer;
  margin-top: 6px;
  width: fit-content;
}
.ce-replace:hover { color: var(--fg); border-color: var(--border-strong); background: var(--bg-alt); }
.ce-replace.disabled { opacity: 0.5; cursor: default; }
.ce-replace input, .ce-upload input { display: none; }
.ce-upload {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 22px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-lg);
  color: var(--muted);
  font-size: 0.85rem;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.ce-upload:hover { border-color: var(--accent-line); background: var(--accent-light); color: var(--accent); }
.ce-upload.disabled { opacity: 0.5; cursor: default; }
.ce-upload-icon { font-size: 22px; }

/* 图片放大遮罩 */
.ce-zoom {
  position: fixed; inset: 0; background: rgba(38, 40, 44, 0.8);
  backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center; z-index: 1100; cursor: zoom-out;
}
.ce-zoom img { max-width: 92vw; max-height: 92vh; border-radius: var(--radius); box-shadow: var(--shadow-lg); }
</style>
