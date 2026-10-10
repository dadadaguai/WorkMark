<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/composables/useApi'
import type { Document, Block } from '@/types'

const props = defineProps<{ id: string }>()
const router = useRouter()

const doc = ref<Document | null>(null)
const blocks = ref<Block[]>([])
const newBlockTitle = ref('')

onMounted(async () => {
  doc.value = await api.get<Document>(`/documents/${props.id}`)
  blocks.value = await api.get<Block[]>(`/blocks/document/${props.id}`)
})

async function addBlock() {
  const block = await api.post<Block>('/blocks', {
    document_id: Number(props.id),
    title: newBlockTitle.value || undefined,
    content: '[]',
  })
  blocks.value.push(block)
  newBlockTitle.value = ''
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
  if (!confirm('确认删除此块？')) return
  await api.del(`/blocks/${blockId}`)
  blocks.value = blocks.value.filter(b => b.id !== blockId)
}

async function updateBlockTitle(block: Block, title: string) {
  await api.put(`/blocks/${block.id}`, { title })
  block.title = title
}

async function updateBlockContent(block: Block, content: string) {
  await api.put(`/blocks/${block.id}`, { content })
  block.content = content
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
        <button class="primary" @click="addBlock">+ 添加任务块</button>
      </div>

      <div v-if="blocks.length === 0" class="empty">
        暂无任务块，添加第一个开始记录。
      </div>

      <div v-for="block in blocks" :key="block.id" class="block-card"
           :class="{ 'sub-block': block.parent_id !== null }">
        <div class="block-header">
          <input
            v-if="block.title !== null"
            :value="block.title"
            class="block-title"
            @change="updateBlockTitle(block, ($event.target as HTMLInputElement).value)"
            placeholder="无标题"
          />
          <span v-else class="block-title muted">无标题</span>
          <span class="block-time">{{ block.created_at }}</span>
          <button class="danger" @click="deleteBlock(block.id)">删除</button>
        </div>
        <div class="block-content">
          <textarea
            :value="block.content"
            @change="updateBlockContent(block, ($event.target as HTMLTextAreaElement).value)"
            placeholder="输入内容..."
            class="content-area"
          ></textarea>
        </div>
        <div v-if="block.parent_id === null" class="block-actions">
          <button @click="addSubBlock(block.id)">+ 添加子块</button>
        </div>
      </div>
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
.empty { color: var(--muted); text-align: center; padding: 40px; }
.block-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 12px;
  padding: 16px;
  background: var(--bg);
}
.block-card.sub-block { margin-left: 32px; border-left: 3px solid var(--accent); }
.block-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.block-title { border: none; font-weight: 600; font-size: 1rem; flex: 1; background: transparent; }
.block-title:focus { border: 1px solid var(--border); }
.block-title.muted { color: var(--muted); font-weight: 400; }
.block-time { color: var(--muted); font-size: 0.8rem; }
.block-content { margin-bottom: 8px; }
.content-area {
  width: 100%;
  min-height: 60px;
  font-family: "Cascadia Code", Consolas, monospace;
  font-size: 0.88rem;
  resize: vertical;
}
.block-actions { margin-top: 8px; }
.loading { padding: 40px; text-align: center; color: var(--muted); }
</style>
