<template>
  <div class="crystal-trophy" :class="stateClass" :style="rootStyle">
    <svg
      class="ct-svg"
      viewBox="0 0 120 128"
      width="100%"
      height="100%"
      role="img"
      :aria-label="ariaLabel"
    >
      <title>{{ ariaLabel }}</title>
      <defs>
        <linearGradient :id="`${uid}-shell`" x1="0.15" y1="0" x2="0.85" y2="1">
          <stop offset="0%" :stop-color="pal.shellLeft" />
          <stop offset="34%" :stop-color="c.light" />
          <stop offset="68%" :stop-color="c.shell" />
          <stop offset="100%" :stop-color="pal.shellRight" />
        </linearGradient>
        <linearGradient :id="`${uid}-rim`" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" :stop-color="pal.rimA" />
          <stop offset="50%" :stop-color="c.rim" />
          <stop offset="100%" :stop-color="pal.rimB" />
        </linearGradient>
        <linearGradient :id="`${uid}-edge`" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.9" />
          <stop offset="70%" stop-color="#ffffff" stop-opacity="0" />
        </linearGradient>
        <radialGradient :id="`${uid}-core`" cx="50%" cy="42%" r="66%">
          <stop v-for="(s, i) in coreStops" :key="i" :offset="s.o" :stop-color="s.col" :stop-opacity="s.op" />
        </radialGradient>
        <linearGradient :id="`${uid}-wing`" x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0%" :stop-color="c.edge" stop-opacity="0.6" />
          <stop offset="100%" :stop-color="c.shell" stop-opacity="0" />
        </linearGradient>
        <linearGradient :id="`${uid}-orbit`" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" :stop-color="c.edge" stop-opacity="0" />
          <stop offset="50%" :stop-color="c.rim" stop-opacity="0.95" />
          <stop offset="100%" :stop-color="c.edge" stop-opacity="0" />
        </linearGradient>
        <radialGradient :id="`${uid}-halo`" cx="50%" cy="50%" r="50%">
          <stop offset="0%" :stop-color="c.edge" stop-opacity="0.55" />
          <stop offset="100%" :stop-color="c.edge" stop-opacity="0" />
        </radialGradient>
        <linearGradient :id="`${uid}-metal`" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" :stop-color="pal.metalA" />
          <stop offset="28%" :stop-color="c.rim" />
          <stop offset="52%" :stop-color="c.edge" />
          <stop offset="76%" :stop-color="c.shell" />
          <stop offset="100%" :stop-color="pal.metalB" />
        </linearGradient>
        <linearGradient :id="`${uid}-gloss`" x1="0" y1="0" x2="0.25" y2="1">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.92" />
          <stop offset="48%" stop-color="#ffffff" stop-opacity="0.1" />
          <stop offset="100%" stop-color="#ffffff" stop-opacity="0" />
        </linearGradient>
        <linearGradient :id="`${uid}-inner`" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" :stop-color="c.edge" stop-opacity="0.62" />
          <stop offset="50%" stop-color="#ffffff" stop-opacity="0.08" />
          <stop offset="100%" :stop-color="c.edge" stop-opacity="0.5" />
        </linearGradient>
        <radialGradient :id="`${uid}-star`" cx="50%" cy="50%" r="50%">
          <stop offset="0%" :stop-color="c.rim" stop-opacity="0.85" />
          <stop offset="50%" :stop-color="c.edge" stop-opacity="0.3" />
          <stop offset="100%" :stop-color="c.edge" stop-opacity="0" />
        </radialGradient>
        <clipPath :id="`${uid}-body`">
          <path d="M 35 36 C 35 55, 44 67, 54 74 L 66 74 C 76 67, 85 55, 85 36 Z" />
        </clipPath>
      </defs>

      <!-- 底座能量光环 -->
      <g v-if="unlocked" class="ct-halo">
        <ellipse v-for="(r, i) in haloRings" :key="`h${i}`" cx="60" cy="108" :rx="r" :ry="r * 0.26" :stroke="c.edge" :opacity="0.5 - i * 0.1" />
        <ellipse cx="60" cy="110" rx="30" ry="20" :fill="`url(#${uid}-halo)`" opacity="0.5" />
      </g>

      <!-- 光翼（高阶） -->
      <g v-if="wings >= 1" class="ct-wings" :fill="`url(#${uid}-wing)`">
        <path d="M 46 44 C 18 34, 4 58, 24 80 C 16 60, 28 46, 48 50 Z" />
        <path d="M 74 44 C 102 34, 116 58, 96 80 C 104 60, 92 46, 72 50 Z" />
      </g>
      <g v-if="wings >= 2" class="ct-wings ct-wings-inner" :fill="`url(#${uid}-wing)`">
        <path d="M 48 50 C 30 45, 23 61, 35 74 C 29 62, 37 53, 50 55 Z" />
        <path d="M 72 50 C 90 45, 97 61, 85 74 C 91 62, 83 53, 70 55 Z" />
      </g>

      <!-- 双手柄（金属反光描边） -->
      <g class="ct-handles" fill="none" stroke-linecap="round">
        <path d="M 36 39 C 23 40, 20 53, 33 59" :stroke="`url(#${uid}-metal)`" stroke-width="4" />
        <path d="M 84 39 C 97 40, 100 53, 87 59" :stroke="`url(#${uid}-metal)`" stroke-width="4" />
        <path d="M 37 40 C 26 41, 23.5 51, 33.5 57.5" :stroke="c.rim" stroke-width="1" opacity="0.65" />
        <path d="M 83 40 C 94 41, 96.5 51, 86.5 57.5" :stroke="c.rim" stroke-width="1" opacity="0.65" />
      </g>

      <!-- 底座 -->
      <g class="ct-base">
        <ellipse cx="60" cy="94" rx="18" ry="4.6" :fill="c.deep" />
        <polygon points="42,94 78,94 83,104 37,104" :fill="`url(#${uid}-metal)`" :stroke="c.shell" stroke-width="0.8" />
        <ellipse cx="60" cy="99" rx="20" ry="5" :fill="c.shell" opacity="0.5" />
        <ellipse cx="60" cy="104" rx="23" ry="5.6" :fill="`url(#${uid}-metal)`" :stroke="c.edge" stroke-width="1" />
        <ellipse cx="60" cy="103" rx="15" ry="3.2" :fill="c.light" opacity="0.5" />
        <path d="M 39 103.6 Q 60 107.6 81 103.6" fill="none" :stroke="`url(#${uid}-gloss)`" stroke-width="1.5" opacity="0.7" stroke-linecap="round" />
      </g>

      <!-- 杯柄 -->
      <path d="M 51 74 L 69 74 L 66 82 L 54 82 Z" :fill="`url(#${uid}-metal)`" />
      <rect x="56" y="80" width="8" height="14" rx="2" :fill="pal.neck" />
      <line x1="57.4" y1="81" x2="57.4" y2="92" :stroke="c.rim" stroke-width="0.8" opacity="0.5" />

      <!-- 杯身（水晶） -->
      <path
        class="ct-body"
        d="M 35 36 C 35 55, 44 67, 54 74 L 66 74 C 76 67, 85 55, 85 36 Z"
        :fill="`url(#${uid}-shell)`"
        :stroke="c.shell"
        stroke-width="1.2"
      />

      <!-- 棱面彩色折射（分光） -->
      <g v-if="unlocked" class="ct-prism-facets" :clip-path="`url(#${uid}-body)`">
        <path d="M 35 36 L 60 36 L 54 74 Z" :fill="pal.facets[0]" opacity="0.2" />
        <path d="M 60 36 L 85 36 L 66 74 Z" :fill="pal.facets[pal.facets.length - 1]" opacity="0.2" />
        <path d="M 54 74 L 66 74 L 60 36 Z" :fill="pal.facets[Math.floor(pal.facets.length / 2)]" opacity="0.16" />
      </g>

      <!-- 内缘折射反光 -->
      <path class="ct-inner" d="M 39 38 C 39 54, 46 66, 54 72" fill="none" :stroke="`url(#${uid}-inner)`" stroke-width="1.6" stroke-linecap="round" />
      <path class="ct-inner ct-inner-r" d="M 81 38 C 81 54, 74 66, 66 72" fill="none" :stroke="`url(#${uid}-inner)`" stroke-width="1.1" stroke-linecap="round" />

      <!-- 内部能量芯 -->
      <ellipse v-if="hasCoreBloom" class="ct-core-bloom" cx="60" cy="52" rx="18" ry="24" :fill="accent" opacity="0.16" />
      <ellipse v-if="hasPrismCore" class="ct-core-bloom ct-core-bloom-2" cx="60" cy="59" rx="12" ry="16" :fill="accent2" opacity="0.22" />
      <ellipse v-if="unlocked" class="ct-core" cx="60" cy="52" rx="14" ry="20" :fill="`url(#${uid}-core)`" />
      <ellipse v-if="unlocked" class="ct-core-hl" cx="60" cy="45.5" rx="4.4" ry="6.8" fill="#ffffff" opacity="0.5" />

      <!-- 水晶棱面（彩虹分光） -->
      <g class="ct-facets" fill="none" stroke-width="0.8" opacity="0.6">
        <line x1="60" y1="37" x2="60" y2="73" :stroke="pal.facets[Math.min(1, pal.facets.length - 1)]" />
        <path d="M 47 37 C 47 52, 51 66, 57 73" :stroke="pal.facets[0]" />
        <path d="M 73 37 C 73 52, 69 66, 63 73" :stroke="pal.facets[pal.facets.length - 1]" />
        <path d="M 40 50 Q 60 57 80 50" :stroke="pal.facets[Math.min(2, pal.facets.length - 1)]" />
        <path d="M 42 62 Q 60 68 78 62" :stroke="pal.facets[Math.floor(pal.facets.length / 2)]" />
      </g>
      <!-- 棱面反光高光 -->
      <g class="ct-facet-hl" fill="none" stroke="#ffffff" stroke-width="0.55" opacity="0.5">
        <line x1="61.4" y1="38" x2="61.4" y2="72" />
        <path d="M 41.6 51 Q 60 58 78 51" />
        <path d="M 43.4 63 Q 60 69 76 63" />
      </g>

      <!-- 左侧镜面高光 + 顶边高光 -->
      <path d="M 42 39 C 41 53, 46 65, 53 72 C 47 64, 44 52, 45 39 Z" :fill="`url(#${uid}-gloss)`" />
      <path class="ct-edge-hl" d="M 41 37 L 79 37 L 76 44" :stroke="`url(#${uid}-edge)`" stroke-width="1.4" fill="none" stroke-linecap="round" />

      <!-- 杯口 -->
      <ellipse cx="60" cy="36" rx="25" ry="7" :fill="c.deep" />
      <ellipse cx="60" cy="36" rx="25" ry="7" :fill="`url(#${uid}-rim)`" opacity="0.92" />
      <ellipse cx="60" cy="36" rx="25" ry="7" fill="none" :stroke="c.edge" stroke-width="0.8" opacity="0.85" />
      <ellipse cx="60" cy="36" rx="21" ry="5.2" :fill="c.deep" opacity="0.85" />
      <ellipse v-if="unlocked" cx="60" cy="36" rx="14" ry="3.4" :fill="`url(#${uid}-core)`" />
      <path d="M 37 34.5 Q 60 27.5 83 34.5" fill="none" :stroke="`url(#${uid}-edge)`" stroke-width="1.2" stroke-linecap="round" opacity="0.85" />

      <!-- 高阶层宝石镶嵌 -->
      <g v-if="gems && unlocked" class="ct-gems">
        <circle cx="42" cy="35" r="1.7" :fill="accent2" :stroke="c.edge" stroke-width="0.4" />
        <circle cx="60" cy="30.4" r="1.9" :fill="accent" :stroke="c.edge" stroke-width="0.4" />
        <circle cx="78" cy="35" r="1.7" :fill="accent2" :stroke="c.edge" stroke-width="0.4" />
      </g>

      <!-- 高阶层环绕轨道 -->
      <g v-if="orbits >= 1" class="ct-orbit" :stroke="`url(#${uid}-orbit)`" fill="none">
        <ellipse cx="60" cy="52" rx="45" ry="12.5" stroke-width="1.6" />
        <ellipse v-if="orbits >= 2" cx="60" cy="52" rx="37" ry="9.5" transform="rotate(24 60 52)" stroke-width="1.2" />
      </g>

      <!-- 顶部星徽 -->
      <g class="ct-star">
        <circle v-if="unlocked" class="ct-star-halo" cx="60" cy="15" r="13" :fill="`url(#${uid}-star)`" />
        <g v-if="starRays && unlocked" class="ct-star-rays" :stroke="tier >= 9 ? accent2 : c.rim" stroke-width="1.1" stroke-linecap="round" opacity="0.85">
          <line x1="60" y1="1.5" x2="60" y2="5" />
          <line x1="48.5" y1="9" x2="51.8" y2="11.2" />
          <line x1="71.5" y1="9" x2="68.2" y2="11.2" />
          <line x1="49" y1="21.5" x2="52.4" y2="19.2" />
          <line x1="71" y1="21.5" x2="67.6" y2="19.2" />
        </g>
        <polygon
          points="60,6 62,11.3 67.6,11.5 63.2,15.1 64.7,20.5 60,17.4 55.3,20.5 56.8,15.1 52.4,11.5 58,11.3"
          :fill="pal.star"
          :stroke="c.shell"
          stroke-width="0.7"
        />
      </g>

      <!-- 创世棱光（顶级·彩虹分光） -->
      <g v-if="prismatic" class="ct-prism" stroke-width="1.2" opacity="0.75">
        <line x1="60" y1="52" x2="60" y2="8" :stroke="pal.facets[0]" />
        <line x1="60" y1="52" x2="104" y2="34" :stroke="pal.facets[Math.min(1, pal.facets.length - 1)]" />
        <line x1="60" y1="52" x2="16" y2="34" :stroke="pal.facets[pal.facets.length - 1]" />
        <line x1="60" y1="52" x2="98" y2="82" :stroke="pal.facets[Math.floor(pal.facets.length / 2)]" />
        <line x1="60" y1="52" x2="22" y2="82" :stroke="pal.facets[Math.min(2, pal.facets.length - 1)]" />
      </g>

      <!-- 星尘微光 -->
      <g v-if="unlocked" class="ct-sparks" :fill="tier >= 8 ? accent : c.rim">
        <path
          v-for="(s, i) in sparkles"
          :key="`s${i}`"
          :d="`M ${s.x},${s.y - s.s} L ${s.x + s.s * 0.26},${s.y - s.s * 0.26} L ${s.x + s.s},${s.y} L ${s.x + s.s * 0.26},${s.y + s.s * 0.26} L ${s.x},${s.y + s.s} L ${s.x - s.s * 0.26},${s.y + s.s * 0.26} L ${s.x - s.s},${s.y} L ${s.x - s.s * 0.26},${s.y - s.s * 0.26} Z`"
        />
      </g>
    </svg>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  tier: { type: Number, default: 1 },
  unlocked: { type: Boolean, default: false },
  current: { type: Boolean, default: false },
  size: { type: [Number, String], default: 56 },
})

