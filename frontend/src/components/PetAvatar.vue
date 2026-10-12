<script setup>
import { computed } from 'vue'

import { petStage } from '@/utils/petStage'

const props = defineProps({
  species: { type: String, default: 'spirit' },
  color: { type: String, default: '#22d3ee' },
  size: { type: Number, default: 64 },
  level: { type: Number, default: 1 },
  leveledUp: { type: Boolean, default: false },
  // 情绪：由后端情感状态机驱动（happy/excited/content/curious/proud/lonely/tired）
  mood: { type: String, default: 'content' },
})

let _seq = 0
_seq = (_seq + 1) % 1000
const uid = `pa${Date.now().toString(36)}${_seq}`

function clamp(v) {
  return Math.max(0, Math.min(255, Math.round(v)))
}

function shade(hex, p) {
  let h = (hex || '#22d3ee').replace('#', '')
  if (h.length === 3) h = h.split('').map((c) => c + c).join('')
  const num = parseInt(h, 16)
  let r = (num >> 16) & 255
  let g = (num >> 8) & 255
  let b = num & 255
  if (p >= 0) {
    r += (255 - r) * p
    g += (255 - g) * p
    b += (255 - b) * p
  } else {
    r *= 1 + p
    g *= 1 + p
    b *= 1 + p
  }
  return `rgb(${clamp(r)},${clamp(g)},${clamp(b)})`
}

const light = computed(() => shade(props.color, 0.55))
const base = computed(() => shade(props.color, 0.04))
const deep = computed(() => shade(props.color, -0.32))
const darker = computed(() => shade(props.color, -0.5))
const belly = computed(() => shade(props.color, 0.82))

const isCat = computed(() => props.species === 'cat')
const isFox = computed(() => props.species === 'fox')
const isRabbit = computed(() => props.species === 'rabbit')
const isBear = computed(() => props.species === 'bear')
const isDragon = computed(() => props.species === 'dragon')
const isBird = computed(() => props.species === 'bird')
const isJelly = computed(() => props.species === 'jelly')
const isSpirit = computed(() => !['cat', 'fox', 'rabbit', 'bear', 'dragon', 'bird', 'jelly'].includes(props.species))

// 进化形态：同一只宠物随等级呈现「幼年体 → 成长期 → 完全体」三种外观。
const stage = computed(() => petStage(props.level))

// 各形态的身体/五官尺寸与装饰开关：幼年偏小偏萌，完全体偏大且带能量星环。
const config = computed(() => {
  const presets = {
    baby: {
      bodyRx: 25.5, bodyRy: 25.5, bellyRx: 15, bellyRy: 12.5,
      eyeRx: 6.9, eyeRy: 8.5, eyeDx: 12.4,
      blushRx: 5.6, blushRy: 3.6, blushOpacity: 0.5,
      glow: 1.5, halo: false, aura: false, orbit: false,
    },
    teen: {
      bodyRx: 30, bodyRy: 30, bellyRx: 18, bellyRy: 15,
      eyeRx: 6, eyeRy: 7.4, eyeDx: 10,
      blushRx: 4.6, blushRy: 3, blushOpacity: 0.4,
      glow: 2.4, halo: false, aura: false, orbit: false,
    },
    adult: {
      bodyRx: 33, bodyRy: 33, bellyRx: 20, bellyRy: 17,
      eyeRx: 5.4, eyeRy: 6.9, eyeDx: 9.4,
      blushRx: 4, blushRy: 2.7, blushOpacity: 0.3,
      glow: 3.4, halo: true, aura: true, orbit: true,
    },
  }
  return presets[stage.value]
})

const shadowStyle = computed(() => ({
  baby: 'drop-shadow(0 0 6px rgba(6, 182, 212, 0.25))',
  teen: 'drop-shadow(0 0 10px rgba(6, 182, 212, 0.35))',
  adult: 'drop-shadow(0 0 16px rgba(6, 182, 212, 0.55))',
}[stage.value]))

// —— 情绪化表情（由 mood 驱动五官与装饰）——
const MOOD_KEYS = ['happy', 'excited', 'content', 'curious', 'proud', 'lonely', 'tired']
const moodKey = computed(() => {
  const m = String(props.mood || 'content').toLowerCase()
  return MOOD_KEYS.includes(m) ? m : 'content'
})
// 疲惫：闭眼；孤单：垂眼 + 下移
const eyesClosed = computed(() => moodKey.value === 'tired')
const eyeRyScale = computed(() => {
  if (moodKey.value === 'lonely') return 0.62
  if (moodKey.value === 'curious') return 1.12
  return 1
})
const eyeUpshift = computed(() => (moodKey.value === 'lonely' ? 2.2 : 0))

