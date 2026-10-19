<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { api } from '@/composables/useApi'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import type { Folder, Document, SearchResult } from '@/types'

const router = useRouter()
const store = useAppStore()

// 新建表单
const showNewFolder = ref(false)
const newFolderName = ref('')
const newDocName = ref('')

// 重命名（文件夹内联编辑）
const editingFolderId = ref<number | null>(null)
const editingFolderName = ref('')

// 重命名（文档）
const editingDocId = ref<number | null>(null)
const editingDocName = ref('')

// 删除确认对话框
const deleteTarget = ref<{ type: 'folder' | 'document'; id: number; name: string } | null>(null)
const deleteImpact = ref<{ label: string; value: number | string }[]>([])

// 移动文档对话框
const moveTargetDoc = ref<{ id: number; name: string } | null>(null)
const moveTargetFolderId = ref<number | null>(null)

// 移动文件夹对话框（设置 parent_id）
const moveFolderTarget = ref<{ id: number; name: string } | null>(null)
const moveFolderParentId = ref<number | null>(null)

// 可选目标文件夹（排除自身及其子树）
const moveableFolders = computed(() => {
  if (!moveTargetDoc.value) return store.folders
  return store.folders
})

/** 返回 folder_id 及其全部子孙文件夹 id（用于移动时排除，避免循环嵌套）。 */
function folderDescendants(id: number): Set<number> {
  const excluded = new Set<number>()
  let frontier = [id]
  while (frontier.length) {
    const next: number[] = []
    for (const pid of frontier) {
      for (const f of store.folders) {
        if (f.parent_id === pid && !excluded.has(f.id)) {
          excluded.add(f.id)
          next.push(f.id)
        }
      }
    }
    frontier = next
  }
  return excluded
}

const folderMoveTargets = computed(() => {
  if (!moveFolderTarget.value) return []
  // 排除自身及其整个子树（否则会把文件夹移进自己的子孙，形成循环）
  const excluded = folderDescendants(moveFolderTarget.value.id)
  excluded.add(moveFolderTarget.value.id)
  return store.folders.filter(f => !excluded.has(f.id))
})

onMounted(async () => {
  await store.loadFolders()
  const def = store.folders.find(f => f.is_default === 1)
  if (def) {
    store.currentFolderId = def.id
    await store.loadDocuments(def.id)
  }
  // 最近工作文档（"继续上次工作"入口）
  try {
    const r = await api.get<{ document: { id: number; name: string; last_position: string | null } | null }>('/search/last-work')
    lastDoc.value = r.document
  } catch {
    lastDoc.value = null
  }
})

async function selectFolder(id: number) {
  store.currentFolderId = id
  await store.loadDocuments(id)
}

async function handleNewDocument() {
  const doc = await store.createDocument(newDocName.value || undefined, store.currentFolderId ?? undefined)
  newDocName.value = ''
  router.push(`/document/${doc.id}`)
}

function openNewFolder() {
  newFolderName.value = ''
  showNewFolder.value = true
}

function cancelNewFolder() {
  newFolderName.value = ''
  showNewFolder.value = false
}

async function handleNewFolder() {
  const name = newFolderName.value.trim()
  if (!name) return
  await store.createFolder(name, store.currentFolderId ?? undefined)
  showNewFolder.value = false
  newFolderName.value = ''
  await store.loadFolders()
}

// ── 文件夹重命名 ──
function startRenameFolder(f: Folder) {
  if (f.is_default) return
  editingFolderId.value = f.id
  editingFolderName.value = f.name
}

async function confirmRenameFolder() {
  if (editingFolderId.value !== null && editingFolderName.value.trim()) {
    await store.updateFolder(editingFolderId.value, { name: editingFolderName.value.trim() })
    await store.loadFolders()
  }
  editingFolderId.value = null
  editingFolderName.value = ''
}

function cancelRenameFolder() {
  editingFolderId.value = null
  editingFolderName.value = ''
}

// ── 文档重命名 ──
function startRenameDoc(doc: { id: number; name: string }) {
  editingDocId.value = doc.id
  editingDocName.value = doc.name
}

async function confirmRenameDoc() {
  if (editingDocId.value !== null && editingDocName.value.trim()) {
    await store.updateDocument(editingDocId.value, { name: editingDocName.value.trim() })
  }
  editingDocId.value = null
  editingDocName.value = ''
}