const uid = `ct-${Math.random().toString(36).slice(2, 9)}`

const MATERIALS = {
  jade: { light: '#a7f3d0', shell: '#34d399', deep: '#0f766e', edge: '#6ee7b7', rim: '#d1fae5', core: '#fbbf24', core2: '#fef08a' },
  teal: { light: '#99f6e4', shell: '#2dd4bf', deep: '#115e59', edge: '#5eead4', rim: '#ccfbf1', core: '#fb7185', core2: '#fecdd3' },
  sapphire: { light: '#bae6fd', shell: '#38bdf8', deep: '#1e40af', edge: '#7dd3fc', rim: '#e0f2fe', core: '#f472b6', core2: '#fbcfe8' },
  indigo: { light: '#c7d2fe', shell: '#6366f1', deep: '#312e81', edge: '#a5b4fc', rim: '#e0e7ff', core: '#fcd34d', core2: '#fef3c7' },
  amethyst: { light: '#e9d5ff', shell: '#a855f7', deep: '#6b21a8', edge: '#c4b5fd', rim: '#f3e8ff', core: '#22d3ee', core2: '#a5f3fc' },
  orchid: { light: '#f5d0fe', shell: '#d946ef', deep: '#86198f', edge: '#f0abfc', rim: '#fae8ff', core: '#22d3ee', core2: '#a5f3fc' },
  gold: { light: '#fde68a', shell: '#f59e0b', deep: '#b45309', edge: '#fcd34d', rim: '#fef3c7', core: '#38bdf8', core2: '#bae6fd' },
  coral: { light: '#fecdd3', shell: '#fb7185', deep: '#9f1239', edge: '#fda4af', rim: '#fff1f2', core: '#38bdf8', core2: '#bae6fd' },
  platinum: { light: '#ffffff', shell: '#cbd5e1', deep: '#64748b', edge: '#e2e8f0', rim: '#ffffff', core: '#a78bfa', core2: '#ddd6fe' },
  obsidian: { light: '#64748b', shell: '#334155', deep: '#0b0f17', edge: '#22d3ee', rim: '#94a3b8', core: '#f472b6', core2: '#fbcfe8' },
  diamond: { light: '#ffffff', shell: '#7dd3fc', deep: '#3b82f6', edge: '#a5f3fc', rim: '#ffffff', core: '#f472b6', core2: '#67e8f9' },
  eternal: { light: '#ffffff', shell: '#e2e8f0', deep: '#94a3b8', edge: '#f0abfc', rim: '#ffffff', core: '#67e8f9', core2: '#a5f3fc' },
}

