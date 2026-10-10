<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { api } from '@/composables/useApi'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import type { Folder, Document } from '@/types'

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

const folderMoveTargets = computed(() => {
  if (!moveFolderTarget.value) return []
  // 排除自身
  return store.folders.filter(f => f.id !== moveFolderTarget.value!.id)
})

onMounted(async () => {
  await store.loadFolders()
  const def = store.folders.find(f => f.is_default === 1)
  if (def) {
    store.currentFolderId = def.id
    await store.loadDocuments(def.id)
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

async function handleNewFolder() {
  if (!newFolderName.value) return
  await store.createFolder(newFolderName.value, store.currentFolderId ?? undefined)
  newFolderName.value = ''
  showNewFolder.value = false
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
</script>

<template>
  <div class="home">
    <header class="home-header">
      <h1>WorkMark</h1>
      <button class="primary" @click="handleNewDocument">+ 新建文档</button>
    </header>

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
        <button v-if="!showNewFolder" @click="showNewFolder = true">+ 新建文件夹</button>
        <div v-else class="new-folder-form">
          <input v-model="newFolderName" placeholder="文件夹名称" @keyup.enter="handleNewFolder" />
          <button class="primary" @click="handleNewFolder">确定</button>
          <button @click="showNewFolder = false">取消</button>
        </div>
      </aside>

      <!-- 文档列表 -->
      <main class="content">
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
      </main>
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
.home-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border);
}
.home-header h1 { font-size: 1.4rem; }
.home-body { display: flex; height: calc(100vh - 65px); }
.sidebar {
  width: 240px;
  padding: 16px;
  border-right: 1px solid var(--border);
  background: var(--bg-alt);
  overflow-y: auto;
}
.sidebar h3 { margin-bottom: 12px; font-size: 0.9rem; color: var(--muted); }
.folder-list { list-style: none; margin-bottom: 16px; }
.folder-list li {
  display: flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 0.92rem;
  gap: 4px;
}
.folder-list li:hover { background: var(--accent-light); }
.folder-list li.active { background: var(--accent-light); color: var(--accent); font-weight: 600; }
.folder-name { flex: 1; }
.default-icon { color: var(--warn); }
.folder-actions { display: none; gap: 2px; }
.folder-list li:hover .folder-actions { display: flex; }
.icon-btn {
  border: none; background: transparent; cursor: pointer;
  padding: 2px 6px; font-size: 0.85rem; border-radius: 3px;
  color: var(--muted);
}
.icon-btn:hover { background: var(--border); color: var(--text); }
.icon-btn.danger:hover { color: var(--danger); }
.rename-input {
  flex: 1;
  font-size: 0.92rem;
  padding: 2px 6px;
  border: 1px solid var(--accent);
  border-radius: 3px;
  background: var(--bg);
}
.new-folder-form { display: flex; gap: 8px; flex-wrap: wrap; }
.new-folder-form input { flex: 1; }
.content { flex: 1; padding: 24px; overflow-y: auto; }
.new-doc-bar { display: flex; gap: 8px; margin-bottom: 20px; }
.new-doc-bar input { flex: 1; }
.empty { color: var(--muted); padding: 40px; text-align: center; }
.doc-list { list-style: none; }
.doc-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.15s;
  gap: 8px;
}
.doc-item:hover { border-color: var(--accent); box-shadow: var(--shadow); }
.doc-name { font-weight: 500; flex: 1; }
.doc-time { color: var(--muted); font-size: 0.85rem; }
.doc-actions { display: none; gap: 2px; }
.doc-item:hover .doc-actions { display: flex; }
.move-select { width: 100%; padding: 8px; margin-bottom: 12px; border: 1px solid var(--border); border-radius: var(--radius); font-size: 0.9rem; background: var(--bg); }
.dialog-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.dialog {
  background: var(--bg);
  border-radius: var(--radius);
  padding: 24px;
  min-width: 360px;
  max-width: 480px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}
.dialog-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 8px; }
.dialog-message { color: var(--muted); margin-bottom: 12px; font-size: 0.9rem; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>