const mouthPath = computed(() => ({
  happy: 'M44 63 Q50 71 56 63',
  excited: 'M43 62 Q50 73 57 62',
  proud: 'M44 64 Q50 69 56 64',
  lonely: 'M45 66 Q50 62 55 66',
  tired: 'M46 65 Q50 67 54 65',
  curious: 'M45 64 Q50 69 55 64',
  content: 'M45 64 Q50 69 55 64',
}[moodKey.value]))
</script>

<template>
  <svg
    :class="['pet-avatar', `stage-${stage}`, `mood-${moodKey}`, { 'pet-avatar-levelup': leveledUp }]"
    :width="size"
    :height="size"
    viewBox="0 0 100 100"
    xmlns="http://www.w3.org/2000/svg"
    role="img"
    :style="{ filter: shadowStyle }"
  >
    <defs>
      <radialGradient :id="`body-${uid}`" cx="40%" cy="26%" r="82%">
        <stop offset="0%" :stop-color="light" />
        <stop offset="42%" :stop-color="base" />
        <stop offset="100%" :stop-color="deep" />
      </radialGradient>
      <radialGradient :id="`belly-${uid}`" cx="50%" cy="42%" r="62%">
        <stop offset="0%" :stop-color="belly" stop-opacity="0.9" />
        <stop offset="100%" :stop-color="belly" stop-opacity="0" />
      </radialGradient>
      <filter :id="`glow-${uid}`" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur :stdDeviation="config.glow" result="b" />
        <feMerge>
          <feMergeNode in="b" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>

    <ellipse cx="50" cy="92" rx="22" ry="5" :fill="darker" opacity="0.18" />

    <!-- 形态光环：完全体能量星环 / 幼年体柔光底座 -->
    <g v-if="config.aura" class="pet-aura">
      <circle cx="50" cy="58" r="39" :fill="light" opacity="0.07" />
      <ellipse
        cx="50"
        cy="58"
        rx="39"
        ry="39"
        fill="none"
        :stroke="light"
        stroke-width="1.1"
        stroke-dasharray="4 8"
        opacity="0.5"
        :filter="`url(#glow-${uid})`"
      >
        <animateTransform
          attributeName="transform"
          type="rotate"
          from="0 50 58"
          to="360 50 58"
          dur="16s"
          repeatCount="indefinite"
        />
      </ellipse>
      <g :fill="light" :filter="`url(#glow-${uid})`">
        <circle cx="50" cy="15" r="2.2" />
        <circle cx="14" cy="69" r="1.7" opacity="0.8" />
        <circle cx="86" cy="69" r="1.7" opacity="0.8" />
      </g>
    </g>
    <ellipse
      v-else-if="stage === 'baby'"
      cx="50"
      cy="83"
      rx="16"
      ry="4.6"
      :fill="light"
      opacity="0.16"
      :filter="`url(#glow-${uid})`"
    />

    <!-- 物种特征：耳朵 / 角 / 触须（绘制在身体之后，位于头部两侧） -->
    <g :fill="base" :stroke="deep" stroke-width="0">
      <template v-if="isCat">
        <path d="M28 40 L24 18 L44 32 Z" />
        <path d="M72 40 L76 18 L56 32 Z" />
      </template>
      <template v-else-if="isFox">
        <path d="M27 42 L18 16 L45 31 Z" />
        <path d="M73 42 L82 16 L55 31 Z" />
        <path d="M27 42 L18 16 L45 31 Z" :fill="belly" opacity="0.55" />
        <path d="M73 42 L82 16 L55 31 Z" :fill="belly" opacity="0.55" />
      </template>
      <template v-else-if="isRabbit">
        <ellipse cx="38" cy="22" rx="7" ry="20" />
        <ellipse cx="62" cy="22" rx="7" ry="20" />
        <ellipse cx="38" cy="22" rx="3" ry="14" :fill="belly" opacity="0.7" />
        <ellipse cx="62" cy="22" rx="3" ry="14" :fill="belly" opacity="0.7" />
      </template>
      <template v-else-if="isBear">
        <circle cx="30" cy="30" r="13" />
        <circle cx="70" cy="30" r="13" />
        <circle cx="30" cy="30" r="6" :fill="belly" opacity="0.6" />
        <circle cx="70" cy="30" r="6" :fill="belly" opacity="0.6" />
      </template>
      <template v-else-if="isDragon">
        <path d="M30 34 L22 14 L40 26 Z" :fill="deep" />
        <path d="M70 34 L78 14 L60 26 Z" :fill="deep" />
        <path d="M50 12 L44 2 L56 2 Z" :fill="base" />
      </template>
      <template v-else-if="isBird">
        <path d="M50 12 C48 4 52 2 50 -2" :stroke="deep" stroke-width="2.4" fill="none" stroke-linecap="round" />
        <circle cx="50" cy="0" r="2.6" :fill="light" />
      </template>
    </g>

    <!-- 通用身体 -->
    <ellipse cx="50" cy="58" :rx="config.bodyRx" :ry="config.bodyRy" :fill="`url(#body-${uid})`" :filter="`url(#glow-${uid})`" />
    <ellipse cx="50" cy="66" :rx="config.bellyRx" :ry="config.bellyRy" :fill="`url(#belly-${uid})`" />

    <!-- 水母触须 -->
    <g v-if="isJelly" :stroke="deep" stroke-width="2.6" fill="none" stroke-linecap="round" opacity="0.85">
      <path d="M36 82 C33 90 38 94 34 99" />
      <path d="M50 84 C50 92 50 95 50 100" />
      <path d="M64 82 C67 90 62 94 66 99" />
    </g>

    <!-- 龙翼 -->
    <g v-if="isDragon" :fill="deep" opacity="0.75">
      <path d="M22 56 C10 48 6 36 8 26 C16 36 22 42 28 48 Z" />
      <path d="M78 56 C90 48 94 36 92 26 C84 36 78 42 72 48 Z" />
    </g>

    <!-- 小鸟翅膀 -->
    <g v-if="isBird" :fill="deep" opacity="0.6">
      <path d="M22 56 C14 50 12 42 14 34 C20 42 26 48 30 52 Z" />
      <path d="M78 56 C86 50 88 42 86 34 C80 42 74 48 70 52 Z" />
    </g>

    <!-- 眼睛（按情绪切换：疲惫闭眼 / 孤单垂眼 / 其余常规） -->
    <template v-if="eyesClosed">
      <path
        :d="`M${50 - config.eyeDx - config.eyeRx} 54 Q${50 - config.eyeDx} 50 ${50 - config.eyeDx + config.eyeRx} 54`"
        stroke="#12212e" stroke-width="2.4" fill="none" stroke-linecap="round"
      />
      <path
        :d="`M${50 + config.eyeDx - config.eyeRx} 54 Q${50 + config.eyeDx} 50 ${50 + config.eyeDx + config.eyeRx} 54`"
        stroke="#12212e" stroke-width="2.4" fill="none" stroke-linecap="round"
      />
    </template>
    <template v-else>
      <ellipse :cx="50 - config.eyeDx" :cy="54 + eyeUpshift" :rx="config.eyeRx" :ry="config.eyeRy * eyeRyScale" fill="#12212e" />
      <ellipse :cx="50 + config.eyeDx" :cy="54 + eyeUpshift" :rx="config.eyeRx" :ry="config.eyeRy * eyeRyScale" fill="#12212e" />
      <circle :cx="50 - config.eyeDx - 2" :cy="51.5 + eyeUpshift" :r="config.eyeRx * 0.38" fill="#ffffff" />
      <circle :cx="50 + config.eyeDx - 2" :cy="51.5 + eyeUpshift" :r="config.eyeRx * 0.38" fill="#ffffff" />
      <circle :cx="50 - config.eyeDx + 2" :cy="57 + eyeUpshift" r="1" :fill="light" />
      <circle :cx="50 + config.eyeDx + 2" :cy="57 + eyeUpshift" r="1" :fill="light" />
      <!-- 孤单：微微下垂的八字眉 -->
      <template v-if="moodKey === 'lonely'">
        <path :d="`M${50 - config.eyeDx - 7} 45 Q${50 - config.eyeDx} 43 ${50 - config.eyeDx + 7} 46`" stroke="#12212e" stroke-width="1.6" fill="none" stroke-linecap="round" />
        <path :d="`M${50 + config.eyeDx - 7} 46 Q${50 + config.eyeDx} 43 ${50 + config.eyeDx + 7} 45`" stroke="#12212e" stroke-width="1.6" fill="none" stroke-linecap="round" />
      </template>
    </template>

    <!-- 腮红 -->
    <ellipse cx="31" cy="64" :rx="config.blushRx" :ry="config.blushRy" fill="#fb7185" :opacity="config.blushOpacity" />
    <ellipse cx="69" cy="64" :rx="config.blushRx" :ry="config.blushRy" fill="#fb7185" :opacity="config.blushOpacity" />

    <!-- 嘴 / 喙（按情绪切换弧度） -->
    <path v-if="!isBird" :d="mouthPath" stroke="#12212e" stroke-width="2" fill="none" stroke-linecap="round" />
    <path v-else d="M50 60 L45 66 L55 66 Z" fill="#fbbf24" />

    <!-- 情绪装饰：兴奋/骄傲的星光、开心的爱心、孤单的泪滴、疲惫的 z、好奇的问号 -->
    <g v-if="moodKey === 'excited' || moodKey === 'proud'" class="mood-sparkles" :fill="light">
      <path d="M24 30 l1.6 4 4 1.6 -4 1.6 -1.6 4 -1.6 -4 -4 -1.6 4 -1.6 Z" />
      <path d="M78 34 l1.2 3 3 1.2 -3 1.2 -1.2 3 -1.2 -3 -3 -1.2 3 -1.2 Z" opacity="0.85" />
    </g>
    <path v-else-if="moodKey === 'happy'" d="M77 30 c-3-3-6 0-3 3 l3 3 l3-3 c3-3 0-6-3-3 Z" fill="#fb7185" opacity="0.9" />
    <path v-else-if="moodKey === 'lonely'" d="M62 62 q2 4 0 6 q-3-2 0-6 Z" fill="#60a5fa" opacity="0.85" />
    <text v-else-if="moodKey === 'tired'" x="74" y="32" :fill="light" font-size="11" font-weight="700" opacity="0.8">z</text>
    <text v-else-if="moodKey === 'curious'" x="76" y="35" :fill="light" font-size="13" font-weight="700" opacity="0.85">?</text>

    <!-- 精灵头顶光点 -->
    <g v-if="isSpirit">
      <path d="M50 28 C49 21 51 18 50 12" :stroke="deep" stroke-width="2.2" fill="none" stroke-linecap="round" />
      <circle cx="50" cy="11" r="3.4" :fill="light" :filter="`url(#glow-${uid})`" />
      <circle cx="50" cy="11" r="1.5" fill="#ffffff" />
    </g>
  </svg>