const MATERIAL_BY_TIER = [
  'jade', 'teal',
  'sapphire', 'indigo',
  'amethyst', 'orchid',
  'gold', 'coral',
  'platinum', 'obsidian',
  'diamond', 'eternal',
]

const LOCKED_COLOR = { light: '#3a4557', shell: '#2a3544', deep: '#161d28', edge: '#475569', rim: '#334155', core: '#475569', core2: '#475569' }

const SPARKLES = [
  { x: 24, y: 26, s: 2.4 },
  { x: 96, y: 30, s: 2.0 },
  { x: 34, y: 82, s: 2.2 },
  { x: 87, y: 84, s: 2.6 },
  { x: 17, y: 60, s: 1.8 },
  { x: 103, y: 62, s: 2.2 },
  { x: 47, y: 15, s: 1.6 },
  { x: 74, y: 17, s: 1.8 },
]

const tier = computed(() => Math.min(12, Math.max(1, props.tier || 1)))
const unlocked = computed(() => props.unlocked)

const c = computed(() =>
  unlocked.value ? MATERIALS[MATERIAL_BY_TIER[tier.value - 1]] : LOCKED_COLOR
)

function hexToHsl(hex) {
  let v = String(hex).replace('#', '')
  if (v.length === 3) v = v.split('').map((x) => x + x).join('')
  const r = parseInt(v.slice(0, 2), 16) / 255
  const g = parseInt(v.slice(2, 4), 16) / 255
  const b = parseInt(v.slice(4, 6), 16) / 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  let h = 0
  let s = 0
  const d = max - min
  if (d) {
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    if (max === r) h = (g - b) / d + (g < b ? 6 : 0)
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
    h /= 6
  }
  return { h: h * 360, s: s * 100, l: l * 100 }
}

