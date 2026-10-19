/** Node 构建配置的最小类型声明（离线环境无法安装 @types/node 时的替代）。
 * 仅覆盖 vite.config.ts 用到的 node:url 与 import.meta.url，供 tsconfig.node.json 类型检查。
 */

declare module 'node:url' {
  export class URL {
    constructor(input: string, base?: string | URL)
    toString(): string
  }
  export function fileURLToPath(url: string | URL): string
}

interface ImportMeta {
  url: string
}