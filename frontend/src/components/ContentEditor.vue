<script setup lang="ts">
/** 内容块编辑器（单块模式）：渲染并编辑 content 行的唯一 ContentBlock。
 * v-model 传 JSON 字符串（'[{item}]'），任何修改立即 emit 保存。
 * 块的删除/移动/复制由行级 ⋯ 菜单负责，块内只保留编辑相关操作。
 */
import { ref, watch } from 'vue'
import { highlight } from '@/utils/highlight'
import { api } from '@/composables/useApi'
import type { ContentBlock } from '@/types'

const props = defineProps<{ modelValue: string; blockId?: number }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()

const item = ref<ContentBlock>(parse(props.modelValue))

function parse(s: string): ContentBlock {
  try {
    const arr = JSON.parse(s || '[]')
    return Array.isArray(arr) && arr[0] ? arr[0] : { type: 'code', content: '' }
  } catch {
    return { type: 'code', content: '' }
  }
}

function flush() {
  emit('update:modelValue', JSON.stringify([item.value]))
}

watch(
  () => props.modelValue,
  v => {
    if (v !== JSON.stringify([item.value])) item.value = parse(v)
  },
)

// ── 编辑/预览状态（code/shell/output 双态，默认编辑态）──
const mode = ref<'edit' | 'view'>('edit')

// ── 折叠/展开（预览态长内容）──
const expanded = ref(false)

// ── 一键复制（复制原文，不含行号）──
const copied = ref(false)

async function copyText(text: string) {
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
  copied.value = true
  setTimeout(() => { copied.value = false }, 1200)
}

// ── 待办清单 ──
function addTodo() {
  if (!item.value.items) item.value.items = []
  item.value.items.push({ text: '', done: false })
  flush()
}

// ── 表格 ──
function addRow() {
  if (!item.value.rows) item.value.rows = [[]]
  const cols = item.value.rows[0]?.length || 2
  item.value.rows.push(Array(cols).fill(''))
  flush()
}

function addCol() {
  if (!item.value.rows) item.value.rows = [['']]
  item.value.rows.forEach(r => r.push(''))
  flush()
}

function removeRow(ri: number) {
  item.value.rows?.splice(ri, 1)
  flush()
}

// ── 图片（附件系统：上传后引用 attachment_id；旧 dataURL 内容保持兼容）──
const zoomSrc = ref<string | null>(null)
const imageUploading = ref(false)
const imageError = ref('')

function imageUrl(): string | null {
  if (item.value.attachment_id) return `/api/attachments/${item.value.attachment_id}/file`
  return item.value.content || null
}