function cancelRenameDoc() {
  editingDocId.value = null
  editingDocName.value = ''
}

// ── 删除确认 ──
async function requestDeleteFolder(f: Folder) {
  if (f.is_default) return
  // 获取影响范围（直接调 API，不修改 store 状态）
  const subfolders = store.folders.filter(x => x.parent_id === f.id).length
  const docs = await api.get<Document[]>(`/documents?folder_id=${f.id}`)
  deleteImpact.value = [
    { label: '子文件夹', value: subfolders },
    { label: '文档', value: docs.length },
  ]
  deleteTarget.value = { type: 'folder', id: f.id, name: f.name }
}

function requestDeleteDoc(doc: { id: number; name: string }) {
  deleteImpact.value = []
  deleteTarget.value = { type: 'document', id: doc.id, name: doc.name }
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  const t = deleteTarget.value
  if (t.type === 'folder') {
    await store.deleteFolder(t.id)
    await store.loadFolders()
    // 如果当前文件夹被删除，切回默认
    const def = store.folders.find(f => f.is_default === 1)
    if (def) {
      store.currentFolderId = def.id
      await store.loadDocuments(def.id)
    }
  } else {
    await store.deleteDocument(t.id)
  }
  deleteTarget.value = null
  deleteImpact.value = []
}

function cancelDelete() {
  deleteTarget.value = null
  deleteImpact.value = []
}

// ── 移动文档 ──
function requestMoveDoc(doc: { id: number; name: string }) {
  moveTargetDoc.value = { id: doc.id, name: doc.name }
  moveTargetFolderId.value = store.currentFolderId
}

async function confirmMoveDoc() {
  if (moveTargetDoc.value && moveTargetFolderId.value !== null) {
    await store.moveDocument(moveTargetDoc.value.id, moveTargetFolderId.value)
    await store.loadDocuments(store.currentFolderId ?? undefined)
  }
  moveTargetDoc.value = null
  moveTargetFolderId.value = null
}

function cancelMoveDoc() {
  moveTargetDoc.value = null
  moveTargetFolderId.value = null
}

// ── 移动文件夹（设置 parent_id）──
function requestMoveFolder(f: Folder) {
  if (f.is_default) return
  moveFolderTarget.value = { id: f.id, name: f.name }
  moveFolderParentId.value = f.parent_id
}

async function confirmMoveFolder() {
  if (moveFolderTarget.value) {
    await store.updateFolder(moveFolderTarget.value.id, { parent_id: moveFolderParentId.value })
    await store.loadFolders()
  }
  moveFolderTarget.value = null
  moveFolderParentId.value = null
}

function cancelMoveFolder() {
  moveFolderTarget.value = null
  moveFolderParentId.value = null
}

// ── 搜索与上下文恢复（FR-05）──
const searchQuery = ref('')
const searchDate = ref('')
const searchResult = ref<SearchResult | null>(null)
const searching = ref(false)
const searchError = ref('')

const hasSearchTerms = computed(() => searchQuery.value.trim() !== '' || searchDate.value !== '')

async function doSearch() {
  const q = searchQuery.value.trim()
  const date = searchDate.value
  if (!q && !date) return
  searching.value = true
  searchError.value = ''
  try {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (date) params.set('date', date)
    searchResult.value = await api.get<SearchResult>(`/search?${params.toString()}`)
  } catch {
    searchError.value = '搜索失败，请重试'
    searchResult.value = null
  } finally {
    searching.value = false
  }
}

function clearSearch() {
  searchQuery.value = ''
  searchDate.value = ''
  searchResult.value = null
  searchError.value = ''
}

/** 关键词高亮：按搜索词把文本拆成片段数组，命中的片段由模板渲染为 mark。 */
function highlightParts(text: string): (string | { hit: string })[] {
  const terms = searchQuery.value.trim().split(/\s+/).filter(Boolean)
  if (!terms.length) return [text]
  const escaped = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const lowers = terms.map(t => t.toLowerCase())
  const re = new RegExp(`(${escaped.join('|')})`, 'gi')
  return text.split(re).map(part => (lowers.includes(part.toLowerCase()) ? { hit: part } : part))
}

