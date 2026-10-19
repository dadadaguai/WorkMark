/** 对话框焦点管理：初始聚焦、Tab 焦点圈定、Esc 关闭、关闭后焦点恢复。
 * 供 ConfirmDialog 与各处条件渲染的弹窗（首页新建/移动、编辑器离页守卫）统一复用。
 */
import { type Ref, nextTick, onUnmounted, watch } from 'vue'

const FOCUSABLE = 'button, input, select, textarea, [href], [tabindex]:not([tabindex="-1"])'

export function useDialogFocus(root: Ref<HTMLElement | null>, onClose: () => void) {
  let opened = false
  let previouslyFocused: HTMLElement | null = null

  const elements = () =>
    Array.from(root.value?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(
      el => !el.hasAttribute('disabled'),
    )

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') { e.preventDefault(); onClose(); return }
    if (e.key !== 'Tab') return
    const els = elements()
    if (!els.length) return
    const first = els[0]
    const last = els[els.length - 1]
    const active = document.activeElement as HTMLElement
    if (e.shiftKey && active === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus() }
  }

  function close() {
    if (!opened) return
    opened = false
    document.removeEventListener('keydown', onKeydown)
    previouslyFocused?.focus?.()
    previouslyFocused = null
  }

  // 弹窗以 v-if 存在/销毁：root 由 null↔DOM 切换，据此收放焦点管理
  watch(root, (el) => {
    if (el && !opened) {
      opened = true
      previouslyFocused = document.activeElement as HTMLElement | null
      document.addEventListener('keydown', onKeydown)
    } else if (!el) {
      close()
    }
  }, { immediate: true })

  onUnmounted(close)

  /** 初始聚焦：默认第一个可聚焦元素；可传 picker 选择目标（如危险弹窗聚焦「取消」）。 */
  function focusInitial(picker: (els: HTMLElement[]) => HTMLElement | undefined = els => els[0]) {
    nextTick(() => picker(elements())?.focus?.())
  }

  return { focusInitial }
}