async function onImagePick(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!f) return
  if (imageUploading.value) return
  imageUploading.value = true
  imageError.value = ''
  try {
    const form = new FormData()
    form.append('file', f)
    const att = await api.upload<{ id: number }>('/attachments', form)
    item.value.attachment_id = att.id
    item.value.content = ''
    flush()
  } catch (err) {
    imageError.value = `图片上传失败：${err instanceof Error ? err.message : err}`
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
    <div class="ce-item" :class="`ce-${item.type}`">
      <!-- ── 代码 / 命令 / 输出：一体化头部栏 + 主体 ── -->
      <template v-if="item.type === 'code' || item.type === 'shell' || item.type === 'output'">
        <div class="ce-head">
          <span class="ce-type" :class="'ce-type-' + item.type"><span class="ce-dot"></span>{{ { code: '代码', shell: '命令', output: '输出' }[item.type] }}</span>
          <input
            v-if="item.type === 'code'"
            v-model="item.language"
            class="ce-lang"
            placeholder="语言"
            @change="flush"
          />
          <span class="ce-spacer"></span>
          <div class="ce-seg">
            <button class="ce-op" :class="{ on: mode === 'edit' }" @click="mode = 'edit'">编辑</button>
            <button class="ce-op" :class="{ on: mode === 'view' }" @click="mode = 'view'">预览</button>
          </div>
          <button class="ce-op copy-btn" @click="copyText(item.content || '')">{{ copied ? '已复制 ✓' : '复制' }}</button>
        </div>
        <textarea
          v-if="mode === 'edit'"
          v-model="item.content"
          class="ce-input ce-textarea mono"
          :class="{ 'shell-input': item.type === 'shell' }"
          :placeholder="item.type === 'shell' ? '输入命令...' : item.type === 'output' ? '粘贴终端输出...' : '输入代码...'"
          @input="flush"
          @blur="flush"
        ></textarea>
        <div v-else class="ce-preview-wrap">
          <div class="ce-code-view" :class="{ collapsed: !expanded }">
            <pre class="ce-ln">{{ lineNumbers(item.content || '') }}</pre>
            <pre class="ce-code" v-html="highlight(item.content || '', item.language)"></pre>
          </div>
          <button v-if="!expanded" class="ce-expand" @click="expanded = true">展开 ▾</button>
          <button v-else class="ce-expand" @click="expanded = false">收起 ▴</button>
        </div>
      </template>

      <!-- ── 待办清单 ── -->
      <template v-else-if="item.type === 'todo'">
        <div class="ce-head">
          <span class="ce-type ce-type-todo"><span class="ce-dot"></span>待办</span>
        </div>
        <div class="ce-body">
          <div v-for="(t, ti) in item.items" :key="ti" class="ce-todo-row">
            <input v-model="t.done" type="checkbox" @change="flush" />
            <input v-model="t.text" class="ce-input ce-todo-text" :class="{ done: t.done }" placeholder="待办内容..." @change="flush" />
            <button class="ce-op danger ce-todo-del" title="删除此项" @click="item.items?.splice(ti, 1); flush()">✕</button>
          </div>
          <button class="ce-add" @click="addTodo">＋ 添加待办</button>
        </div>
      </template>

      <!-- ── 表格 ── -->
      <template v-else-if="item.type === 'table'">
        <div class="ce-head">
          <span class="ce-type ce-type-table"><span class="ce-dot"></span>表格</span>
        </div>
        <div class="ce-body">
          <table class="ce-table">
            <tbody>
              <tr v-for="(row, ri) in item.rows" :key="ri" :class="{ head: ri === 0 }">
                <td v-for="(_, ci) in row" :key="ci">
                  <input v-model="row[ci]" class="ce-input ce-cell" @change="flush" />
                </td>
                <td class="ce-row-op"><button class="ce-op danger" title="删行" @click="removeRow(ri)">✕</button></td>
              </tr>
            </tbody>
          </table>
          <div class="ce-table-ops">
            <button class="ce-add" @click="addRow">＋ 行</button>
            <button class="ce-add" @click="addCol">＋ 列</button>
          </div>
        </div>
      </template>

      <!-- ── 图片 ── -->
      <template v-else-if="item.type === 'image'">
        <div class="ce-head">
          <span class="ce-type ce-type-image"><span class="ce-dot"></span>图片</span>
        </div>
        <div class="ce-body ce-image-body">
          <template v-if="imageUrl()">
            <img :src="imageUrl()!" class="ce-image" @click="zoomSrc = imageUrl()" title="点击放大" />
            <label class="ce-replace" :class="{ disabled: imageUploading }">
              {{ imageUploading ? '上传中…' : '更换图片' }}
              <input type="file" accept="image/*" :disabled="imageUploading" @change="onImagePick" />
            </label>
          </template>
          <label v-else class="ce-upload" :class="{ disabled: imageUploading }">
            <span class="ce-upload-icon">🖼</span>
            <span>{{ imageUploading ? '上传中…' : '点击上传图片' }}</span>
            <input type="file" accept="image/*" :disabled="imageUploading" @change="onImagePick" />
          </label>
          <p v-if="imageError" class="ce-image-error">{{ imageError }}</p>
        </div>
      </template>

      <!-- ── text 兜底（新模型正文走 title，不出现于此）── -->
      <template v-else>
        <div class="ce-body">{{ item.content }}</div>
      </template>
    </div>

    <!-- 图片放大遮罩 -->
    <div v-if="zoomSrc" class="ce-zoom" @click="zoomSrc = null">
      <img :src="zoomSrc" />
    </div>
  </div>
</template>

<style scoped>
.content-editor { display: flex; flex-direction: column; flex: 1; min-width: 0; }

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

.ce-textarea {
  width: 100%; min-height: 60px; resize: none; box-sizing: border-box;
  border: none; outline: none; background: transparent; border-radius: 0;
  padding: 10px 12px; font-family: inherit; font-size: 0.88rem; line-height: 1.6;
  color: var(--fg); overflow: hidden;
  field-sizing: content;
}
.ce-textarea::placeholder { color: #c9cdd1; }
.mono { font-family: var(--font-mono); font-size: 0.84rem; }
.shell-input { background: #1f232a; color: #9ece6a; }

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
.ce-image-error { color: var(--danger); font-size: 0.8rem; margin-top: 6px; }

/* 图片放大遮罩 */
.ce-zoom {
  position: fixed; inset: 0; background: rgba(38, 40, 44, 0.8);
  backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center; z-index: 1100; cursor: zoom-out;
}
.ce-zoom img { max-width: 92vw; max-height: 92vh; border-radius: var(--radius); box-shadow: var(--shadow-lg); }
</style>
