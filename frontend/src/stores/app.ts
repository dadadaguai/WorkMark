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

  async function updateFolder(id: number, data: { name?: string; parent_id?: number | null; sort_order?: number }) {
    const folder = await api.put<Folder>(`/folders/${id}`, data)
    const idx = folders.value.findIndex(f => f.id === id)
    if (idx >= 0) folders.value[idx] = folder
    return folder
  }

  async function deleteFolder(id: number): Promise<{ deleted: number; affected_documents: number; affected_subfolders: number }> {
    const result = await api.del<{ deleted: number; affected_documents: number; affected_subfolders: number }>(`/folders/${id}`)
    folders.value = folders.value.filter(f => f.id !== id)
    return result
  }

  async function updateDocument(id: number, data: { name?: string; folder_id?: number; sort_order?: number; last_position?: string }) {
    const doc = await api.put<Document>(`/documents/${id}`, data)
    const idx = documents.value.findIndex(d => d.id === id)
    if (idx >= 0) documents.value[idx] = doc
    return doc
  }

  async function deleteDocument(id: number): Promise<{ deleted: number; affected_blocks: number }> {
    const result = await api.del<{ deleted: number; affected_blocks: number }>(`/documents/${id}`)
    documents.value = documents.value.filter(d => d.id !== id)
    return result
  }

  async function moveDocument(docId: number, targetFolderId: number) {
    const doc = await api.put<Document>(`/documents/${docId}`, { folder_id: targetFolderId })
    documents.value = documents.value.filter(d => d.id !== docId)
    return doc
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
    updateFolder,
    deleteFolder,
    updateDocument,
    deleteDocument,
    moveDocument,
  }
})
