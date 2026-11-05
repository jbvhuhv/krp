<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'

import { petApi } from '@/api'
import { useUserStore } from '@/stores/user'
import PetAvatar from '@/components/PetAvatar.vue'
import HoloTrophyIcon from '@/components/HoloTrophyIcon.vue'
import { petStage, petStageLabel } from '@/utils/petStage'
import treeImg from '@/assets/cognitive-tree-cutout.png'
import treeImgWebp from '@/assets/cognitive-tree-cutout.png?format=webp'

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return { text: '夜深了，仍在探索', sub: '知识的星空永不熄灭' }
  if (hour < 12) return { text: '早上好，你的认知正在生长', sub: '新的一天，新的可能' }
  if (hour < 14) return { text: '中午好，稍作休憩', sub: '整理思绪，再出发' }
  if (hour < 18) return { text: '下午好，保持专注', sub: '深度学习正在进行' }
  return { text: '晚上好，回顾与反思', sub: '今日所学，明日之基' }
})


const petData = ref({
  level: 1,
  exp: 0,
  exp_max: 100,
  fruits: 0,
  total_harvested: 0,
  medal: null,
  medals: [],
  next_medal: null,
  next_medal_threshold: null,
  tree_growth: 0,
  harvestable_cycles: 0,
  nodes_to_mature: 0,

  name: '',
  species: '',
  color: '#22d3ee',
  personality: '',
  knowledge_total: 0,
  tree_fruits: 0,
  threads: [],
  // 情感状态机
  mood: 'content',
  bond: 0,
  bond_level: '初识',
  streak_days: 0,
  greeting: null,
})
const petLoading = ref(false)
const petLoadError = ref(false)
const petNeedLogin = ref(false)
const userStore = useUserStore()
const feedAnimating = ref(false)
const leveledUpPulse = ref(false)
const harvestReady = computed(
  () => petData.value.tree_growth >= 100 || (petData.value.harvestable_cycles || 0) > 0,
)
// 宠物主动关怀气泡（每日首次进入时后端返回一次）
const careGreeting = ref('')
let careTimer = null

// 情绪展示映射（与后端 pet_service.MOODS 对应）
const MOOD_META = {
  happy: { emoji: '😊', label: '开心' },
  excited: { emoji: '🤩', label: '兴奋' },
  content: { emoji: '😌', label: '平静' },
  curious: { emoji: '🤔', label: '好奇' },
  proud: { emoji: '😎', label: '自豪' },
  lonely: { emoji: '🥺', label: '想念' },
  tired: { emoji: '😴', label: '疲惫' },
}
const moodMeta = computed(() => MOOD_META[petData.value.mood] || MOOD_META.content)
const bondPercent = computed(() => Math.min(100, Math.max(0, petData.value.bond || 0)))

// 成就奖杯：与后端 12 档 MEDAL_TIERS 对应，3D 水晶奖杯随星阶递进形态（金属材质分级）
// 卡片强调色沿用 HoloTrophyIcon 的材质 shell 色，保证卡片与奖杯材质一一呼应
const TIER_ACCENTS = [
  '#34d399', '#2dd4bf', '#38bdf8', '#6366f1', '#a855f7', '#d946ef',
  '#f59e0b', '#fb7185', '#cbd5e1', '#22d3ee', '#7dd3fc', '#f0abfc',
]
const tierAccent = (i) => TIER_ACCENTS[i] || '#67e8f9'
const medalList = computed(() => petData.value.medals || [])
const unlockedCount = computed(() => medalList.value.filter((m) => m.unlocked).length)
const currentIndex = computed(() => {
  let idx = -1
  medalList.value.forEach((m, i) => {
    if (m.unlocked) idx = i
  })
  return idx
})
const currentTier = computed(() => currentIndex.value + 1)
const currentMedal = computed(() => (currentIndex.value >= 0 ? medalList.value[currentIndex.value] : null))
const nextMedalInfo = computed(() => {
  const id = petData.value.next_medal
  if (!id) return null
  const meta = medalList.value.find((m) => m.id === id) || { name: '星阶', threshold: 0 }
  const threshold = petData.value.next_medal_threshold || meta.threshold || 0
  const need = Math.max(0, threshold - petData.value.total_harvested)
  return { id, name: meta.name, threshold, need }
})
const achProgress = computed(() => {
  if (!nextMedalInfo.value) return 100
  const target = nextMedalInfo.value.threshold || 1
  return Math.min(100, Math.round((petData.value.total_harvested / target) * 100))
})
// 认知星图（水晶奖杯殿堂）弹窗开关
const achievementVisible = ref(false)
// 收取果实瞬间点亮新星阶的提示
const newMedalBanner = ref(null)

