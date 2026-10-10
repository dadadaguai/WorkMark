<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const store = useAppStore()
const showNewFolder = ref(false)
const newFolderName = ref('')
const newDocName = ref('')

onMounted(async () => {
  await store.loadFolders()
  // 选中默认文件夹
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
            {{ f.name }}
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
          <li v-for="doc in store.documents" :key="doc.id" @click="router.push(`/document/${doc.id}`)">
            <span class="doc-name">{{ doc.name }}</span>
            <span class="doc-time">{{ doc.updated_at }}</span>
          </li>
        </ul>
      </main>
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
  padding: 8px 12px;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 0.92rem;
}
.folder-list li:hover { background: var(--accent-light); }
.folder-list li.active { background: var(--accent-light); color: var(--accent); font-weight: 600; }
.default-icon { color: var(--warn); }
.new-folder-form { display: flex; gap: 8px; flex-wrap: wrap; }
.new-folder-form input { flex: 1; }
.content { flex: 1; padding: 24px; overflow-y: auto; }
.new-doc-bar { display: flex; gap: 8px; margin-bottom: 20px; }
.new-doc-bar input { flex: 1; }
.empty { color: var(--muted); padding: 40px; text-align: center; }
.doc-list { list-style: none; }
.doc-list li {
  display: flex;
  justify-content: space-between;
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.doc-list li:hover { border-color: var(--accent); box-shadow: var(--shadow); }
.doc-name { font-weight: 500; }
.doc-time { color: var(--muted); font-size: 0.85rem; }
</style>
