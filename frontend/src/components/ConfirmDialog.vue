<script setup lang="ts">
/** 通用确认对话框，支持显示影响范围详情。 */

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

function onConfirm() { emit('confirm') }
function onCancel() { emit('cancel') }
</script>

<template>
  <div class="dialog-overlay" @click.self="onCancel">
    <div class="dialog">
      <h3 class="dialog-title">{{ title }}</h3>
      <p v-if="message" class="dialog-message">{{ message }}</p>
      <ul v-if="details && details.length" class="dialog-details">
        <li v-for="d in details" :key="d.label">
          <span class="detail-label">{{ d.label }}</span>
          <span class="detail-value">{{ d.value }}</span>
        </li>
      </ul>
      <div class="dialog-slot"><slot /></div>
      <div class="dialog-actions">
        <button @click="onCancel">{{ cancelText || '取消' }}</button>
        <button :class="danger ? 'danger' : 'primary'" @click="onConfirm">{{ confirmText || '确认' }}</button>
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
  min-width: 360px;
  max-width: 480px;
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