const SPECIES_LABEL = {
  spirit: '光之精灵',
  jelly: '泡泡水母',
  fox: '小狐狸',
  cat: '猫咪',
  rabbit: '小兔子',
  bear: '小熊',
  dragon: '小龙',
  bird: '小鸟',
}
const speciesLabel = computed(() => SPECIES_LABEL[petData.value.species] || '知识精灵')

const stageKey = computed(() => petStage(petData.value.level))
const stageLabel = computed(() => petStageLabel(petData.value.level))
// 升级瞬间的进化提示（等级跃迁到新形态时短暂高亮）
const evolvingStage = ref(false)

// —— 认知之树：真实盆景素材 + 树冠发光果实 ——
// 树体为一张去背 PNG（形态固定），成长进度只体现为树冠上逐颗长出的发光果实。
const MAX_TREE_FRUITS = 8

// 树冠内部预置的果实锚点（百分比，相对树图容器定位）
const FRUIT_ANCHORS = [
  { x: 30, y: 19 },
  { x: 50, y: 18 },
  { x: 69, y: 20 },
  { x: 22, y: 26 },
  { x: 40, y: 23 },
  { x: 60, y: 25 },
  { x: 48, y: 28 },
  { x: 74, y: 31 },
]

// 树上果实数：随成长进度（0 → 100）逐颗长出；成熟（含一次性导入的溢出轮次）时 8 颗全部可收
const harvestableCount = computed(() => {
  if ((petData.value.harvestable_cycles || 0) > 0) return MAX_TREE_FRUITS
  const growth = Math.min(100, Math.max(0, petData.value.tree_growth || 0))
  return Math.floor((growth / 100) * MAX_TREE_FRUITS + 1e-6)
})

const visibleFruits = computed(() => FRUIT_ANCHORS.slice(0, harvestableCount.value))

const treeFigureRef = ref(null)
const petAvatarRef = ref(null)
const harvesting = ref(false)


async function loadPetStatus() {
  petLoadError.value = false
  petNeedLogin.value = false
  try {
    const data = await petApi.getStatus()
    petData.value = data
    // 主动关怀：每日首次进入时，宠物主动开口
    if (data.greeting) {
      careGreeting.value = data.greeting
      if (careTimer) clearTimeout(careTimer)
      careTimer = setTimeout(() => {
        careGreeting.value = ''
      }, 9000)
    }
  } catch (e) {
    if (e?.response?.status === 401 || !userStore.isLoggedIn) {
      petNeedLogin.value = true
    } else {
      petLoadError.value = true
    }
  }
}

async function handleHarvest() {
  petLoading.value = true
  try {
    const data = await petApi.harvest()
    petData.value.fruits = data.fruits
    petData.value.tree_growth = data.tree_growth
    if (data.new_medal) {
      const hit = medalList.value.find((m) => m.id === data.new_medal)
      newMedalBanner.value = { name: hit?.name || '星阶' }
      setTimeout(() => { newMedalBanner.value = null }, 3200)
    }
    await loadPetStatus()
  } catch {
    // 错误已在拦截器中提示
  } finally {
    petLoading.value = false
  }
}

