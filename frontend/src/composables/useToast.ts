/** 全局轻量 Toast：模块级响应式队列，任意组件可直接调用 toast()。 */
import { ref } from 'vue'

export type ToastType = 'info' | 'success' | 'error'
export interface ToastItem { id: number; message: string; type: ToastType }

const toasts = ref<ToastItem[]>([])
let seq = 0

/** 弹出提示并自动消失（error 稍长）。 */
export function toast(message: string, type: ToastType = 'info') {
  const id = ++seq
  toasts.value.push({ id, message, type })
  const delay = type === 'error' ? 5000 : 3200
  window.setTimeout(() => dismissToast(id), delay)
}

export function dismissToast(id: number) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

/** 组件内读取响应式队列。 */
export function useToasts() {
  return toasts
}