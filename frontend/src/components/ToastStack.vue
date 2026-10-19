<script setup lang="ts">
/** 全局 Toast 容器：右上角堆叠，点击可关闭，按类型着色。 */
import { useToasts, dismissToast } from '@/composables/useToast'
const toasts = useToasts()
</script>

<template>
  <Teleport to="body">
    <div class="toast-stack" role="status" aria-live="polite">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="toast"
        :class="t.type"
        @click="dismissToast(t.id)"
      >
        <span class="toast-ico">{{ t.type === 'error' ? '✕' : t.type === 'success' ? '✓' : 'ℹ' }}</span>
        <span class="toast-msg">{{ t.message }}</span>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}
.toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: min(380px, calc(100vw - 40px));
  padding: 11px 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  background: var(--bg);
  box-shadow: var(--shadow-lg);
  font-size: 0.88rem;
  cursor: pointer;
  animation: toast-in 0.2s ease-out;
}
.toast-ico {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 700;
  background: var(--bg-alt);
  border: 1px solid var(--border-strong);
  color: var(--muted);
}
.toast.success { border-color: #2f9e44; }
.toast.success .toast-ico { background: #2f9e44; border-color: #2f9e44; color: #fff; }
.toast.error { border-color: var(--danger); }
.toast.error .toast-ico { background: var(--danger); border-color: var(--danger); color: #fff; }
.toast-msg { line-height: 1.5; word-break: break-word; }
@keyframes toast-in {
  from { opacity: 0; transform: translateY(-6px); }
  to { opacity: 1; transform: none; }
}
</style>