async function handleFruitClick() {
  if (harvesting.value || petLoading.value) return
  // 未成熟时给出明确反馈：此前是静默 return，用户会以为「点了没反应」
  if (!harvestReady.value) {
    const remain = petData.value.nodes_to_mature || 0
    ElMessage.info(
      remain > 0
        ? `知识树还在成长，再积累 ${remain} 个知识点就会结出新果实`
        : '知识树还在成长，继续积累知识点就能结果啦',
    )
    return
  }
  harvesting.value = true
  const target = petAvatarRef.value?.getBoundingClientRect()
  const els = treeFigureRef.value
    ? Array.from(treeFigureRef.value.querySelectorAll('.tree-fruit'))
    : []
  const anims = []
  els.forEach((el) => {
    const rect = el.getBoundingClientRect()
    const dx = target
      ? target.left + target.width / 2 - (rect.left + rect.width / 2)
      : window.innerWidth - (rect.left + rect.width / 2)
    const dy = target
      ? target.top + target.height / 2 - (rect.top + rect.height / 2)
      : window.innerHeight - (rect.top + rect.height / 2)
    anims.push(
      el.animate(
        [
          { transform: 'translate(0, 0) scale(1)', opacity: 1, offset: 0 },
          { transform: `translate(${dx * 0.32}px, ${dy * 0.32 - 16}px) scale(1.08)`, opacity: 1, offset: 0.42 },
          { transform: `translate(${dx}px, ${dy}px) scale(0.28)`, opacity: 0, offset: 1 },
        ],
        { duration: 840, easing: 'cubic-bezier(0.55, -0.15, 0.7, 1)', fill: 'forwards' },
      ),
    )
  })
  try {
    await Promise.all(anims.map((a) => a.finished.catch(() => {})))
    await handleHarvest()
  } finally {
    els.forEach((el) => el.getAnimations().forEach((a) => a.cancel()))
    harvesting.value = false
  }
}

async function handleFeed() {
  petLoading.value = true
  feedAnimating.value = true
  try {
    const data = await petApi.feed()
    const beforeStage = stageKey.value
    petData.value = { ...petData.value, ...data }
    if (data.leveled_up) {
      leveledUpPulse.value = true
      setTimeout(() => { leveledUpPulse.value = false }, 900)
      if (stageKey.value !== beforeStage) {
        evolvingStage.value = true
        setTimeout(() => { evolvingStage.value = false }, 2600)
      }
    }
    setTimeout(() => { feedAnimating.value = false }, 800)
  } catch {
    feedAnimating.value = false
  } finally {
    petLoading.value = false
  }
}

onMounted(async () => {
  await loadPetStatus()
})
</script>