function hslToHex(h, s, l) {
  const hh = (((h % 360) + 360) % 360) / 360
  const ss = Math.max(0, Math.min(100, s)) / 100
  const ll = Math.max(0, Math.min(100, l)) / 100
  let r
  let g
  let b
  if (!ss) {
    r = g = b = ll
  } else {
    const hue2rgb = (p, q, t) => {
      let tt = t
      if (tt < 0) tt += 1
      if (tt > 1) tt -= 1
      if (tt < 1 / 6) return p + (q - p) * 6 * tt
      if (tt < 1 / 2) return q
      if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6
      return p
    }
    const q = ll < 0.5 ? ll * (1 + ss) : ll + ss - ll * ss
    const p = 2 * ll - q
    r = hue2rgb(p, q, hh + 1 / 3)
    g = hue2rgb(p, q, hh)
    b = hue2rgb(p, q, hh - 1 / 3)
  }
  const to = (x) => Math.round(x * 255).toString(16).padStart(2, '0')
  return `#${to(r)}${to(g)}${to(b)}`
}

function shiftHue(hex, deg, lightAdj = 0, satAdj = 0) {
  const { h, s, l } = hexToHsl(hex)
  return hslToHex(h + deg, s + satAdj, l + lightAdj)
}

// 外形配色组：以主色（shell）为基准，色相跨度随档位递增
const pal = computed(() => {
  const mat = c.value
  const on = unlocked.value
  const t = on ? tier.value : 1
  const d = on ? Math.min(66, 16 + t * 4) : 0
  const spread = on ? Math.min(74, 18 + t * 4.5) : 0
  const n = on ? Math.min(7, 3 + Math.floor(t / 2)) : 1
  const facets = Array.from({ length: n }, (_, i) =>
    shiftHue(mat.shell, n === 1 ? 0 : -spread + (2 * spread * i) / (n - 1), -4)
  )
  return {
    shellLeft: shiftHue(mat.shell, -d, 6),
    shellRight: shiftHue(mat.shell, d, -20),
    rimA: shiftHue(mat.shell, -d * 1.1, 4),
    rimB: shiftHue(mat.shell, d * 1.1, 4),
    metalA: shiftHue(mat.shell, -d * 0.8, -14),
    metalB: shiftHue(mat.shell, d * 0.8, -14),
    neck: shiftHue(mat.shell, d * 1.2, 2),
    star: shiftHue(mat.shell, -d * 0.5, 10),
    facets,
  }
})

