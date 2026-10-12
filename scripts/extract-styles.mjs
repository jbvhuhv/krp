#!/usr/bin/env node
/**
 * scripts/extract-styles.mjs
 *
 * 将 frontend/src/views/ 下 style 行数 > 400 的 .vue 文件的 <style> 块外提为
 * 同目录 .css 文件，并把原标签替换为 <style {原属性} src="./Xxx.css"></style>。
 *
 * 关键约定：
 *  - 纯移动：CSS 内容与换行符（CRLF / LF）原样保留，不做任何格式化。
 *  - 保留属性：scoped / lang="scss" / module 等原样写回标签。
 *  - 多 <style> 块（如 scoped + 非 scoped 全局块）分别外提为独立文件，避免互相覆盖：
 *        scoped 块   -> Xxx.css
 *        非 scoped 块 -> Xxx.global.css
 *        若 lang="scss"，则扩展名为 .scss
 *  - 每个文件处理前备份为 .vue.bak，成功后再删除；失败自动回滚。
 *  - 默认 dry-run：只打印统计，不改动任何文件。
 *  - 加 --apply 才真正写入，并在 frontend/ 下自动执行 npm run build。
 *
 * 用法（在项目任意目录执行均可）：
 *   node scripts/extract-styles.mjs            # dry-run，仅统计
 *   node scripts/extract-styles.mjs --apply    # 实际外提 + 运行构建
 */

import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const ROOT = path.resolve(__dirname, '..')
const VIEWS_DIR = path.resolve(ROOT, 'frontend', 'src', 'views')
const FRONTEND_DIR = path.resolve(ROOT, 'frontend')

// 与需求一致：精确匹配 <style {属性}>{内容}</style>，非贪婪匹配到第一个 </style>
const STYLE_RE = /<style\s*([^>]*)>([\s\S]*?)<\/style>/g
const STYLE_THRESHOLD = 400
const APPLY = process.argv.includes('--apply')

/** 递归收集目录下所有 .vue 文件 */
function walkVue(dir) {
  const out = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) out.push(...walkVue(full))
    else if (entry.isFile() && entry.name.endsWith('.vue')) out.push(full)
  }
  return out
}

/** 统计文本行数（兼容 CRLF / LF） */
function countLines(text) {
  if (!text) return 0
  return text.split(/\r?\n/).length
}

/** 解析单个 .vue：返回内容、所有 <style> 块，以及 style 总行数 */
function planFile(file) {
  const content = fs.readFileSync(file, 'utf8')
  const blocks = []
  STYLE_RE.lastIndex = 0
  let m
  while ((m = STYLE_RE.exec(content)) !== null) {
    blocks.push({ full: m[0], attrs: m[1].trim(), css: m[2] })
  }
  const styleLines = blocks.reduce((n, b) => n + countLines(b.full), 0)
  return { file, content, blocks, styleLines }
}

/** 根据属性推导外提文件扩展名（默认 .css，lang="scss" 时为 .scss） */
function cssExt(attrs) {
  const m = attrs.match(/lang\s*=\s*["']?(\w+)/)
  return m ? `.${m[1]}` : '.css'
}

/** 生成 CSS 目标文件名：scoped -> base.css；非 scoped -> base.global.css；重名追加序号 */
function cssTargetName(base, attrs, used) {
  const ext = cssExt(attrs)
  const scoped = /(^|\s)scoped(\s|$)/.test(attrs)
  let name = scoped ? `${base}${ext}` : `${base}.global${ext}`
  if (used.has(name)) {
    let i = 2
    while (used.has(`${base}.${i}${ext}`)) i++
    name = `${base}.${i}${ext}`
  }
  used.add(name)
  return name
}

/** 用新标签替换原 <style> 块（按出现顺序一一对应） */
function replaceStyleTags(content, blocks, cssNames) {
  STYLE_RE.lastIndex = 0
  let i = 0
  return content.replace(STYLE_RE, () => {
    const attrs = blocks[i].attrs
    const name = cssNames[i]
    i++
    const attrPart = attrs ? ` ${attrs}` : ''
    return `<style${attrPart} src="./${name}"></style>`
  })
}

function rel(p) {
  return path.relative(ROOT, p).replace(/\\/g, '/')
}

/* ------------------------------- 主流程 ------------------------------- */

const files = walkVue(VIEWS_DIR)
const plans = files.map(planFile)

const selected = plans.filter((p) => p.styleLines > STYLE_THRESHOLD)
const totalLines = selected.reduce((n, p) => n + p.styleLines, 0)

console.log(`扫描目录：${rel(VIEWS_DIR)}`)
console.log(`共 ${files.length} 个 .vue；style > ${STYLE_THRESHOLD} 行的文件 ${selected.length} 个：\n`)

for (const p of selected) {
  const names = []
  const used = new Set()
  const base = path.basename(p.file, '.vue')
  for (const b of p.blocks) names.push(cssTargetName(base, b.attrs, used))
  console.log(`  - ${rel(p.file)}  (style ${p.styleLines} 行, ${p.blocks.length} 块)`)
  console.log(`      → ${names.join(', ')}`)
}

console.log(`\n合计：将外提 ${selected.length} 个文件，共 ${totalLines} 行 style。`)

for (const p of plans) {
  if (p.blocks.length === 0) {
    console.warn(`  [warn] ${rel(p.file)} 无 <style> 块，跳过`)
  }
}

if (!APPLY) {
  console.log('\n[dry-run] 未修改任何文件。确认统计无误后，加 --apply 实际写入。')
  process.exit(0)
}

/* ------------------------------- 实际写入 ------------------------------- */

console.log('\n[apply] 开始外提…\n')
let failed = 0

for (const p of selected) {
  const dir = path.dirname(p.file)
  const base = path.basename(p.file, '.vue')
  const used = new Set()
  const cssNames = p.blocks.map((b) => cssTargetName(base, b.attrs, used))
  const bak = `${p.file}.bak`

  fs.copyFileSync(p.file, bak)
  try {
    const next = replaceStyleTags(p.content, p.blocks, cssNames)
    for (let k = 0; k < p.blocks.length; k++) {
      fs.writeFileSync(path.join(dir, cssNames[k]), p.blocks[k].css, 'utf8')
    }
    fs.writeFileSync(p.file, next, 'utf8')
    fs.unlinkSync(bak)
    console.log(`  ✓ ${rel(p.file)} → ${cssNames.join(', ')}`)
  } catch (err) {
    if (fs.existsSync(bak)) {
      fs.copyFileSync(bak, p.file)
      fs.unlinkSync(bak)
    }
    failed++
    console.error(`  ✗ ${rel(p.file)} 外提失败，已回滚：${err.message}`)
  }
}

if (failed > 0) {
  console.error(`\n[apply] 有 ${failed} 个文件处理失败，已回滚，跳过构建。`)
  process.exit(1)
}

console.log('\n[apply] 外提完成。运行 npm run build …\n')

const child = spawn('npm', ['run', 'build'], {
  cwd: FRONTEND_DIR,
  stdio: 'inherit',
  shell: true,
})

child.on('close', (code) => {
  if (code === 0) {
    console.log('\n[build] 构建通过 ✓')
  } else {
    console.error(`\n[build] 构建失败，退出码 ${code}`)
    process.exitCode = code || 1
  }
})