</template>

<style scoped>
.pet-avatar {
  display: block;
  filter: drop-shadow(0 0 10px rgba(6, 182, 212, 0.35));
  transition: filter 0.3s ease, transform 0.3s ease;
}

.pet-avatar-levelup {
  animation: petAvatarPop 0.8s ease;
}

@keyframes petAvatarPop {
  0% { transform: scale(1); }
  40% { transform: scale(1.18) rotate(-4deg); }
  100% { transform: scale(1); }
}

/* —— 情绪动作：让宠物“活”起来 —— */
.pet-avatar.mood-excited {
  animation: petBounce 1.05s ease-in-out infinite;
}

@keyframes petBounce {
  0%, 100% { transform: translateY(0) scale(1); }
  50% { transform: translateY(-8%) scale(1.04); }
}

.pet-avatar.mood-happy {
  animation: petSway 2.6s ease-in-out infinite;
}

@keyframes petSway {
  0%, 100% { transform: rotate(-3deg); }
  50% { transform: rotate(3deg); }
}

.pet-avatar.mood-proud {
  animation: petFloat 3s ease-in-out infinite;
}

@keyframes petFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5%); }
}

.pet-avatar.mood-curious {
  animation: petTilt 2.4s ease-in-out infinite;
}

@keyframes petTilt {
  0%, 100% { transform: rotate(0deg); }
  40% { transform: rotate(-7deg); }
  70% { transform: rotate(3deg); }
}

.pet-avatar.mood-lonely {
  animation: petSigh 3.4s ease-in-out infinite;
  filter: saturate(0.85) drop-shadow(0 0 8px rgba(96, 165, 250, 0.35));
}

@keyframes petSigh {
  0%, 100% { transform: translateY(0) scale(1); }
  50% { transform: translateY(3%) scale(0.97); }
}

.pet-avatar.mood-tired {
  animation: petDoze 4s ease-in-out infinite;
  filter: saturate(0.7) drop-shadow(0 0 6px rgba(148, 163, 184, 0.3));
}

@keyframes petDoze {
  0%, 100% { transform: rotate(-2deg) scale(1); }
  50% { transform: rotate(2deg) scale(0.98); }
}

.mood-sparkles {
  animation: petTwinkle 1.6s ease-in-out infinite;
  transform-origin: 50px 40px;
}

@keyframes petTwinkle {
  0%, 100% { opacity: 0.5; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.1); }
}
</style>