<script setup lang="ts">
/** 通用确认对话框，支持显示影响范围详情。
 * 无障碍：role=dialog + aria-modal、Esc 关闭、初始聚焦、Tab 焦点圈定、关闭后焦点恢复。
 */
import { onMounted, onUnmounted, ref, nextTick } from 'vue'

defineProps<{
  title: string
  message?: string
  details?: { label: string; value: number | string }[]
  confirmText?: string
  cancelText?: string
  danger?: boolean
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()

const root = ref<HTMLElement | null>(null)
const cancelBtn = ref<HTMLButtonElement | null>(null)
const confirmBtn = ref<HTMLButtonElement | null>(null)

let previouslyFocused: HTMLElement | null = null

function onConfirm() { emit('confirm') }
function onCancel() { emit('cancel') }

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') { e.preventDefault(); onCancel(); return }
  if (e.key !== 'Tab') return
  const list = Array.from(
    root.value?.querySelectorAll<HTMLElement>('button, input, select, textarea, [href], [tabindex]:not([tabindex="-1"])') ?? [],
  ).filter(el => !el.hasAttribute('disabled'))
  if (list.length === 0) return
  const first = list[0]
  const last = list[list.length - 1]
  const active = document.activeElement as HTMLElement
  if (e.shiftKey && active === first) { e.preventDefault(); last.focus() }
  else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus() }
}

onMounted(() => {
  previouslyFocused = document.activeElement as HTMLElement | null
  nextTick(() => (confirmBtn.value || cancelBtn.value)?.focus())
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  previouslyFocused?.focus?.()
})
</script>

<template>
  <div ref="root" class="dialog-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title" @click.self="onCancel">
    <div class="dialog">
      <h3 id="confirm-dialog-title" class="dialog-title">{{ title }}</h3>
      <p v-if="message" class="dialog-message">{{ message }}</p>
      <ul v-if="details && details.length" class="dialog-details">
        <li v-for="d in details" :key="d.label">
          <span class="detail-label">{{ d.label }}</span>
          <span class="detail-value">{{ d.value }}</span>
        </li>
      </ul>
      <div class="dialog-slot"><slot /></div>
      <div class="dialog-actions">
        <button ref="cancelBtn" @click="onCancel">{{ cancelText || '取消' }}</button>
        <button ref="confirmBtn" :class="danger ? 'danger' : 'primary'" @click="onConfirm">{{ confirmText || '确认' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dialog-overlay {
  position: fixed; inset: 0;
  background: rgba(35, 39, 43, 0.38);
  backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.dialog {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 26px;
  width: min(480px, calc(100vw - 32px));
  box-shadow: var(--shadow-lg);
  animation: wm-pop 0.18s ease-out;
}
.dialog-title { font-family: var(--font-serif); font-size: 1.15rem; font-weight: 700; margin-bottom: 8px; }
.dialog-message { color: var(--muted); margin-bottom: 12px; font-size: 0.9rem; }
.dialog-details { list-style: none; margin-bottom: 16px; }
.dialog-details li {
  display: flex; justify-content: space-between;
  padding: 7px 12px; background: var(--bg-alt);
  border: 1px solid var(--border);
  border-radius: var(--radius); margin-bottom: 6px; font-size: 0.88rem;
}
.detail-label { color: var(--muted); }
.detail-value { font-weight: 600; font-variant-numeric: tabular-nums; }
.dialog-slot { margin-bottom: 16px; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>