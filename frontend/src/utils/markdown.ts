/** 极简 Markdown 渲染（离线、无依赖）。
 * 支持：代码围栏、1-3 级标题、无序/有序列表、行内代码、粗体、斜体、链接、段落换行。
 * 所有文本先 HTML 转义再包标签，保证原文保真且安全。
 */

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function inline(s: string): string {
  return esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
}

export function renderMarkdown(src: string): string {
  const lines = (src || '').split('\n')
  const html: string[] = []
  let inCode = false
  let codeBuf: string[] = []
  let listMode: 'ul' | 'ol' | null = null

  const closeList = () => {
    if (listMode) {
      html.push(`</${listMode}>`)
      listMode = null
    }
  }

  for (const line of lines) {
    if (/^```/.test(line)) {
      if (inCode) {
        html.push(`<pre class="md-pre">${esc(codeBuf.join('\n'))}</pre>`)
        codeBuf = []
        inCode = false
      } else {
        closeList()
        inCode = true
      }
      continue
    }
    if (inCode) {
      codeBuf.push(line)
      continue
    }
    const h = /^(#{1,3})\s+(.*)/.exec(line)
    if (h) {
      closeList()
      html.push(`<h${h[1].length + 1}>${inline(h[2])}</h${h[1].length + 1}>`)
      continue
    }
    const ul = /^[-*]\s+(.*)/.exec(line)
    if (ul) {
      if (listMode !== 'ul') {
        closeList()
        html.push('<ul>')
        listMode = 'ul'
      }
      html.push(`<li>${inline(ul[1])}</li>`)
      continue
    }
    const ol = /^\d+[.)]\s+(.*)/.exec(line)
    if (ol) {
      if (listMode !== 'ol') {
        closeList()
        html.push('<ol>')
        listMode = 'ol'
      }
      html.push(`<li>${inline(ol[1])}</li>`)
      continue
    }
    closeList()
    html.push(line.trim() ? `<p>${inline(line)}</p>` : '<p class="md-gap"></p>')
  }
  if (inCode) html.push(`<pre class="md-pre">${esc(codeBuf.join('\n'))}</pre>`)
  closeList()
  return html.join('')
}
