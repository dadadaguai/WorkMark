import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/composables/useApi'
import type { Folder, Document } from '@/types'

export const useAppStore = defineStore('app', () => {
  const folders = ref<Folder[]>([])
  const documents = ref<Document[]>([])
  const currentFolderId = ref<number | null>(null)
  const lastDocumentId = ref<number | null>(null)

  async function loadFolders() {
    folders.value = await api.get<Folder[]>('/folders')
  }

  async function loadDocuments(folderId?: number) {
    const q = folderId ? `?folder_id=${folderId}` : ''
    documents.value = await api.get<Document[]>(`/documents${q}`)
  }

  async function createDocument(name?: string, folderId?: number) {
    const doc = await api.post<Document>('/documents', { name, folder_id: folderId })
    documents.value.unshift(doc)
    return doc
  }

  async function createFolder(name: string, parentId?: number) {
    const folder = await api.post<Folder>('/folders', { name, parent_id: parentId })
    folders.value.push(folder)
    return folder
  }

  return {
    folders,
    documents,
    currentFolderId,
    lastDocumentId,
    loadFolders,
    loadDocuments,
    createDocument,
    createFolder,
  }
})