const accent = computed(() => c.value.core || '#67e8f9')
const accent2 = computed(() => c.value.core2 || accent.value)

const hasCoreBloom = computed(() => unlocked.value && tier.value >= 5)
const hasPrismCore = computed(() => unlocked.value && tier.value >= 9)

const coreStops = computed(() => {
  const a = accent.value
  const a2 = accent2.value
  const mat = c.value
  if (hasPrismCore.value) {
    return [
      { o: '0%', col: '#ffffff', op: 1 },
      { o: '18%', col: a2, op: 1 },
      { o: '40%', col: a, op: 0.95 },
      { o: '60%', col: mat.rim, op: 0.8 },
      { o: '80%', col: mat.edge, op: 0.55 },
      { o: '100%', col: mat.shell, op: 0.05 },
    ]
  }
  if (hasCoreBloom.value) {
    return [
      { o: '0%', col: '#ffffff', op: 1 },
      { o: '22%', col: a2, op: 0.98 },
      { o: '52%', col: a, op: 0.88 },
      { o: '80%', col: mat.edge, op: 0.58 },
      { o: '100%', col: mat.shell, op: 0.07 },
    ]
  }
  return [
    { o: '0%', col: '#ffffff', op: 1 },
    { o: '32%', col: a, op: 0.92 },
    { o: '72%', col: mat.edge, op: 0.55 },
    { o: '100%', col: mat.shell, op: 0.09 },
  ]
})