<template>
  <div class="dashboard-page">
    <div v-if="petNeedLogin" :style="{ margin: '0 0 16px', padding: '10px 16px', borderRadius: '10px', background: 'rgba(34,211,238,0.08)', border: '1px solid rgba(34,211,238,0.35)', color: '#8fe3f5', fontSize: '13px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }">
      <span>登录后即可查看你的知识花园与成长数据</span>
      <el-button size="small" type="primary" @click="userStore.openLoginModal()">去登录</el-button>
    </div>
    <div v-if="petLoadError" :style="{ margin: '0 0 16px', padding: '10px 16px', borderRadius: '10px', background: 'rgba(248,81,73,0.08)', border: '1px solid rgba(248,81,73,0.35)', color: '#f0a8a3', fontSize: '13px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }">
      <span>数据加载失败，展示的可能是默认值</span>
      <el-button size="small" @click="loadPetStatus">重新加载</el-button>
    </div>
    <div class="ambient-glow glow-a"></div>
    <div class="ambient-glow glow-b"></div>

    <header class="hero">
      <div class="hero-main">
        <h1 class="greeting-text">{{ greeting.text }}</h1>
        <p class="greeting-sub">{{ greeting.sub }}</p>
      </div>
      <div class="hero-badges">
        <div class="hero-badge">
          <span class="badge-label">知识精灵</span>
          <span class="badge-value">Lv.{{ petData.level }}</span>
        </div>
        <div class="hero-badge">
          <span class="badge-label">知识点</span>
          <span class="badge-value">📚 {{ petData.knowledge_total }}</span>
        </div>
        <div class="hero-badge">
          <span class="badge-label">累计果实</span>
          <span class="badge-value">🍎 {{ petData.total_harvested }}</span>
        </div>
        <div
          class="hero-badge medal-badge achievement-badge"
          :class="{ 'medal-locked': !currentMedal }"
          role="button"
          tabindex="0"
          @click="achievementVisible = true"
          @keyup.enter="achievementVisible = true"
        >
          <span class="badge-label">认知星图</span>
          <span class="badge-value">
            <HoloTrophyIcon
              class="ach-mini"
              :tier="currentTier || 1"
              :unlocked="!!currentMedal"
              :size="20"
            />
            <template v-if="currentMedal">{{ currentMedal.name }}</template>
            <template v-else>未点亮</template>
          </span>
        </div>
      </div>
    </header>


    <div class="garden-grid">
      <section class="tree-card">
        <div class="card-stars"></div>
        <div class="card-glow"></div>
        <div class="card-shine"></div>
        <div class="card-head">
          <div class="section-title">
            <span class="title-dot"></span>认知之树
          </div>

        </div>
        <div class="tree-container">
          <div class="tree-stage">
            <div ref="treeFigureRef" class="tree-figure">
              <picture class="tree-picture">
                <source :srcset="treeImgWebp" type="image/webp" />
                <img class="tree-img" :src="treeImg" alt="认知之树" draggable="false" />
              </picture>
              <button
                v-for="(fruit, i) in visibleFruits"
                :key="i"
                type="button"
                class="tree-fruit"
                :class="{ 'is-ripe': harvestReady }"
                :style="{ left: fruit.x + '%', top: fruit.y + '%' }"
                aria-label="收取知识果实"
                @click="handleFruitClick"
              >
                <span class="fruit-glow"></span>
                <span class="fruit-core"></span>
              </button>
            </div>
            <div class="hex-base" aria-hidden="true">
              <svg viewBox="0 0 200 60">
                <defs>
                  <radialGradient id="holoBaseGlowG" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.45" />
                    <stop offset="60%" stop-color="#4338ca" stop-opacity="0.22" />
                    <stop offset="100%" stop-color="#4338ca" stop-opacity="0" />
                  </radialGradient>
                  <linearGradient id="holoEdgeG" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stop-color="#a5f3fc" stop-opacity="0.95" />
                    <stop offset="100%" stop-color="#0891b2" stop-opacity="0.18" />
                  </linearGradient>
                </defs>
                <ellipse class="base-aura" cx="100" cy="30" rx="70" ry="18" fill="url(#holoBaseGlowG)" />
                <polygon
                  class="base-hex"
                  points="50,30 76,12 124,12 150,30 124,48 76,48"
                  fill="rgba(8,145,178,0.08)"
                  stroke="url(#holoEdgeG)"
                  stroke-width="1.6"
                  stroke-linejoin="round"
                />
                <polygon
                  class="base-hex-inner"
                  points="62,30 82,17 118,17 138,30 118,43 82,43"
                  fill="none"
                  stroke="#67e8f9"
                  stroke-width="0.8"
                  stroke-dasharray="3 3"
                  opacity="0.7"
                />
              </svg>
            </div>
          </div>

          <div v-if="harvestReady && harvestableCount > 0" class="tree-fruit-hint">
            <span class="hint-icon">🔮</span> 树木已成熟 · 点击果实收取 {{ harvestableCount }} 颗知识果实
          </div>
          <div v-else-if="petData.nodes_to_mature > 0" class="tree-fruit-hint is-growing">
            <span class="hint-icon">🌱</span> 还需 {{ petData.nodes_to_mature }} 个知识点，知识树就会结出果实
          </div>

          <div class="tree-progress">
            <div class="progress-label">
              <span>成长进度</span>
              <span class="progress-value">{{ Math.round(petData.tree_growth) }}<i>%</i></span>
            </div>
            <div class="progress-track">
              <div class="progress-fill" :style="{ width: Math.round(petData.tree_growth) + '%' }">
                <span class="progress-tip"></span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="pet-card">
        <div class="card-shine"></div>
        <div class="card-head">
          <div class="section-title">
            <span class="title-dot"></span>{{ petData.name || '知识精灵' }}
          </div>
          <span class="pet-level-badge">Lv.{{ petData.level }}</span>
        </div>
        <div class="pet-species-row">
          <span class="pet-species-tag">{{ speciesLabel }}</span>
          <span class="pet-stage-tag" :class="`stage-${stageKey}`">{{ stageLabel }}</span>
          <span class="pet-mood-tag">{{ moodMeta.emoji }} {{ moodMeta.label }}</span>
          <span v-if="petData.personality" class="pet-personality-tag">「{{ petData.personality }}」</span>
        </div>
        <div v-if="evolvingStage" class="pet-evolve-banner">✨ 进化！{{ stageLabel }}</div>
        <div class="pet-info-row">
          <div ref="petAvatarRef" class="pet-avatar-wrap" :class="{ 'pet-eating': feedAnimating }">
            <transition name="care-pop">
              <div v-if="careGreeting" class="pet-care-bubble">
                {{ careGreeting }}
                <span class="care-tail"></span>
              </div>
            </transition>
            <PetAvatar
              :species="petData.species"
              :color="petData.color"
              :size="96"
              :level="petData.level"
              :mood="petData.mood"
              :leveled-up="leveledUpPulse || evolvingStage"
            />
            <div class="feed-fruit" v-show="feedAnimating">🍎</div>
          </div>

          <div class="pet-stats-col">
            <div class="pet-stats-grid">
              <div class="pet-stat-cell">
                <span class="stat-cell-top">
                  <span class="stat-cell-emoji">🍎</span>
                  <span class="stat-cell-value total-num">{{ petData.total_harvested }}</span>
                </span>
                <span class="stat-cell-label">累计收取</span>
              </div>
              <div class="pet-stat-cell">
                <span class="stat-cell-top">
                  <span class="stat-cell-emoji">🍏</span>
                  <span class="stat-cell-value balance-num">{{ petData.fruits }}</span>
                </span>
                <span class="stat-cell-label">果实余额</span>
              </div>
              <div class="pet-stat-cell">
                <span class="stat-cell-top">
                  <span class="stat-cell-emoji">🌰</span>
                  <span class="stat-cell-value tree-fruit-num">{{ petData.tree_fruits }}</span>
                </span>
                <span class="stat-cell-label">知识脉络</span>
              </div>
              <div class="pet-stat-cell">
                <span class="stat-cell-top">
                  <span class="stat-cell-emoji">🔥</span>
                  <span class="stat-cell-value streak-num">{{ petData.streak_days }}</span>
                </span>
                <span class="stat-cell-label">连续打卡</span>
              </div>
            </div>
            <div class="pet-bond-row">
              <span class="stat-label">亲密度</span>
              <span class="pet-bond-wrap">
                <span class="pet-bond-bar"><i :style="{ width: bondPercent + '%' }"></i></span>
                <span class="pet-bond-text">{{ petData.bond_level }} · {{ petData.bond }}</span>
              </span>
            </div>
            <div
              class="pet-achievement-entry"
              role="button"
              tabindex="0"
              @click="achievementVisible = true"
              @keyup.enter="achievementVisible = true"
            >
              <div class="ach-entry-main">
                <HoloTrophyIcon
                  :tier="currentTier || 1"
                  :unlocked="!!currentMedal"
                  :size="40"
                />
                <div class="ach-entry-text">
                  <span class="ach-entry-title">认知星图</span>
                  <span class="ach-entry-sub">当前 {{ currentMedal ? currentMedal.name : '未点亮' }} · 已点亮 {{ unlockedCount }}/{{ medalList.length }}</span>
                </div>
                <span class="ach-entry-cta">查看星图 ›</span>
              </div>
              <div class="ach-entry-progress">
                <div class="ach-entry-bar">
                  <span :style="{ width: achProgress + '%' }"></span>
                </div>
                <span v-if="nextMedalInfo" class="ach-entry-need">再收取 {{ nextMedalInfo.need }} 颗点亮「{{ nextMedalInfo.name }}」</span>
                <span v-else class="ach-entry-need all-unlocked">🎉 星图已全部点亮</span>
              </div>
            </div>
            <transition name="medal-pop">
              <div v-if="newMedalBanner" class="pet-medal-banner">
                ✨ 点亮全新星阶 · {{ newMedalBanner.name }}
              </div>
            </transition>
            <div class="pet-exp-bar">
              <div class="pet-exp-head">
                <span class="stat-label">成长经验</span>
                <span class="pet-exp-text">{{ petData.exp }}/{{ petData.exp_max }}</span>
              </div>
              <el-progress
                :percentage="Math.round((petData.exp / petData.exp_max) * 100)"
                :stroke-width="10"
                :color="'#06b6d4'"
                :show-text="false"
              />
            </div>
            <div class="pet-buttons">
              <el-button
                type="primary"
                round
                size="small"
                :disabled="!harvestReady || petLoading"
                @click="handleFruitClick"
              >
                收取果实
              </el-button>
              <el-button
                round
                size="small"
                :disabled="petData.fruits <= 0 || petLoading"
                @click="handleFeed"
              >
                投喂宠物
              </el-button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <div class="growth-guide">
      <div class="guide-step">
        <div class="step-icon">🌱</div>
        <div class="step-text">
          <strong>播种</strong>
          <span>记录笔记，埋下知识的种子</span>
        </div>
      </div>
      <div class="guide-arrow">→</div>
      <div class="guide-step">
        <div class="step-icon">💧</div>
        <div class="step-text">
          <strong>浇灌</strong>
          <span>用反思滋养，让根系更扎实</span>
        </div>
      </div>
      <div class="guide-arrow">→</div>
      <div class="guide-step">
        <div class="step-icon">🌳</div>
        <div class="step-text">
          <strong>生长</strong>
          <span>知识图谱自由生长，收获果实</span>
        </div>
      </div>
    </div>

    <el-dialog

      v-model="achievementVisible"
      class="achievement-dialog"
      width="820px"
      align-center
      :show-close="false"
    >
      <template #header>
        <div class="holo-core-head">
          <div class="holo-core-visual">
            <span class="holo-core-ring ring-a"></span>
            <span class="holo-core-ring ring-b"></span>
            <HoloTrophyIcon
              :tier="currentTier || 1"
              :unlocked="!!currentMedal"
              :current="!!currentMedal"
              :size="104"
            />
          </div>
          <div class="holo-core-meta">
            <h3>认知星图</h3>
            <p class="holo-core-sub">水晶奖杯殿堂 · 已点亮 {{ unlockedCount }}/{{ medalList.length }}</p>
            <div class="holo-core-now">
              <span class="holo-core-tier">{{ currentMedal ? currentMedal.name : '尚未点亮' }}</span>
              <span class="holo-core-count">累计 {{ petData.total_harvested }} 颗</span>
            </div>
            <div class="holo-core-bar"><span :style="{ width: achProgress + '%' }"></span></div>
            <span v-if="nextMedalInfo" class="holo-core-next">再收取 {{ nextMedalInfo.need }} 颗点亮「{{ nextMedalInfo.name }}」</span>
            <span v-else class="holo-core-next done">🎉 水晶奖杯殿堂已全部点亮</span>
          </div>
          <button class="ach-dialog-close" aria-label="关闭" @click="achievementVisible = false">✕</button>
        </div>
      </template>

      <div class="holo-grid">
        <div
          v-for="(m, i) in medalList"
          :key="m.id"
          class="holo-card"
          :class="{ unlocked: m.unlocked, current: m.id === petData.medal }"
          :style="{ '--tier-accent': tierAccent(i) }"
        >
          <span class="holo-card-idx">{{ String(i + 1).padStart(2, '0') }}</span>
          <HoloTrophyIcon
            :tier="i + 1"
            :unlocked="m.unlocked"
            :current="m.id === petData.medal"
            :size="58"
          />
          <span class="holo-card-name">{{ m.name }}</span>
          <span v-if="!m.unlocked" class="holo-card-need">
            还需 {{ Math.max(0, m.threshold - petData.total_harvested) }} 颗
          </span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped src="./Dashboard.css"></style>
<style src="./Dashboard.global.css"></style>