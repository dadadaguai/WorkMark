<script setup lang="ts">
/** 附件管理页（FR-07）：查看、搜索、打开、查看所属记录、删除、添加（托管/引用）。 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/composables/useApi'

interface AttachmentRow {
  id: number
  file_name: string
  stored_path: string
  file_size: number | null
  file_type: string | null
  is_reference: number
  created_at: string
  ref_count: number
  path_exists: boolean | null
  used_by: { block_id: number; title: string | null; document_id: number; document_name: string }[]
}

const router = useRouter()
const items = ref<AttachmentRow[]>([])
const query = ref('')
const loading = ref(false)
const errorMsg = ref('')
const adding = ref(false)

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const q = query.value.trim()
    items.value = await api.get<AttachmentRow[]>(`/attachments${q ? `?q=${encodeURIComponent(q)}` : ''}`)
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function formatSize(n: number | null): string {
  if (n === null || n === undefined) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

function openFile(att: AttachmentRow) {
  window.open(`/api/attachments/${att.id}/file`, '_blank')
}

/** 添加附件：选择文件上传（复制到附件目录，不关联块）。 */
async function onFileAdd(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!f) return
  adding.value = true
  try {
    const form = new FormData()
    form.append('file', f)
    await api.upload('/attachments', form)
    await load()
  } catch (err) {
    alert(`上传失败：${err instanceof Error ? err.message : err}`)
  } finally {
    adding.value = false
  }
}

/** 添加引用：大文件不复制，仅记录原始路径。 */
async function addReference() {
  const p = prompt('输入原始文件完整路径（如 D:\\docs\\big.zip）：')
  if (!p) return
  adding.value = true
  try {
    const form = new FormData()
    form.append('is_reference', '1')
    form.append('original_path', p)
    await api.upload('/attachments', form)
    await load()
  } catch (err) {
    alert(`添加引用失败：${err instanceof Error ? err.message : err}`)
  } finally {
    adding.value = false
  }
}

async function removeAttachment(att: AttachmentRow) {
  if (!confirm(`确认删除附件「${att.file_name}」？`)) return
  try {
    await api.del(`/attachments/${att.id}`)
  } catch (err) {
    // 409：仍被引用，后端拒绝删除
    alert(err instanceof Error ? err.message : '删除失败')
    return
  }
  await load()
}

function jumpToBlock(docId: number, blockId: number) {
  router.push(`/document/${docId}?block=${blockId}`)
}
</script>

<template>
  <div class="att-page">
    <header class="att-header">
      <button @click="router.push('/')">← 返回</button>
      <h2>附件管理</h2>
      <span class="att-spacer"></span>
      <label class="att-add-btn" :class="{ disabled: adding }">
        {{ adding ? '处理中…' : '+ 添加文件' }}
        <input type="file" :disabled="adding" hidden @change="onFileAdd" />
      </label>
      <button :disabled="adding" @click="addReference">+ 引用原始路径</button>
    </header>

    <div class="att-toolbar">
      <input v-model="query" class="att-search" placeholder="按文件名搜索附件" @keyup.enter="load" />
      <button class="primary" @click="load">搜索</button>
    </div>

    <div v-if="loading" class="att-empty">加载中…</div>
    <div v-else-if="errorMsg" class="att-empty">{{ errorMsg }}</div>
    <div v-else-if="items.length === 0" class="att-empty">暂无附件。可在内容块中插入图片，或在此添加文件。</div>

    <ul v-else class="att-list">
      <li v-for="att in items" :key="att.id" class="att-item">
        <div class="att-main">
          <span class="att-name" title="点击打开" @click="openFile(att)">{{ att.file_name }}</span>
          <span v-if="att.is_reference && att.path_exists === false" class="att-broken" title="原始路径不存在">
            ⚠ 引用路径失效
          </span>
          <span class="att-meta">{{ att.is_reference ? '引用' : '托管' }}</span>
          <span class="att-meta">{{ att.file_type || '—' }}</span>
          <span class="att-meta">{{ formatSize(att.file_size) }}</span>
          <span class="att-meta">{{ att.created_at }}</span>
        </div>
        <div class="att-refs">
          <template v-if="att.ref_count > 0">
            <span class="att-ref-label">被 {{ att.ref_count }} 条记录引用：</span>
            <button
              v-for="u in att.used_by"
              :key="u.block_id"
              class="att-ref-link"
              @click="jumpToBlock(u.document_id, u.block_id)"
            >
              {{ u.document_name }}{{ u.title ? ' / ' + u.title : '' }}
            </button>
          </template>
          <span v-else class="att-ref-label muted">未被任何记录引用</span>
        </div>
        <div class="att-ops">
          <button @click="openFile(att)">打开</button>
          <button class="danger" @click="removeAttachment(att)">删除</button>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.att-page { max-width: min(1180px, 92vw); margin: 0 auto; padding: 20px 32px 48px; }
.att-header { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.att-header h2 { font-family: var(--font-serif); font-size: 1.3rem; letter-spacing: 0.03em; }
.att-spacer { flex: 1; }
.att-add-btn {
  display: inline-block; cursor: pointer; padding: 6px 14px;
  border: 1px solid var(--border); border-radius: var(--radius); font-size: 0.88rem;
  background: var(--bg);
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.att-add-btn:hover { background: var(--accent-light); color: var(--accent); border-color: var(--accent-line); }
.att-add-btn.disabled { opacity: 0.5; pointer-events: none; }
.att-toolbar { display: flex; gap: 8px; margin-bottom: 18px; }
.att-search { flex: 1; }
.att-empty { color: var(--muted); text-align: center; padding: 48px; }
.att-list { list-style: none; }
.att-item {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 14px 18px;
  margin-bottom: 10px;
  background: var(--bg);
  transition: border-color 0.15s, box-shadow 0.15s;
  animation: wm-fade-up 0.32s both;
}
.att-item:hover { border-color: var(--border-strong); box-shadow: var(--shadow); }
.att-main { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.att-name { font-weight: 600; cursor: pointer; }
.att-name:hover { color: var(--accent); text-decoration: underline; }
.att-broken { color: var(--danger); font-size: 0.82rem; font-weight: 600; }
.att-meta {
  color: var(--muted); font-size: 0.78rem;
  border: 1px solid var(--border); border-radius: 999px; padding: 0 8px;
  background: var(--bg-alt);
  font-variant-numeric: tabular-nums;
}
.att-refs { margin-top: 8px; font-size: 0.85rem; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.att-ref-label { color: var(--muted); }
.att-ref-label.muted { font-style: italic; }
.att-ref-link {
  border: 1px solid var(--accent-line); background: var(--accent-light); color: var(--accent);
  padding: 2px 10px; border-radius: 999px; cursor: pointer; font-size: 0.8rem;
  transition: background 0.15s;
}
.att-ref-link:hover { background: rgba(181, 68, 44, 0.14); text-decoration: none; }
.att-ops { margin-top: 10px; display: flex; gap: 8px; }
.att-ops button { padding: 3px 12px; font-size: 0.85rem; }
</style>