const stateClass = computed(() => ({
  'is-unlocked': unlocked.value,
  'is-current': props.current && unlocked.value,
  'is-locked': !unlocked.value,
}))

const rootStyle = computed(() => {
  const glow = unlocked.value ? Math.round(5 + tier.value * 1.2) : 0
  return {
    '--glow': glow,
    '--glow-color': unlocked.value ? c.value.edge : 'transparent',
    width: `${props.size}px`,
    height: `${props.size}px`,
  }
})

const ariaLabel = computed(() => {
  const matName = {
    jade: '青玉', teal: '碧玺', sapphire: '蓝晶', indigo: '靛青',
    amethyst: '紫晶', orchid: '兰紫', gold: '黄金', coral: '珊瑚',
    platinum: '铂金', obsidian: '黑曜', diamond: '钻石', eternal: '永恒',
  }[MATERIAL_BY_TIER[tier.value - 1]]
  const state = !unlocked.value ? '未点亮' : props.current ? '当前' : '已点亮'
  return `${state}${matName}水晶奖杯 · 第 ${tier.value} 阶`
})

const haloRings = computed(() => {
  if (tier.value >= 11) return [20, 26, 32, 38]
  if (tier.value >= 8) return [22, 28, 34]
  if (tier.value >= 4) return [24, 30]
  return [24]
})

const wings = computed(() => {
  if (tier.value >= 9) return 2
  if (tier.value >= 5) return 1
  return 0
})

const orbits = computed(() => {
  if (tier.value >= 11) return 2
  if (tier.value >= 7) return 1
  return 0
})

const gems = computed(() => tier.value >= 3)
const starRays = computed(() => tier.value >= 6)
const prismatic = computed(() => tier.value >= 11 && unlocked.value)

