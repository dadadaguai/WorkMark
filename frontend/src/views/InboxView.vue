<script setup lang="ts">
/** 快速记录 / 收件箱（FR-09）：快速输入或粘贴内容进入待整理收件箱，
 * 之后可移动到任务文档、复制到任务文档、关联文档保留原记录，或继续独立存在。
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/composables/useApi'
import type { InboxItem, Document } from '@/types'

const router = useRouter()

const items = ref<InboxItem[]>([])
const docs = ref<Document[]>([])
const draft = ref('')
const adding = ref(false)
const loading = ref(false)
const errorMsg = ref('')

const STATUS_LABEL: Record<string, string> = {
  pending: '待整理', moved: '已移动', copied: '已复制', linked: '已关联',
}

async function load() {
  loading.value = true
  try {
    items.value = await api.get<InboxItem[]>('/inbox')
    errorMsg.value = ''
  } catch (err) {
    errorMsg.value = `加载失败：${err instanceof Error ? err.message : err}`
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await load()
  docs.value = await api.get<Document[]>('/documents')
})

// ── 快速添加（Ctrl+Enter 提交）──
async function addItem() {
  const content = draft.value.trim()
  if (!content || adding.value) return
  adding.value = true
  try {
    await api.post<InboxItem>('/inbox', { content })
    draft.value = ''
    await load()
  } catch (err) {
    alert(`添加失败：${err instanceof Error ? err.message : err}`)
  } finally {
    adding.value = false
  }
}

function onDraftKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    addItem()
  }
}

// ── 整理：移动 / 复制 / 关联（共用选文档对话框）──
const organize = ref<{ item: InboxItem; mode: 'move' | 'copy' | 'link' } | null>(null)
const targetDocId = ref<number | null>(null)
const organizing = ref(false)

const MODE_TEXT: Record<'move' | 'copy' | 'link', string> = {
  move: '移动到任务文档',
  copy: '复制到任务文档',
  link: '关联任务文档（保留原记录）',
}

function openOrganize(item: InboxItem, mode: 'move' | 'copy' | 'link') {
  organize.value = { item, mode }
  targetDocId.value = docs.value.length ? docs.value[0].id : null
}

async function confirmOrganize() {
  if (!organize.value || targetDocId.value === null) return
  const { item, mode } = organize.value
  organizing.value = true
  try {
    await api.post(`/inbox/${item.id}/${mode}`, { document_id: targetDocId.value })
    organize.value = null
    await load()
  } catch (err) {
    alert(`操作失败：${err instanceof Error ? err.message : err}`)
  } finally {
    organizing.value = false
  }
}

async function removeItem(item: InboxItem) {
  if (!confirm('确认删除此收件箱条目？不影响已移动/复制产生的任务块。')) return
  await api.del(`/inbox/${item.id}`)
  await load()
}

function goDocument(docId: number | null, blockId?: number) {
  if (docId === null) return
  router.push(blockId ? `/document/${docId}?block=${blockId}` : `/document/${docId}`)
}
</script>

<template>
  <div class="inbox-page">
    <header class="inbox-header">
      <button @click="router.push('/')">← 返回</button>
      <h2>快速记录 / 收件箱</h2>
    </header>

    <!-- 快速输入：文本 / 粘贴（保留换行缩进，不做格式识别） -->
    <div class="inbox-compose">
      <textarea
        v-model="draft"
        class="inbox-input"
        rows="4"
        placeholder="快速输入或直接粘贴内容（多行文本、代码、命令、输出均可，原样保留）…&#10;Ctrl+Enter 快速添加"
        @keydown="onDraftKeydown"
      ></textarea>
      <div class="compose-ops">
        <span class="compose-hint">粘贴时保留换行与缩进</span>
        <button class="primary" :disabled="!draft.trim() || adding" @click="addItem">
          {{ adding ? '添加中…' : '添加到收件箱' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="inbox-empty">加载中…</div>
    <div v-else-if="errorMsg" class="inbox-empty">{{ errorMsg }}</div>
    <div v-else-if="items.length === 0" class="inbox-empty">收件箱为空。上方输入内容或粘贴剪贴板，随时快速记录。</div>

    <ul v-else class="inbox-list">
      <li v-for="item in items" :key="item.id" class="inbox-item">
        <div class="inbox-item-head">
          <span class="inbox-status" :class="item.status">{{ STATUS_LABEL[item.status] || item.status }}</span>
          <span class="inbox-time">{{ item.created_at }}</span>
          <span class="inbox-spacer"></span>
          <button v-if="item.status === 'pending'" @click="openOrganize(item, 'move')">移动到文档</button>
          <button v-if="item.status === 'pending'" @click="openOrganize(item, 'copy')">复制到文档</button>
          <button v-if="item.status === 'pending'" @click="openOrganize(item, 'link')">关联文档</button>
          <button class="danger" @click="removeItem(item)">删除</button>
        </div>
        <div class="inbox-content">{{ item.content }}</div>
        <div v-if="item.target_document_name" class="inbox-target">
          {{ item.status === 'linked' ? '已关联：' : '去向：' }}
          <button class="inbox-doc-link" @click="goDocument(item.target_document_id, item.block_id)">
            {{ item.target_document_name }}
          </button>
        </div>
      </li>
    </ul>

    <!-- 选文档对话框（移动 / 复制 / 关联共用） -->
    <div v-if="organize" class="dialog-overlay" @click.self="organize = null">
      <div class="dialog">
        <h3 class="dialog-title">{{ MODE_TEXT[organize.mode] }}</h3>
        <p class="dialog-message">
          {{ organize.mode === 'move' ? '条目将转换为目标文档的顶层任务块，并从收件箱标记为已移动。'
             : organize.mode === 'copy' ? '条目将复制为目标文档的顶层任务块，收件箱保留原记录。'
             : '仅记录关联关系，收件箱条目继续独立存在。' }}
        </p>
        <select v-model.number="targetDocId" class="doc-select">
          <option v-for="d in docs" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
        <div class="dialog-actions">
          <button @click="organize = null">取消</button>
          <button class="primary" :disabled="targetDocId === null || organizing" @click="confirmOrganize">
            {{ organizing ? '处理中…' : '确认' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.inbox-page { max-width: min(1180px, 92vw); margin: 0 auto; padding: 20px 32px 48px; }
.inbox-header { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.inbox-header h2 { font-family: var(--font-serif); font-size: 1.3rem; letter-spacing: 0.03em; }

.inbox-compose {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 14px;
  margin-bottom: 20px;
  background: var(--bg);
  box-shadow: var(--shadow);
}
.inbox-input {
  width: 100%;
  box-sizing: border-box;
  font-family: inherit;
  font-size: 0.92rem;
  line-height: 1.7;
  resize: vertical;
  min-height: 80px;
}
.compose-ops { display: flex; align-items: center; gap: 12px; margin-top: 10px; }
.compose-hint { color: var(--muted); font-size: 0.82rem; flex: 1; }

.inbox-empty { color: var(--muted); text-align: center; padding: 48px; }
.inbox-list { list-style: none; }
.inbox-item {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 14px 18px;
  margin-bottom: 10px;
  background: var(--bg);
  transition: border-color 0.15s, box-shadow 0.15s;
  animation: wm-fade-up 0.32s both;
}
.inbox-item:hover { border-color: var(--border-strong); box-shadow: var(--shadow); }
.inbox-item-head { display: flex; align-items: center; gap: 8px; }
.inbox-spacer { flex: 1; }
.inbox-status {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 1px 9px;
  border-radius: 999px;
  background: var(--bg-alt);
  border: 1px solid var(--border);
  color: var(--muted);
  letter-spacing: 0.04em;
}
.inbox-status.pending { background: var(--accent-light); border-color: var(--accent-line); color: var(--accent); }
.inbox-time { color: var(--muted); font-size: 0.8rem; font-variant-numeric: tabular-nums; }
.inbox-item-head button { padding: 2px 10px; font-size: 0.85rem; }

.inbox-content {
  margin-top: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.9rem;
  line-height: 1.7;
}
.inbox-target { margin-top: 8px; font-size: 0.85rem; color: var(--muted); display: flex; align-items: center; gap: 6px; }
.inbox-doc-link {
  border: 1px solid var(--accent-line); background: var(--accent-light); color: var(--accent);
  padding: 2px 10px; border-radius: 999px; cursor: pointer; font-size: 0.8rem;
  transition: background 0.15s;
}
.inbox-doc-link:hover { background: rgba(181, 68, 44, 0.14); text-decoration: none; }

/* 选文档对话框 */
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
  min-width: 360px;
  max-width: 480px;
  box-shadow: var(--shadow-lg);
  animation: wm-pop 0.18s ease-out;
}
.dialog-title { font-family: var(--font-serif); font-size: 1.15rem; font-weight: 700; margin-bottom: 8px; }
.dialog-message { color: var(--muted); margin-bottom: 12px; font-size: 0.9rem; }
.doc-select { width: 100%; padding: 7px 10px; margin-bottom: 16px; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>
