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

/** 内容块（任务块 content JSON 数组的元素） */
export interface ContentBlock {
  type: 'text' | 'code' | 'shell' | 'output' | 'image' | 'todo' | 'table'
  content?: string
  language?: string
  attachment_id?: number
  items?: { text: string; done: boolean }[]
  rows?: string[][]
}