// ── 继续上次工作 ──
const lastDoc = ref<{ id: number; name: string; last_position: string | null } | null>(null)

function parseBlockId(raw: string | null): number {
  try {
    return Number(JSON.parse(raw || '')?.block_id) || 0
  } catch {
    return 0
  }
}

function continueLastWork() {
  if (!lastDoc.value) return
  const pos = parseBlockId(lastDoc.value.last_position)
  router.push(pos ? `/document/${lastDoc.value.id}?block=${pos}` : `/document/${lastDoc.value.id}`)
}
</script>

<template>
  <div class="home">
    <header class="home-header">
      <h1>WorkMark</h1>
      <button class="att-entry" @click="router.push('/inbox')">快速记录</button>
      <button class="att-entry" @click="router.push('/attachments')">附件管理</button>
      <button v-if="lastDoc" class="last-work-btn" @click="continueLastWork" title="恢复上次停留位置">
        ▸ 继续上次工作：{{ lastDoc.name }}
      </button>
      <button class="primary" @click="handleNewDocument">+ 新建文档</button>
    </header>

    <!-- 搜索栏（FR-05：关键词 + 日期，可组合） -->
    <div class="search-bar">
      <input
        v-model="searchQuery"
        class="search-input"
        placeholder="搜索：文档名 / 块标题 / 正文 / 代码 / 命令 / 输出（空格分隔多关键词）"
        @keyup.enter="doSearch"
      />
      <input v-model="searchDate" type="date" class="search-date" title="按日期浏览（创建/工作开始日期）" @change="doSearch" />
      <button class="primary" @click="doSearch">搜索</button>
      <button v-if="hasSearchTerms" @click="clearSearch">清除</button>
    </div>

    <div class="home-body">
      <!-- 文件夹侧栏 -->
      <aside class="sidebar">
        <h3>文件夹</h3>
        <ul class="folder-list">
          <li
            v-for="f in store.folders"
            :key="f.id"
            :class="{ active: f.id === store.currentFolderId }"
            @click="selectFolder(f.id)"
          >
            <span v-if="f.is_default" class="default-icon">★</span>
            <input
              v-if="editingFolderId === f.id"
              v-model="editingFolderName"
              class="rename-input"
              @keyup.enter="confirmRenameFolder"
              @keyup.esc="cancelRenameFolder"
              @click.stop
              v-focus
            />
            <span
              v-else
              class="folder-name"
              @dblclick.stop="startRenameFolder(f)"
            >{{ f.name }}</span>
            <span v-if="!f.is_default" class="folder-actions" @click.stop>
              <button class="icon-btn" title="重命名" @click="startRenameFolder(f)">✎</button>
              <button class="icon-btn" title="移动" @click="requestMoveFolder(f)">→</button>
              <button class="icon-btn danger" title="删除" @click="requestDeleteFolder(f)">✕</button>
            </span>
          </li>
        </ul>
        <button @click="openNewFolder">+ 新建文件夹</button>
      </aside>

      <!-- 文档列表 / 搜索结果 -->
      <main class="content">
        <!-- 搜索结果面板 -->
        <div v-if="hasSearchTerms" class="search-results">
          <div v-if="searching" class="empty">搜索中…</div>
          <div v-else-if="searchError" class="empty">{{ searchError }}</div>
          <template v-else-if="searchResult">
            <div class="search-summary">
              共 {{ searchResult.total }} 个块 / {{ searchResult.documents.length }} 个文档命中
              <template v-if="searchDate">（日期：{{ searchDate }}）</template>
            </div>

            <div v-if="searchResult.total === 0 && searchResult.documents.length === 0" class="empty">
              无匹配结果。
            </div>

            <!-- 文档名命中 -->
            <ul v-if="searchResult.documents.length" class="doc-hit-list">
              <li
                v-for="d in searchResult.documents"
                :key="'doc-' + d.document_id"
                class="doc-hit"
                @click="router.push(`/document/${d.document_id}`)"
              >
                <span class="hit-doc-icon">📄</span>
                <span class="hit-doc-name">{{ d.document_name }}</span>
                <span class="hit-meta">{{ d.block_count }} 块 · 更新于 {{ d.updated_at }}</span>
              </li>
            </ul>

            <!-- 块命中 -->
            <ul v-if="searchResult.blocks.length" class="block-hit-list">
              <li
                v-for="b in searchResult.blocks"
                :key="'blk-' + b.block_id"
                class="block-hit"
                @click="router.push(`/document/${b.document_id}?block=${b.block_id}`)"
              >
                <div class="block-hit-head">
                  <span class="hit-doc-tag">{{ b.document_name }}</span>
                  <span class="hit-block-title">{{ b.is_sub ? '└ ' : '' }}{{ b.block_title }}</span>
                  <span class="hit-meta">{{ b.work_start_time ? '工作 ' + b.work_start_time.replace('T', ' ') : b.created_at }}</span>
                </div>
                <div class="block-hit-digest">
                  <template v-for="(part, i) in highlightParts(b.digest)" :key="i">
                    <mark v-if="typeof part === 'object'">{{ part.hit }}</mark>
                    <template v-else>{{ part }}</template>
                  </template>
                </div>
              </li>
            </ul>
          </template>
        </div>

        <!-- 常规文档列表 -->
        <template v-else>
        <div class="new-doc-bar">
          <input v-model="newDocName" placeholder="文档名称（可选）" @keyup.enter="handleNewDocument" />
          <button class="primary" @click="handleNewDocument">创建</button>
        </div>

        <div v-if="store.documents.length === 0" class="empty">
          当前文件夹暂无文档，点击上方创建。
        </div>
        <ul v-else class="doc-list">
          <li v-for="doc in store.documents" :key="doc.id" class="doc-item" @click="router.push(`/document/${doc.id}`)">
            <input
              v-if="editingDocId === doc.id"
              v-model="editingDocName"
              class="rename-input"
              @keyup.enter="confirmRenameDoc"
              @keyup.esc="cancelRenameDoc"
              @click.stop
              v-focus
            />
            <template v-else>
              <span class="doc-name" @dblclick.stop="startRenameDoc(doc)">{{ doc.name }}</span>
              <span class="doc-time">{{ doc.updated_at }}</span>
              <span class="doc-actions" @click.stop>
                <button class="icon-btn" title="重命名" @click="startRenameDoc(doc)">✎</button>
                <button class="icon-btn" title="移动" @click="requestMoveDoc(doc)">→</button>
                <button class="icon-btn danger" title="删除" @click="requestDeleteDoc(doc)">✕</button>
              </span>
            </template>
          </li>
        </ul>
        </template>
      </main>
    </div>

    <!-- 新建文件夹对话框 -->
    <div v-if="showNewFolder" class="dialog-overlay" @click.self="cancelNewFolder">
      <div class="dialog">
        <h3 class="dialog-title">新建文件夹</h3>
        <p class="dialog-message">在当前文件夹下创建子文件夹：</p>
        <input
          v-model="newFolderName"
          class="dialog-input"
          placeholder="文件夹名称"
          @keyup.enter="handleNewFolder"
          @keyup.esc="cancelNewFolder"
          v-focus
        />
        <div class="dialog-actions">
          <button @click="cancelNewFolder">取消</button>
          <button class="primary" @click="handleNewFolder">创建</button>
        </div>
      </div>
    </div>

    <!-- 删除确认对话框 -->
    <ConfirmDialog
      v-if="deleteTarget"
      :title="`确认删除${deleteTarget.type === 'folder' ? '文件夹' : '文档'}「${deleteTarget.name}」？`"
      :message="deleteTarget.type === 'folder' ? '删除后将级联删除其中所有子文件夹和文档，且不可恢复。' : '删除后将级联删除其中所有任务块，且不可恢复。'"
      :details="deleteImpact"
      confirmText="删除"
      :danger="true"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />

    <!-- 移动文档对话框 -->
    <div v-if="moveTargetDoc" class="dialog-overlay" @click.self="cancelMoveDoc">
      <div class="dialog">
        <h3 class="dialog-title">移动文档「{{ moveTargetDoc.name }}」到</h3>
        <p class="dialog-message">选择目标文件夹：</p>
        <select v-model="moveTargetFolderId" class="move-select">
          <option v-for="f in moveableFolders" :key="f.id" :value="f.id">
            {{ f.is_default ? '★ ' : '' }}{{ f.name }}
          </option>
        </select>
        <div class="dialog-actions">
          <button @click="cancelMoveDoc">取消</button>
          <button class="primary" @click="confirmMoveDoc">移动</button>
        </div>
      </div>
    </div>

    <!-- 移动文件夹对话框 -->
    <div v-if="moveFolderTarget" class="dialog-overlay" @click.self="cancelMoveFolder">
      <div class="dialog">
        <h3 class="dialog-title">移动文件夹「{{ moveFolderTarget.name }}」到</h3>
        <p class="dialog-message">选择目标父文件夹（选择根级请留空）：</p>
        <select v-model="moveFolderParentId" class="move-select">
          <option :value="null">（根级）</option>
          <option v-for="f in folderMoveTargets" :key="f.id" :value="f.id">
            {{ f.is_default ? '★ ' : '' }}{{ f.name }}
          </option>
        </select>
        <div class="dialog-actions">
          <button @click="cancelMoveFolder">取消</button>
          <button class="primary" @click="confirmMoveFolder">移动</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home { display: flex; flex-direction: column; height: 100vh; }
