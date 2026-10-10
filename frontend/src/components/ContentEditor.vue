<script setup lang="ts">
/** 块内容编辑器：渲染并编辑 ContentBlock[]（text/code/shell/output/todo/table/image）。
 * v-model 传 JSON 字符串（block.content），任何修改立即 emit 保存。
 */
import { ref, watch } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { highlight } from '@/utils/highlight'
import type { ContentBlock } from '@/types'

const props = defineProps<{ modelValue: string }>()
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

function addBlock(type: ContentBlock['type']) {
  const base: ContentBlock = { type }
  if (type === 'text') base.content = ''
  if (type === 'code') { base.content = ''; base.language = 'python' }
  if (type === 'shell' || type === 'output') base.content = ''
  if (type === 'todo') base.items = [{ text: '新待办', done: false }]
  if (type === 'table') base.rows = [['列1', '列2'], ['', '']]
  if (type === 'image') base.content = ''
  items.value.push(base)
  flush()
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
  mode.value[i] = m
  flush()
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

// ── 图片（dataURL，≤2MB；后续迁移到附件系统）──
const zoomSrc = ref<string | null>(null)

function onImagePick(item: ContentBlock, e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  if (f.size > 2 * 1024 * 1024) {
    alert('图片不能超过 2MB')
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    item.content = reader.result as string
    flush()
  }
  reader.readAsDataURL(f)
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

    <div v-for="(item, i) in items" :key="i" class="ce-item" :class="`ce-${item.type}`">
      <div class="ce-toolbar">
        <span class="ce-badge">{{ TYPE_LABEL[item.type] || item.type }}</span>
        <input
          v-if="item.type === 'code'"
          v-model="item.language"
          class="ce-lang"
          placeholder="语言"
          @change="flush"
        />
        <span class="ce-spacer"></span>
        <button class="ce-btn" title="上移" @click="moveItem(i, -1)">↑</button>
        <button class="ce-btn" title="下移" @click="moveItem(i, 1)">↓</button>
        <button class="ce-btn danger" title="删除" @click="removeItem(i)">✕</button>
      </div>

      <!-- 文本：预览 ⇄ 编辑 -->
      <template v-if="item.type === 'text'">
        <div v-if="modeOf(i, 'view') === 'view'" class="ce-preview-wrap">
          <div
            class="ce-preview md-render"
            :class="{ collapsed: !expanded[i] }"
            v-html="renderMarkdown(item.content || '')"
            @click="setMode(i, 'edit')"
          ></div>
          <button v-if="!expanded[i]" class="ce-expand" @click="expanded[i] = true">展开</button>
          <button v-else class="ce-expand" @click="expanded[i] = false">收起</button>
        </div>
        <textarea
          v-else
          v-model="item.content"
          class="ce-input ce-textarea"
          placeholder="输入文本，支持 Markdown（# 标题、**粗体**、`代码`、- 列表）..."
          @blur="flush(); setMode(i, 'view')"
        ></textarea>
      </template>

      <!-- 代码 / 命令 / 输出 -->
      <template v-else-if="item.type === 'code' || item.type === 'shell' || item.type === 'output'">
        <div class="ce-mode-bar">
          <button class="ce-btn" :class="{ on: modeOf(i, 'edit') === 'edit' }" @click="setMode(i, 'edit')">编辑</button>
          <button class="ce-btn" :class="{ on: modeOf(i, 'view') === 'view' }" @click="setMode(i, 'view')">预览</button>
          <span class="ce-spacer"></span>
          <button class="ce-btn" @click="copyText(i, item.content || '')">{{ copied[i] ? '已复制' : '复制' }}</button>
        </div>
        <textarea
          v-if="modeOf(i, 'edit') === 'edit'"
          v-model="item.content"
          class="ce-input ce-textarea mono"
          :class="{ 'shell-input': item.type === 'shell' }"
          :placeholder="item.type === 'shell' ? '输入命令...' : item.type === 'output' ? '粘贴终端输出...' : '输入代码...'"
          @blur="flush"
        ></textarea>
        <div v-else class="ce-preview-wrap">
          <div class="ce-code-view" :class="{ collapsed: !expanded[i] }">
            <pre class="ce-ln">{{ lineNumbers(item.content || '') }}</pre>
            <pre class="ce-code" v-html="highlight(item.content || '', item.language)"></pre>
          </div>
          <button v-if="!expanded[i]" class="ce-expand" @click="expanded[i] = true">展开</button>
          <button v-else class="ce-expand" @click="expanded[i] = false">收起</button>
        </div>
      </template>

      <!-- 待办清单 -->
      <template v-else-if="item.type === 'todo'">
        <div v-for="(t, ti) in item.items" :key="ti" class="ce-todo-row">
          <input v-model="t.done" type="checkbox" @change="flush" />
          <input v-model="t.text" class="ce-input ce-todo-text" :class="{ done: t.done }" placeholder="待办内容..." @change="flush" />
          <button class="ce-btn danger" @click="item.items?.splice(ti, 1); flush()">✕</button>
        </div>
        <button class="ce-btn" @click="addTodo(item)">+ 添加待办</button>
      </template>

      <!-- 表格 -->
      <template v-else-if="item.type === 'table'">
        <table class="ce-table">
          <tbody>
            <tr v-for="(row, ri) in item.rows" :key="ri" :class="{ head: ri === 0 }">
              <td v-for="(_, ci) in row" :key="ci">
                <input v-model="row[ci]" class="ce-input ce-cell" @change="flush" />
              </td>
              <td class="ce-row-op"><button class="ce-btn danger" title="删行" @click="removeRow(item, ri)">✕</button></td>
            </tr>
          </tbody>
        </table>
        <div class="ce-table-ops">
          <button class="ce-btn" @click="addRow(item)">+ 行</button>
          <button class="ce-btn" @click="addCol(item)">+ 列</button>
        </div>
      </template>

      <!-- 图片 -->
      <template v-else-if="item.type === 'image'">
        <img v-if="item.content" :src="item.content" class="ce-image" @click="zoomSrc = item.content" title="点击放大" />
        <div v-else class="ce-image-empty">
          <input type="file" accept="image/*" @change="onImagePick(item, $event)" />
        </div>
        <div v-if="item.content" class="ce-mode-bar">
          <input type="file" accept="image/*" @change="onImagePick(item, $event)" />
        </div>
      </template>
    </div>

    <!-- 添加内容块工具条 -->
    <div class="ce-add-bar">
      <button v-for="t in (['text','code','shell','output','todo','table','image'] as const)" :key="t" class="ce-btn" @click="addBlock(t)">
        + {{ TYPE_LABEL[t] }}
      </button>
    </div>

    <!-- 图片放大遮罩 -->
    <div v-if="zoomSrc" class="ce-zoom" @click="zoomSrc = null">
      <img :src="zoomSrc" />
    </div>
  </div>
</template>

<style scoped>
.content-editor { display: flex; flex-direction: column; gap: 8px; }
.ce-empty { color: var(--muted); font-size: 0.85rem; padding: 8px; }
.ce-item { border: 1px solid var(--border); border-radius: var(--radius); padding: 8px; background: var(--bg); }
.ce-item.ce-shell { border-left: 3px solid #d19a66; }
.ce-item.ce-output { border-left: 3px solid #89ca78; }
.ce-item.ce-code { border-left: 3px solid #7aa2f7; }
.ce-toolbar { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.ce-badge {
  font-size: 0.72rem; padding: 1px 8px; border-radius: 10px;
  background: var(--accent-light); color: var(--accent); font-weight: 600;
}
.ce-lang { width: 80px; font-size: 0.8rem; padding: 2px 6px; border: 1px solid var(--border); border-radius: 3px; }
.ce-spacer { flex: 1; }
.ce-btn {
  border: none; background: transparent; cursor: pointer;
  padding: 2px 8px; font-size: 0.78rem; border-radius: 3px; color: var(--muted);
}
.ce-btn:hover { background: var(--border); color: var(--text); }
.ce-btn.danger:hover { color: var(--danger); }
.ce-btn.on { background: var(--accent-light); color: var(--accent); }
.ce-mode-bar { display: flex; gap: 4px; margin-bottom: 4px; align-items: center; }
.ce-input { border: 1px solid var(--border); border-radius: 3px; padding: 6px 8px; font-size: 0.88rem; background: var(--bg); }
.ce-textarea { width: 100%; min-height: 70px; resize: vertical; box-sizing: border-box; }
.mono { font-family: 'Cascadia Code', Consolas, monospace; font-size: 0.84rem; }
.shell-input { background: #1a1b26; color: #9ece6a; }
.ce-preview-wrap { position: relative; }
.ce-preview { cursor: text; min-height: 24px; padding: 4px 2px; }
.ce-preview:empty::before { content: '（空，点击输入）'; color: var(--muted); font-size: 0.85rem; }
.ce-preview.collapsed { max-height: 300px; overflow: hidden; }
.md-render :deep(p) { margin: 4px 0; white-space: pre-wrap; word-break: break-word; }
.md-render :deep(p.md-gap) { height: 0.5em; }
.md-render :deep(h2), .md-render :deep(h3), .md-render :deep(h4) { margin: 8px 0 4px; }
.md-render :deep(pre.md-pre) {
  background: var(--bg-alt); padding: 8px; border-radius: 4px; overflow-x: auto;
  font-family: 'Cascadia Code', Consolas, monospace; font-size: 0.84rem; white-space: pre-wrap;
}
.md-render :deep(ul), .md-render :deep(ol) { margin: 4px 0; padding-left: 24px; }
.ce-expand {
  display: block; width: 100%; border: none; border-top: 1px dashed var(--border);
  background: linear-gradient(transparent, var(--bg)); color: var(--accent);
  cursor: pointer; font-size: 0.78rem; padding: 4px;
}
.ce-code-view {
  display: flex; background: #1a1b26; color: #c0caf5;
  border-radius: 4px; overflow: hidden; font-family: 'Cascadia Code', Consolas, monospace;
}
.ce-code-view.collapsed { max-height: 300px; }
.ce-code-view pre { margin: 0; padding: 8px 10px; font-size: 0.84rem; line-height: 1.5; }
.ce-ln { color: #444a6b; text-align: right; user-select: none; min-width: 36px; }
.ce-code { flex: 1; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }
.ce-code :deep(.hl-comment) { color: #565f89; font-style: italic; }
.ce-code :deep(.hl-string) { color: #9ece6a; }
.ce-code :deep(.hl-number) { color: #ff9e64; }
.ce-code :deep(.hl-keyword) { color: #bb9af7; }
.ce-todo-row { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.ce-todo-text { flex: 1; }
.ce-todo-text.done { text-decoration: line-through; color: var(--muted); }
.ce-table { border-collapse: collapse; width: 100%; }
.ce-table td { border: 1px solid var(--border); padding: 2px; }
.ce-table tr.head td { background: var(--bg-alt); }
.ce-cell { border: none; width: 100%; min-width: 80px; font-size: 0.85rem; }
.ce-row-op { border: none !important; width: 30px; text-align: center; }
.ce-table-ops { display: flex; gap: 6px; margin-top: 4px; }
.ce-image { max-width: 100%; max-height: 300px; cursor: zoom-in; border-radius: 4px; display: block; }
.ce-image-empty { padding: 8px; color: var(--muted); font-size: 0.85rem; }
.ce-add-bar { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.ce-zoom {
  position: fixed; inset: 0; background: rgba(0, 0, 0, 0.75);
  display: flex; align-items: center; justify-content: center; z-index: 1100; cursor: zoom-out;
}
.ce-zoom img { max-width: 92vw; max-height: 92vh; border-radius: 4px; }
</style>
