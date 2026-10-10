/** 前端 TypeScript 类型定义。 */

export interface Folder {
  id: number
  name: string
  parent_id: number | null
  sort_order: number
  is_default: number
  created_at: string
  updated_at: string
}

export interface Document {
  id: number
  folder_id: number
  name: string
  sort_order: number
  last_position: string | null
  created_at: string
  updated_at: string
}

export interface Block {
  id: number
  document_id: number
  parent_id: number | null
  title: string | null
  content: string  // JSON 数组
  sort_order: number
  work_start_time: string | null
  work_end_time: string | null
  created_at: string
  updated_at: string
}

/** 搜索结果（FR-05） */
export interface SearchBlockHit {
  block_id: number
  document_id: number
  document_name: string
  block_title: string
  is_sub: boolean
  created_at: string
  work_start_time: string | null
  digest: string
}

export interface SearchDocHit {
  document_id: number
  document_name: string
  updated_at: string
  block_count: number
}

export interface SearchResult {
  blocks: SearchBlockHit[]
  documents: SearchDocHit[]
  total: number
}

/** 内容块（任务块 content JSON 数组的元素） */
export interface ContentBlock {
  type: 'text' | 'code' | 'shell' | 'output' | 'image' | 'todo' | 'table'
  content?: string
  language?: string
  attachment_id?: number
  items?: { text: string; done: boolean }[]
  rows?: string[][]
}