.home-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 14px 28px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
}
.home-header h1 {
  font-family: var(--font-serif);
  font-size: 1.45rem;
  letter-spacing: 0.04em;
  display: flex;
  align-items: center;
}
/* 朱砂印章式标记 */
.home-header h1::before {
  content: '';
  width: 12px;
  height: 12px;
  background: var(--accent);
  border-radius: 3px;
  margin-right: 10px;
  box-shadow: 0 1px 2px rgba(157, 58, 36, 0.4);
}
.home-body { display: flex; flex: 1; min-height: 0; }
.sidebar {
  width: 260px;
  flex-shrink: 0;
  padding: 20px 14px;
  border-right: 1px solid var(--border);
  background: var(--bg-alt);
  overflow-y: auto;
}
.sidebar h3 {
  margin: 0 8px 12px;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  color: var(--muted);
}
.folder-list { list-style: none; margin-bottom: 16px; }
.folder-list li {
  display: flex;
  align-items: center;
  padding: 7px 12px;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 0.92rem;
  gap: 4px;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
}
.folder-list li:hover { background: rgba(181, 68, 44, 0.06); }
.folder-list li.active {
  background: var(--accent-light);
  color: var(--accent);
  font-weight: 600;
  box-shadow: inset 2px 0 0 var(--accent);
}
.folder-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.default-icon { color: var(--warn); }
.folder-actions { display: none; gap: 2px; }
.folder-list li:hover .folder-actions { display: flex; }
.icon-btn {
  border: none; background: transparent; cursor: pointer;
  padding: 2px 6px; font-size: 0.85rem; border-radius: 4px;
  color: var(--muted);
  transition: background 0.15s, color 0.15s;
}
.icon-btn:hover { background: rgba(35, 39, 43, 0.08); color: var(--fg); }
.icon-btn.danger:hover { color: var(--danger); }
.rename-input {
  flex: 1;
  font-size: 0.92rem;
  padding: 2px 6px;
  border: 1px solid var(--accent-line);
  border-radius: 4px;
  background: var(--bg);
}