const sparkles = computed(() => SPARKLES.slice(0, Math.min(SPARKLES.length, Math.max(1, tier.value - 3))))
</script>

<style scoped>
.crystal-trophy {
  position: relative;
  display: inline-block;
  filter:
    drop-shadow(0 0 calc(var(--glow, 0) * 0.55px) var(--glow-color, transparent))
    drop-shadow(0 0 calc(var(--glow, 0) * 1.7px) color-mix(in srgb, var(--glow-color, #67e8f9) 45%, transparent));
  transition: filter 0.4s ease;
}

.ct-svg {
  position: relative;
  z-index: 1;
  display: block;
  overflow: visible;
}

.ct-halo ellipse {
  fill: none;
  stroke-width: 1.1;
}

.ct-wings path {
  opacity: 0.75;
}

.ct-wings-inner path {
  opacity: 0.5;
}

.ct-core {
  filter: blur(0.4px);
}

/* 棱面彩色折射 */
.ct-prism-facets {
  mix-blend-mode: screen;
}

.ct-facets {
  mix-blend-mode: screen;
}

/* 能量芯对比色光晕（随档位递增） */
.ct-core-bloom {
  filter: blur(4px);
  transform-box: fill-box;
  transform-origin: center;
  animation: ct-core-glow 4.2s ease-in-out infinite;
}

.ct-core-bloom-2 {
  filter: blur(5px);
  animation-duration: 3.1s;
  animation-direction: alternate-reverse;
}

@keyframes ct-core-glow {
  0%, 100% { opacity: 0.08; transform: scale(0.92); }
  50% { opacity: 0.26; transform: scale(1.06); }
}

/* 能量芯高光脉冲 */
.ct-core-hl {
  transform-box: fill-box;
  transform-origin: center;
  animation: ct-pulse 3.4s ease-in-out infinite;
}

.ct-orbit {
  transform-box: fill-box;
  transform-origin: center;
  animation: ct-spin 22s linear infinite;
}

.ct-prism {
  transform-box: fill-box;
  transform-origin: 60px 52px;
  animation: ct-spin 30s linear infinite;
}

/* 星徽光晕呼吸 */
.ct-star-halo {
  transform-box: fill-box;
  transform-origin: center;
  animation: ct-halo-breathe 3.6s ease-in-out infinite;
}

/* 宝石闪烁 */
.ct-gems circle {
  transform-box: fill-box;
  transform-origin: center;
  animation: ct-twinkle 2.6s ease-in-out infinite;
}

.ct-gems circle:nth-child(2) { animation-delay: 0.6s; }
.ct-gems circle:nth-child(3) { animation-delay: 1.2s; }

.ct-sparks path {
  transform-box: fill-box;
  transform-origin: center;
  animation: ct-twinkle 3s ease-in-out infinite;
}

.ct-sparks path:nth-child(2) { animation-delay: 0.5s; }
.ct-sparks path:nth-child(3) { animation-delay: 1s; }
.ct-sparks path:nth-child(4) { animation-delay: 1.5s; }
.ct-sparks path:nth-child(5) { animation-delay: 0.8s; }
.ct-sparks path:nth-child(6) { animation-delay: 1.3s; }
.ct-sparks path:nth-child(7) { animation-delay: 0.3s; }

@keyframes ct-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes ct-twinkle {
  0%, 100% { opacity: 0.35; transform: scale(0.7); }
  50% { opacity: 1; transform: scale(1.05); }
}

@keyframes ct-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.78; }
}

@keyframes ct-halo-breathe {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 1; }
}

/* 已点亮：水晶呼吸 */
.is-unlocked .ct-svg {
  animation: ct-breath 4.6s ease-in-out infinite;
}

.is-current .ct-svg {
  animation: ct-breath 2.6s ease-in-out infinite;
}

@keyframes ct-breath {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.04); }
}

/* 未点亮：暗色剪影 */
.is-locked {
  filter: saturate(0.2) brightness(0.7);
  opacity: 0.32;
}

@media (prefers-reduced-motion: reduce) {
  .ct-svg,
  .ct-orbit,
  .ct-prism,
  .ct-core-hl,
  .ct-core-bloom,
  .ct-star-halo,
  .ct-gems circle,
  .ct-sparks path {
    animation: none;
  }
}
</style>