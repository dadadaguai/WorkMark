/** 极简语法高亮（离线、无依赖）：注释 / 字符串 / 数字 / 关键字。 */

const KEYWORDS: Record<string, Set<string>> = {
  python: new Set(
    ('def class if elif else for while import from as return try except finally with pass break continue ' +
      'lambda yield global nonlocal assert raise del in is not and or None True False async await self ' +
      'print len range str int float list dict set tuple open type isinstance super enumerate zip').split(' '),
  ),
  javascript: new Set(
    ('function const let var if else for while return class extends new this typeof instanceof null undefined ' +
      'true false async await import export default try catch finally throw switch case break continue of in do ' +
      'yield static get set console log').split(' '),
  ),
  shell: new Set(
    ('if then else elif fi for do done while case esac function echo cd ls cp mv rm mkdir touch grep awk sed cat ' +
      'chmod chown export source alias sudo apt npm pip git python node curl wget tar zip unzip ssh scp kill ps ' +
      'read local return exit set xargs find which env useradd usermod passwd systemctl journalctl docker').split(' '),
  ),
}

const ALIAS: Record<string, string> = {
  js: 'javascript',
  ts: 'javascript',
  typescript: 'javascript',
  jsx: 'javascript',
  py: 'python',
  python3: 'python',
  bash: 'shell',
  sh: 'shell',
  zsh: 'shell',
  console: 'shell',
  terminal: 'shell',
}

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function highlight(code: string, lang?: string): string {
  const key = lang ? (ALIAS[lang.toLowerCase()] || lang.toLowerCase()) : ''
  const kw = KEYWORDS[key]
  if (!kw) return esc(code)

  const out: string[] = []
  let i = 0
  const n = code.length
  while (i < n) {
    const rest = code.slice(i)
    // 注释（# 行注释 / // 行注释 / /* 块注释 */）
    let m = /^(#[^\n]*(?:\n|$)|\/\/[^\n]*(?:\n|$)|\/\*[\s\S]*?\*\/)/.exec(rest)
    if (m) {
      out.push(`<span class="hl-comment">${esc(m[0])}</span>`)
      i += m[0].length
      continue
    }
    // 字符串（单引号 / 双引号 / 模板串）
    m = /^('(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`)/.exec(rest)
    if (m) {
      out.push(`<span class="hl-string">${esc(m[0])}</span>`)
      i += m[0].length
      continue
    }
    // 数字
    m = /^\d+(?:\.\d+)?/.exec(rest)
    if (m) {
      out.push(`<span class="hl-number">${esc(m[0])}</span>`)
      i += m[0].length
      continue
    }
    // 标识符 / 关键字
    m = /^[A-Za-z_][A-Za-z0-9_-]*/.exec(rest)
    if (m) {
      const word = m[0]
      out.push(kw.has(word) ? `<span class="hl-keyword">${esc(word)}</span>` : esc(word))
      i += word.length
      continue
    }
    out.push(esc(rest[0]))
    i += 1
  }
  return out.join('')
}