.content { flex: 1; padding: 28px 32px; overflow-y: auto; }
.new-doc-bar { display: flex; gap: 8px; margin-bottom: 22px; }
.new-doc-bar input { flex: 1; }
.empty { color: var(--muted); padding: 48px; text-align: center; }
.doc-list { list-style: none; }
.doc-item {
  display: flex;
  align-items: center;
  padding: 13px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  margin-bottom: 10px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
  gap: 10px;
  background: var(--bg);
  animation: wm-fade-up 0.32s both;
}
.doc-item:nth-child(2) { animation-delay: 0.04s; }
.doc-item:nth-child(3) { animation-delay: 0.08s; }
.doc-item:nth-child(4) { animation-delay: 0.12s; }
.doc-item:nth-child(5) { animation-delay: 0.16s; }
.doc-item:nth-child(6) { animation-delay: 0.2s; }
.doc-item:hover {
  border-color: var(--accent-line);
  box-shadow: var(--shadow);
  transform: translateY(-1px);
}
.doc-name { font-weight: 600; flex: 1; }
.doc-time { color: var(--muted); font-size: 0.82rem; font-variant-numeric: tabular-nums; }
.doc-actions { display: none; gap: 2px; }
.doc-item:hover .doc-actions { display: flex; }
.move-select { width: 100%; padding: 8px; margin-bottom: 12px; border: 1px solid var(--border); border-radius: var(--radius); font-size: 0.9rem; background: var(--bg); }
.dialog-input { width: 100%; padding: 8px 10px; margin-bottom: 12px; border: 1px solid var(--border); border-radius: var(--radius); font-size: 0.9rem; background: var(--bg); }
.dialog-overlay {
  position: fixed; inset: 0;
  background: rgba(35, 39, 43, 0.38);
  backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.dialog {
  background: var(--bg);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  padding: 26px;
  width: min(480px, calc(100vw - 32px));
  box-shadow: var(--shadow-lg);
  animation: wm-pop 0.18s ease-out;
}
.dialog-title { font-family: var(--font-serif); font-size: 1.15rem; font-weight: 700; margin-bottom: 8px; }
.dialog-message { color: var(--muted); margin-bottom: 12px; font-size: 0.9rem; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }

/* 搜索栏与结果（FR-05） */
.home-header h1 { margin-right: auto; }
.att-entry {
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--fg);
  padding: 7px 16px;
  border-radius: 8px;
  font-size: 0.88rem;
  font-weight: 500;
  letter-spacing: 0.01em;
  transition:
    color 0.16s ease,
    border-color 0.16s ease,
    background 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
}
.att-entry:hover { background: var(--accent-light); color: var(--accent); border-color: var(--accent-line); }
.att-entry:active { transform: translateY(1px) scale(0.99); }
.last-work-btn {
  border: 1px solid var(--accent-line);
  background: var(--accent-light);
  color: var(--accent);
  padding: 7px 16px;
  border-radius: 999px;
  font-size: 0.88rem;
  font-weight: 500;
  letter-spacing: 0.01em;
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition:
    background 0.16s ease,
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
}
.last-work-btn:hover { background: rgba(181, 68, 44, 0.14); border-color: var(--accent); }
.last-work-btn:active { transform: translateY(1px) scale(0.99); }
.search-bar {
  display: flex;
  gap: 8px;
  padding: 12px 28px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-alt);
}
.search-input { flex: 1; }
.search-date { width: 160px; }
.search-results { overflow-y: auto; }
.search-summary { color: var(--muted); font-size: 0.85rem; margin-bottom: 12px; }
.doc-hit-list, .block-hit-list { list-style: none; margin-bottom: 16px; }
.doc-hit {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  margin-bottom: 8px;
  cursor: pointer;
  background: var(--bg);
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}
.doc-hit:hover { border-color: var(--accent-line); box-shadow: var(--shadow); transform: translateY(-1px); }
.hit-doc-name { font-weight: 600; flex: 1; }
.hit-meta { color: var(--muted); font-size: 0.8rem; white-space: nowrap; font-variant-numeric: tabular-nums; }
.block-hit {
  padding: 11px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  margin-bottom: 8px;
  cursor: pointer;
  background: var(--bg);
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}
.block-hit:hover { border-color: var(--accent-line); box-shadow: var(--shadow); transform: translateY(-1px); }
.block-hit-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.hit-doc-tag {
  background: var(--accent-light);
  color: var(--accent);
  border: 1px solid var(--accent-line);
  font-size: 0.75rem;
  padding: 0 8px;
  border-radius: 999px;
  white-space: nowrap;
}
.hit-block-title { font-weight: 600; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.block-hit-digest { color: var(--muted); font-size: 0.85rem; line-height: 1.6; }
.block-hit-digest mark { background: rgba(176, 121, 22, 0.22); color: inherit; padding: 0 2px; border-radius: 3px; }

/* 响应式：覆盖窄窗口 / 分屏 / 浏览器缩放（不主打手机，但不至于布局塌陷） */
@media (max-width: 860px) {
  .sidebar { width: 200px; }
  .home-header { flex-wrap: wrap; }
  .search-bar { flex-wrap: wrap; }
}
@media (max-width: 640px) {
  .sidebar { width: 168px; padding: 14px 10px; }
  .content { padding: 20px 16px; }
  .home-header { padding: 12px 16px; }
  .search-bar { padding: 10px 16px; }
  .search-date { width: 130px; }
}
</style>
