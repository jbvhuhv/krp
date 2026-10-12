<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { petApi } from '@/api'
import { useUserStore } from '@/stores/user'
import PetAvatar from '@/components/PetAvatar.vue'

const userStore = useUserStore()

const pet = ref({ name: '', species: 'jelly', color: '#22d3ee', personality: '', mood: 'content' })

async function loadPet() {
  try {
    const data = await petApi.getStatus()
    pet.value = { ...pet.value, ...data }
    applySavedPreset(data.voice_preset)
  } catch {
    // 未登录或接口异常时使用默认形象
    applySavedPreset(null)
  }
}

function applySavedPreset(serverPreset) {
  const valid = (id) => VOICE_PRESETS.some((p) => p.id === id)
  let id = null
  if (serverPreset && valid(serverPreset)) {
    id = serverPreset
  } else {
    try {
      const saved = localStorage.getItem('pet-voice-preset')
      if (saved && valid(saved)) id = saved
    } catch {
      /* ignore */
    }
  }
  if (id) {
    activePresetId.value = id
    applyPresetVoice()
  }
}

let refreshTimer = null

onMounted(() => {
  loadPet()
  initVoice()
  loadRate()
  // 情绪随闲置时间衰减，定期刷新保持悬浮宠物形象与后端一致
  refreshTimer = window.setInterval(loadPet, 60000)
})


const isHovering = ref(false)
const dialogVisible = ref(false)
// 情绪由后端情感状态机驱动（pet.mood），不再随机
const petMood = computed(() => pet.value.mood || 'content')

const chatMessages = ref([])
const chatInput = ref('')
const chatLoading = ref(false)
const chatScrollRef = ref()

const voiceInputSupported = ref(false)
const voiceOutputSupported = ref(false)
const listening = ref(false)
const speakEnabled = ref(true)
const speaking = ref(false)
const activePresetId = ref('cute_girl')
// 语速倍率（叠加在音色预设的基准语速上），仅本地持久化
const userRate = ref(1)
const RATE_OPTIONS = [
  { label: '慢', value: 0.85 },
  { label: '标准', value: 1 },
  { label: '稍快', value: 1.15 },
  { label: '快', value: 1.3 },
]
let recognition = null

// 热门音色预设（未配置用户的默认推荐）。id 必须与后端 pet_service.VOICE_PRESETS 一致。
// engine='browser'：用浏览器 Web Speech API 合成，patterns 按优先级匹配系统音色，
// gender 为兜底倾向；引擎切到后端 TTS 时只需改 engine 并补 pitch/rate 之外的播放逻辑。
const VOICE_PRESETS = [
  {
    id: 'cute_girl',
    name: '可爱少女',
    emoji: '🎀',
    desc: '甜美元气 · 默认推荐',
    engine: 'browser',
    gender: 'female',
    pitch: 1.6,
    rate: 1.02,
    patterns: [/xiaoxiao.*natural/i, /xiaoyi.*natural/i, /xiaoxiao/i, /xiaoyi/i, /huihui/i],
  },
  {
    id: 'gentle_woman',
    name: '温柔女声',
    emoji: '🌸',
    desc: '轻柔舒缓 · 适合陪伴',
    engine: 'browser',
    gender: 'female',
    pitch: 1.25,
    rate: 0.98,
    patterns: [/xiaoyan.*natural/i, /xiaomo/i, /yaoyao/i, /huihui/i, /female|女/i],
  },
  {
    id: 'lively_kid',
    name: '活泼童声',
    emoji: '🐣',
    desc: '蹦蹦跳跳的童趣',
    engine: 'browser',
    gender: 'female',
    pitch: 1.85,
    rate: 1.08,
    patterns: [/child|kid|童/i, /xiaoxiao/i, /female|女|girl/i],
  },
  {
    id: 'magnetic_man',
    name: '磁性男声',
    emoji: '🎙️',
    desc: '低沉有磁性',
    engine: 'browser',
    gender: 'male',
    pitch: 0.75,
    rate: 0.98,
    patterns: [/yunxi.*natural/i, /yunyang.*natural/i, /yunxi/i, /kangkang/i, /male|男/i],
  },
  {
    id: 'calm_narrator',
    name: '沉稳旁白',
    emoji: '📖',
    desc: '从容沉稳的讲述感',
    engine: 'browser',
    gender: 'male',
    pitch: 0.9,
    rate: 0.92,
    patterns: [/yunyang.*natural/i, /yunye.*natural/i, /yunyang/i, /male|男/i],
  },
]

// 各情绪下的开场白（键与后端 pet_service.MOODS 一致）
const MOOD_GREETINGS = {
  happy: '喵～主人好！我是你的知识花园小精灵 🐱',
  excited: '哇！你来了！我今天超有干劲的 ✨',
  content: '呼～安安静静陪着你，也很好呀 🍃',
  curious: '你在学什么呀？让我看看你的知识图谱～',
  proud: '嘿嘿，我们最近进步好大，我超骄傲的！',
  lonely: '你终于来啦…我等你等了好久 🥺',
  tired: '呼噜噜…有点困了，但看到你就精神啦～',
}

const moodGreeting = computed(() => MOOD_GREETINGS[petMood.value] || MOOD_GREETINGS.content)


function handleMouseEnter() {
  isHovering.value = true
}

function handleMouseLeave() {
  isHovering.value = false
}

const PET_SIZE = 64
const STORAGE_KEY = 'pet-float-pos'

const floatRef = ref()
const pos = ref(null)
const dragging = ref(false)
let hasMoved = false
let startX = 0
let startY = 0
let startLeft = 0
let startTop = 0

const floatStyle = computed(() =>
  pos.value
    ? { left: `${pos.value.x}px`, top: `${pos.value.y}px`, right: 'auto', bottom: 'auto' }
    : {},
)

function clampPos(x, y) {
  const maxX = Math.max(0, window.innerWidth - PET_SIZE)
  const maxY = Math.max(0, window.innerHeight - PET_SIZE)
  return {
    x: Math.min(Math.max(0, x), maxX),
    y: Math.min(Math.max(0, y), maxY),
  }
}

function onPointerDown(e) {
  const el = floatRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  startX = e.clientX
  startY = e.clientY
  startLeft = rect.left
  startTop = rect.top
  hasMoved = false
  dragging.value = true
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  e.preventDefault()
}

function onPointerMove(e) {
  if (!dragging.value) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  if (Math.abs(dx) > 4 || Math.abs(dy) > 4) hasMoved = true
  pos.value = clampPos(startLeft + dx, startTop + dy)
}

function onPointerUp() {
  dragging.value = false
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  if (hasMoved) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(pos.value))
    } catch {
      /* ignore */
    }
  } else {
    handleClick()
  }
}

function onWindowResize() {
  if (pos.value) pos.value = clampPos(pos.value.x, pos.value.y)
}

onMounted(() => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    if (saved && typeof saved.x === 'number' && typeof saved.y === 'number') {
      pos.value = clampPos(saved.x, saved.y)
    }
  } catch {
    /* ignore */
  }
  window.addEventListener('resize', onWindowResize)
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  window.removeEventListener('resize', onWindowResize)
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  toggleVoice(false)
  stopSpeaking()
  if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = null
})

function onDialogClosed() {
  toggleVoice(false)
  stopSpeaking()
}

function handleClick() {
  dialogVisible.value = true
  if (chatMessages.value.length === 0) {
    chatMessages.value.push({ role: 'pet', content: moodGreeting.value })
    speak(moodGreeting.value)
  }
}

async function sendChatMessage() {
  const msg = chatInput.value.trim()
  if (!msg || chatLoading.value) return

  // 新一轮回答：打断上一轮仍在播放的语音
  stopSpeaking()
  chatMessages.value.push({ role: 'user', content: msg })
  chatInput.value = ''
  chatLoading.value = true

  const petMsg = { role: 'pet', content: '' }
  chatMessages.value.push(petMsg)

  let speakBuffer = ''
  try {
    const token = userStore.token
    const resp = await fetch('/api/v1/pet/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ message: msg }),
    })

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') break
          petMsg.content += data
          // 流式分句：凑齐完整句立即播报，首句更快出声、更接近实时对话
          speakBuffer += data
          const [ready, rest] = drainSentences(speakBuffer)
          speakBuffer = rest
          if (ready.length) ready.forEach((s) => enqueueSpeech(s))
        }
      }
    }
  } catch {
    petMsg.content = '喵...我走神了，再说一次好吗？'
    enqueueSpeech(petMsg.content)
  } finally {
    chatLoading.value = false
    await nextTick()
    if (chatScrollRef.value) chatScrollRef.value.scrollTop = chatScrollRef.value.scrollHeight
    // 收尾：补读最后不足一句的残余文本（回复过短、无句末标点时）
    const tail = speakBuffer.trim()
    if (tail) enqueueSpeech(tail)
  }
}

function cleanForSpeech(text) {
  return (text || '')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/[#*_>`~[\]()]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function currentPreset() {
  return VOICE_PRESETS.find((p) => p.id === activePresetId.value) || VOICE_PRESETS[0]
}

// === 句子级朗读引擎 ===
// 按句末标点切句，逐句合成并加入句间停顿；疑问句尾上扬、感叹句加强，
// 告别「一整段一口气念完」的机械感。长句再按逗号/顿号细分，避免单句过长
// （也顺带规避 Chrome 对超长 utterance 中途暂停的问题）。
function splitSentences(text) {
  const clean = cleanForSpeech(text)
  if (!clean) return []
  const raw = clean.match(/[^。！？!?…\n]+[。！？!?…\n]*/g) || [clean]
  const out = []
  for (const seg of raw) {
    const s = seg.trim()
    if (!s) continue
    if (s.length <= 36) {
      out.push(s)
      continue
    }
    const sub = s.match(/[^，,、；;]+[，,、；;]*/g) || [s]
    let acc = ''
    for (const piece of sub) {
      if (acc && (acc + piece).length > 36) {
        out.push(acc)
        acc = piece
      } else {
        acc += piece
      }
    }
    if (acc) out.push(acc)
  }
  return out
}

// 依据句末标点推断语气微调与句间停顿：疑问上扬、感叹加强、逗号略顿、句号收束
function sentenceTone(sentence) {
  const t = (sentence || '').trim()
  if (/[？?]\s*$/.test(t)) return { dPitch: 0.14, dRate: -0.02, gap: 260 }
  if (/[！!]\s*$/.test(t)) return { dPitch: 0.1, dRate: 0.03, gap: 300 }
  if (/[；;]\s*$/.test(t)) return { dPitch: 0.02, dRate: 0, gap: 200 }
  if (/[，,、]\s*$/.test(t)) return { dPitch: 0, dRate: 0, gap: 90 }
  return { dPitch: 0, dRate: 0, gap: 240 }
}

// 从流式缓冲里取出已完结的句子（含句末标点），剩余片段留待下一批
function drainSentences(buf) {
  const ready = []
  let rest = buf
  const re = /[^。！？!?…\n]*[。！？!?…\n]/
  let m
  while ((m = re.exec(rest))) {
    if (m[0].trim()) ready.push(m[0])
    rest = rest.slice(m[0].length)
  }
  return [ready, rest]
}

let ttsQueue = []
let ttsRunning = false
let ttsTimer = null

function enqueueSpeech(text) {
  if (!speakEnabled.value || !voiceOutputSupported.value) return
  const sentences = splitSentences(text)
  if (!sentences.length) return
  ttsQueue.push(...sentences)
  pumpSpeech()
}

function pumpSpeech() {
  if (ttsRunning) return
  if (ttsTimer) {
    clearTimeout(ttsTimer)
    ttsTimer = null
  }
  const sentence = ttsQueue.shift()
  if (!sentence) {
    speaking.value = false
    return
  }
  const preset = currentPreset()
  const tone = sentenceTone(sentence)
  const pitch = Math.min(2, Math.max(0, preset.pitch + tone.dPitch))
  const rate = Math.min(2, Math.max(0.5, preset.rate * userRate.value + tone.dRate))
  ttsRunning = true
  // 预留：preset.engine === 'backend' 时未来走后端 TTS 播放，当前一律用浏览器合成
  try {
    const utter = new SpeechSynthesisUtterance(sentence)
    utter.lang = 'zh-CN'
    if (cuteVoice) utter.voice = cuteVoice
    utter.rate = rate
    utter.pitch = pitch
    utter.volume = 1
    utter.onstart = () => { speaking.value = true }
    utter.onend = () => {
      ttsRunning = false
      if (ttsQueue.length) ttsTimer = setTimeout(pumpSpeech, tone.gap)
      else speaking.value = false
    }
    utter.onerror = () => {
      ttsRunning = false
      if (ttsQueue.length) ttsTimer = setTimeout(pumpSpeech, 60)
      else speaking.value = false
    }
    window.speechSynthesis.speak(utter)
  } catch {
    ttsRunning = false
    speaking.value = false
  }
}

// 朗读一段文本：先打断当前队列，再从整段文本入队（试听/开场白等场景）
function speak(text) {
  stopSpeaking()
  enqueueSpeech(text)
}

let cuteVoice = null

function findVoiceForPreset(preset) {
  const all = window.speechSynthesis.getVoices() || []
  const zh = all.filter((v) => /^zh|cmn/i.test(v.lang || ''))
  const pools = zh.length ? [zh, all] : [all]
  for (const pool of pools) {
    for (const re of preset.patterns) {
      const hit = pool.find((v) => re.test(v.name || ''))
      if (hit) return hit
    }
    if (preset.gender) {
      const re =
        preset.gender === 'male'
          ? /male|男|yunxi|yunyang|yunye|kangkang/i
          : /female|女|xiaoxiao|xiaoyi|huihui|yaoyao/i
      const hit = pool.find((v) => re.test(v.name || ''))
      if (hit) return hit
    }
  }
  return null
}

function applyPresetVoice() {
  if (!voiceOutputSupported.value) return
  cuteVoice = findVoiceForPreset(currentPreset())
}

async function onPresetChange(id) {
  activePresetId.value = id
  applyPresetVoice()
  try {
    localStorage.setItem('pet-voice-preset', id)
  } catch {
    /* ignore */
  }
  if (userStore.token) {
    try {
      await petApi.setVoice(id)
    } catch {
      /* ignore */
    }
  }
  speak('你好呀，我是你的知识小精灵～')
}

// 语速档位：本地持久化并即时试听
function loadRate() {
  try {
    const v = parseFloat(localStorage.getItem('pet-voice-rate'))
    if (RATE_OPTIONS.some((o) => o.value === v)) userRate.value = v
  } catch {
    /* ignore */
  }
}

function onRateChange(v) {
  try {
    localStorage.setItem('pet-voice-rate', String(v))
  } catch {
    /* ignore */
  }
  speak('这是我的语速，你觉得合适吗？')
}

function stopSpeaking() {
  if (ttsTimer) {
    clearTimeout(ttsTimer)
    ttsTimer = null
  }
  ttsQueue = []
  ttsRunning = false
  try {
    window.speechSynthesis.cancel()
  } catch {
    /* ignore */
  }
  speaking.value = false
}

function onSpeakToggle(val) {
  if (!val) stopSpeaking()
}

function initVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition
  voiceInputSupported.value = !!SR
  voiceOutputSupported.value = typeof window.speechSynthesis !== 'undefined'
  if (voiceOutputSupported.value) {
    applyPresetVoice()
    window.speechSynthesis.onvoiceschanged = applyPresetVoice
  }
  if (SR) {
    recognition = new SR()
    recognition.lang = 'zh-CN'
    recognition.interimResults = true
    recognition.continuous = false
    recognition.onresult = (e) => {
      let finalText = ''
      let interim = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i]
        if (r.isFinal) finalText += r[0].transcript
        else interim += r[0].transcript
      }
      chatInput.value = finalText || interim
      if (finalText.trim()) {
        toggleVoice(false)
        sendChatMessage()
      }
    }
    recognition.onerror = () => { listening.value = false }
    recognition.onend = () => { listening.value = false }
  }
}

function toggleVoice(force) {
  if (!voiceInputSupported.value || !recognition) return
  const next = typeof force === 'boolean' ? force : !listening.value
  if (next) {
    stopSpeaking()
    try {
      recognition.start()
      listening.value = true
    } catch {
      listening.value = false
    }
  } else {
    try {
      recognition.stop()
    } catch {
      /* ignore */
    }
    listening.value = false
  }
}

</script>

<template>
  <div
    ref="floatRef"
    class="pet-float"
    :class="{ 'pet-active': isHovering, 'pet-dragging': dragging }"
    :style="floatStyle"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
    @pointerdown="onPointerDown"
  >
    <div class="pet-bubble" v-show="isHovering">
      <span>{{ pet.name || '主人' }}，我在这里！</span>
      <div class="bubble-tail"></div>
    </div>

    <div class="pet-svg" :class="{ 'pet-bounce': isHovering }">
      <PetAvatar :species="pet.species" :color="pet.color" :size="56" :level="pet.level || 1" :mood="petMood" />
    </div>
  </div>

  <el-dialog
    v-model="dialogVisible"
    width="400px"
    class="pet-dialog"
    :show-close="true"
    align-center
    @closed="onDialogClosed"
  >
    <template #header>
      <div class="pet-dialog-head">
        <span class="pet-head-dot"></span>
        <span class="pet-head-title">🐱 {{ pet.name || '知识花园小精灵' }}</span>
        <span v-if="pet.level" class="pet-head-level">Lv.{{ pet.level }}</span>
      </div>
    </template>
    <div class="pet-dialog-content">
      <div class="pet-avatar">
        <div class="pet-avatar-ring"></div>
        <PetAvatar :species="pet.species" :color="pet.color" :size="60" :level="pet.level || 1" :mood="petMood" />
      </div>
      <div class="chat-messages" ref="chatScrollRef">
        <div
          v-for="(msg, i) in chatMessages"
          :key="i"
          class="chat-msg"
          :class="msg.role === 'user' ? 'chat-msg-user' : 'chat-msg-pet'"
        >
          {{ msg.content || '...' }}
        </div>
      </div>
      <div v-if="listening" class="voice-listening">
        <span class="voice-dot"></span> 正在聆听，请说话…
      </div>
      <div class="chat-input-row">
        <el-button
          v-if="voiceInputSupported"
          class="mic-btn"
          :class="{ 'mic-active': listening }"
          size="small"
          circle
          @click="toggleVoice()"
        >
          {{ listening ? '■' : '🎤' }}
        </el-button>
        <el-input
          v-model="chatInput"
          placeholder="和宠物说句话..."
          @keyup.enter="sendChatMessage"
          :disabled="chatLoading"
          size="small"
        />
        <el-button type="primary" size="small" @click="sendChatMessage" :loading="chatLoading" round>
          发送
        </el-button>
      </div>
      <div v-if="voiceOutputSupported" class="voice-toolbar">
        <div class="voice-field">
          <span class="voice-toolbar-label">🎙️ 音色</span>
          <el-select
            v-model="activePresetId"
            size="small"
            class="voice-select"
            popper-class="voice-select-popper"
            placeholder="选择音色"
            @change="onPresetChange"
          >
            <el-option
              v-for="p in VOICE_PRESETS"
              :key="p.id"
              :label="`${p.emoji} ${p.name}`"
              :value="p.id"
            >
              <span class="preset-opt">
                <span>{{ p.emoji }} {{ p.name }}</span>
                <span class="preset-opt-desc">{{ p.desc }}</span>
              </span>
            </el-option>
          </el-select>
        </div>
        <div class="voice-field">
          <span class="voice-toolbar-label">⏩ 语速</span>
          <el-select
            v-model="userRate"
            size="small"
            class="voice-select voice-rate-select"
            popper-class="voice-select-popper"
            @change="onRateChange"
          >
            <el-option v-for="r in RATE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </div>
        <div class="voice-field voice-field-speak">
          <span class="voice-speak-toggle">
            <span class="voice-toolbar-label">🗣 播报</span>
            <el-switch v-model="speakEnabled" size="small" @change="onSpeakToggle" />
          </span>
          <el-button
            v-if="speaking"
            link
            size="small"
            type="primary"
            @click="stopSpeaking"
          >停止播报</el-button>
        </div>
      </div>
      <div v-if="voiceOutputSupported" class="voice-hint">
        <span class="voice-hint-icon">🔊</span>
        <span>音色由系统语音合成，实际效果因设备而异，建议使用 Edge 浏览器体验自然音</span>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.pet-float {
  position: fixed;
  right: 40px;
  bottom: 100px;
  z-index: 1000;
  width: 64px;
  height: 64px;
  cursor: pointer;
  pointer-events: none;
}

.pet-svg {
  width: 100%;
  height: 100%;
  pointer-events: auto;
  filter: drop-shadow(0 0 10px rgba(6, 182, 212, 0.45));
  transition: filter 0.3s ease;
  animation: petIdle 3.6s ease-in-out infinite;
}

.pet-bounce {
  animation: petBounce 0.6s ease-in-out infinite alternate;
}

@keyframes petIdle {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5px); }
}

@keyframes petBounce {
  from { transform: translateY(-3px) scale(1); }
  to { transform: translateY(-9px) scale(1.08); }
}

.pet-bubble {
  position: absolute;
  bottom: 72px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(22, 27, 34, 0.9);
  border: 1px solid rgba(6, 182, 212, 0.3);
  border-radius: 12px;
  padding: 6px 14px;
  white-space: nowrap;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 0 16px rgba(6, 182, 212, 0.2);
  pointer-events: none;
}

.pet-bubble span {
  font-size: 13px;
  color: #06b6d4;
  font-weight: 500;
  letter-spacing: 0.5px;
}

.bubble-tail {
  position: absolute;
  bottom: -6px;
  left: 50%;
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-top: 6px solid rgba(6, 182, 212, 0.3);
}

.pet-active .pet-svg {
  filter: drop-shadow(0 0 16px rgba(6, 182, 212, 0.7));
}

.pet-float.pet-dragging {
  cursor: grabbing;
  user-select: none;
}

.pet-dragging .pet-svg {
  animation: none;
  transform: scale(1.06);
  filter: drop-shadow(0 0 18px rgba(6, 182, 212, 0.75));
}
</style>

<style>
/* ===== 宠物对话弹窗（teleport 至 body，需全局样式覆盖 Element Plus）===== */
.pet-dialog .el-dialog {
  background: linear-gradient(180deg, rgba(13, 17, 30, 0.92), rgba(7, 10, 20, 0.96));
  border: 1px solid rgba(103, 232, 249, 0.18);
  border-radius: 20px;
  box-shadow:
    0 0 0 1px rgba(99, 102, 241, 0.08),
    0 24px 60px rgba(0, 0, 0, 0.5),
    0 0 42px rgba(34, 211, 238, 0.12);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  max-width: calc(100vw - 32px);
  height: min(620px, 82vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.pet-dialog .el-dialog::before {
  content: '';
  position: absolute;
  top: 0;
  left: 12%;
  right: 12%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(165, 243, 252, 0.75), rgba(165, 180, 252, 0.75), transparent);
  pointer-events: none;
}

.pet-dialog .el-dialog__header {
  flex: none;
  padding: 16px 18px 10px;
  margin: 0;
  border-bottom: 1px dashed rgba(148, 163, 184, 0.14);
}

.pet-dialog-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pet-head-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.9);
  animation: petHeadDot 2.6s ease-in-out infinite;
}

.pet-head-title {
  font-size: 15px;
  font-weight: 600;
  color: #e6edf3;
  letter-spacing: 0.01em;
}

.pet-head-level {
  margin-left: auto;
  font-size: 11px;
  color: #67e8f9;
  border: 1px solid rgba(103, 232, 249, 0.3);
  border-radius: 999px;
  padding: 1px 9px;
  background: rgba(34, 211, 238, 0.08);
  text-shadow: 0 0 8px rgba(103, 232, 249, 0.5);
}

.pet-dialog .el-dialog__headerbtn {
  top: 12px;
  right: 12px;
}

.pet-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b95c9;
  transition: color 0.2s ease, transform 0.25s ease;
}

.pet-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: #67e8f9;
  transform: rotate(90deg);
}

.pet-dialog .el-dialog__body {
  flex: 1;
  min-height: 0;
  display: flex;
  padding: 14px 18px 16px;
}

.pet-dialog-content {
  text-align: center;
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 0;
}

/* 宠物形象：发光圆环底座 */
.pet-avatar {
  position: relative;
  flex: none;
  display: flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 10px;
  padding: 4px 0 4px;
  filter: drop-shadow(0 0 12px rgba(6, 182, 212, 0.45));
}

.pet-avatar-ring {
  position: absolute;
  width: 86px;
  height: 86px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(34, 211, 238, 0.3) 0%, rgba(99, 102, 241, 0.14) 48%, transparent 72%);
  animation: petRingBreath 3.4s ease-in-out infinite;
}

.pet-avatar-ring::after {
  content: '';
  position: absolute;
  inset: -7px;
  border-radius: 50%;
  border: 1px dashed rgba(125, 211, 252, 0.45);
  animation: petRingSpin 20s linear infinite;
}

.pet-avatar > .pet-avatar {
  position: relative;
  z-index: 1;
  display: block;
}

/* 聊天区 */
.pet-dialog .chat-messages {
  position: relative;
  flex: 1;
  min-height: 130px;
  overflow-y: auto;
  padding: 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  text-align: left;
  border-radius: 14px;
  background:
    radial-gradient(120% 100% at 0% 0%, rgba(34, 211, 238, 0.06), transparent 52%),
    radial-gradient(120% 100% at 100% 100%, rgba(99, 102, 241, 0.06), transparent 52%),
    rgba(2, 4, 10, 0.55);
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.pet-dialog .chat-messages::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 14px;
  background-image:
    linear-gradient(rgba(148, 163, 184, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.05) 1px, transparent 1px);
  background-size: 26px 26px;
  -webkit-mask-image: radial-gradient(120% 90% at 50% 20%, #000 30%, transparent 100%);
  mask-image: radial-gradient(120% 90% at 50% 20%, #000 30%, transparent 100%);
  pointer-events: none;
}

.pet-dialog .chat-messages::-webkit-scrollbar {
  width: 4px;
}

.pet-dialog .chat-messages::-webkit-scrollbar-thumb {
  background: rgba(34, 211, 238, 0.3);
  border-radius: 999px;
}

.pet-dialog .chat-messages::-webkit-scrollbar-track {
  background: transparent;
}

.pet-dialog .chat-msg {
  position: relative;
  font-size: 13.5px;
  line-height: 1.65;
  padding: 8px 12px;
  border-radius: 12px;
  max-width: 85%;
  word-break: break-word;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
  animation: chatMsgIn 0.28s cubic-bezier(0.22, 1, 0.36, 1);
}

.pet-dialog .chat-msg-pet:hover {
  border-color: rgba(34, 211, 238, 0.4);
  box-shadow: 0 6px 20px rgba(34, 211, 238, 0.16);
  transform: translateY(-1px);
}

.pet-dialog .chat-msg-user:hover {
  border-color: rgba(129, 140, 248, 0.44);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.18);
  transform: translateY(-1px);
}

.pet-dialog .chat-msg-pet {
  align-self: flex-start;
  background: linear-gradient(135deg, rgba(34, 211, 238, 0.14), rgba(34, 211, 238, 0.05));
  border: 1px solid rgba(34, 211, 238, 0.2);
  color: #cffafe;
  border-top-left-radius: 4px;
  box-shadow: 0 4px 16px rgba(34, 211, 238, 0.08);
}

.pet-dialog .chat-msg-pet::before {
  content: '';
  position: absolute;
  left: -1px;
  top: 18px;
  width: 3px;
  height: 16px;
  border-radius: 99px;
  background: linear-gradient(180deg, #22d3ee, #818cf8);
  box-shadow: 0 0 8px rgba(34, 211, 238, 0.85);
}

.pet-dialog .chat-msg-user {
  align-self: flex-end;
  background: linear-gradient(135deg, rgba(129, 140, 248, 0.2), rgba(139, 92, 246, 0.08));
  border: 1px solid rgba(129, 140, 248, 0.22);
  color: #e0e7ff;
  border-top-right-radius: 4px;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.08);
}

.pet-dialog .chat-msg-user::after {
  content: '';
  position: absolute;
  right: -1px;
  top: 18px;
  width: 3px;
  height: 16px;
  border-radius: 99px;
  background: linear-gradient(180deg, #a78bfa, #818cf8);
  box-shadow: 0 0 8px rgba(129, 140, 248, 0.85);
}

/* 输入区 */
.pet-dialog .chat-input-row {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.pet-dialog .chat-input-row .el-input {
  flex: 1;
}

.pet-dialog .chat-input-row .el-input__wrapper {
  background: rgba(148, 163, 184, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 11px;
  box-shadow: none !important;
  padding-left: 12px;
  padding-right: 12px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.pet-dialog .chat-input-row .el-input__wrapper.is-focus {
  background: rgba(34, 211, 238, 0.05);
  border-color: rgba(34, 211, 238, 0.55);
  box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.14) !important;
}

.pet-dialog .chat-input-row .el-input__inner {
  color: #e2e8f0;
  font-size: 13px;
}

.pet-dialog .chat-input-row .el-input__inner::placeholder {
  color: #64748b;
}

.pet-dialog .mic-btn {
  --mic-cyan: #22d3ee;
  position: relative;
  flex: none;
  background: radial-gradient(circle at 34% 30%, rgba(34, 211, 238, 0.22), rgba(34, 211, 238, 0.06) 70%);
  border: 1px solid rgba(34, 211, 238, 0.3);
  color: #67e8f9;
  box-shadow: 0 0 10px rgba(34, 211, 238, 0.2), inset 0 0 8px rgba(34, 211, 238, 0.12);
  text-shadow: 0 0 8px rgba(103, 232, 249, 0.8);
  transition: background 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, transform 0.2s ease, color 0.2s ease;
}

.pet-dialog .mic-btn:hover {
  background: radial-gradient(circle at 34% 30%, rgba(34, 211, 238, 0.32), rgba(99, 102, 241, 0.08) 70%);
  border-color: rgba(34, 211, 238, 0.55);
  color: #a5f3fc;
  box-shadow: 0 0 16px rgba(34, 211, 238, 0.45), 0 0 28px rgba(34, 211, 238, 0.2), inset 0 0 10px rgba(34, 211, 238, 0.18);
  transform: translateY(-1px);
}

.pet-dialog .mic-btn.mic-active {
  background: radial-gradient(circle at 34% 30%, rgba(248, 113, 113, 0.95), rgba(239, 68, 68, 0.8) 72%);
  border-color: rgba(248, 113, 113, 0.8);
  color: #fff;
  text-shadow: 0 0 10px rgba(255, 255, 255, 0.9);
  animation: micPulse 1.2s ease-in-out infinite;
}

.pet-dialog .mic-btn.mic-active::before,
.pet-dialog .mic-btn.mic-active::after {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: 50%;
  border: 1.5px solid rgba(248, 113, 113, 0.55);
  animation: micRipple 1.6s cubic-bezier(0.25, 0.46, 0.45, 0.94) infinite;
}

.pet-dialog .mic-btn.mic-active::after {
  animation-delay: 0.8s;
}

.pet-dialog .mic-btn > span {
  position: relative;
  z-index: 1;
  display: inline-flex;
}

/* 发送按钮：青紫渐变 + 发光 + 扫光 */
.pet-dialog .chat-input-row .el-button--primary {
  border: none;
  background: linear-gradient(135deg, #0891b2, #6366f1 90%);
  box-shadow: 0 6px 18px rgba(34, 211, 238, 0.35);
  color: #fff;
  font-weight: 600;
  letter-spacing: 0.05em;
  overflow: hidden;
  position: relative;
  transition: transform 0.2s ease, box-shadow 0.25s ease;
}

.pet-dialog .chat-input-row .el-button--primary::after {
  content: '';
  position: absolute;
  top: 0;
  left: -60%;
  width: 45%;
  height: 100%;
  background: linear-gradient(105deg, transparent, rgba(255, 255, 255, 0.4), transparent);
  transform: skewX(-20deg);
  transition: left 0.55s ease;
}

.pet-dialog .chat-input-row .el-button--primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(34, 211, 238, 0.5);
}

.pet-dialog .chat-input-row .el-button--primary:hover::after {
  left: 130%;
}

.pet-dialog .chat-input-row .el-button--primary.is-loading {
  background: linear-gradient(135deg, #0e7490, #4f46e5);
}

/* 聆听提示 */
.voice-listening {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #67e8f9;
  margin-top: 10px;
  letter-spacing: 0.03em;
}

.voice-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.8);
  animation: micPulse 1.2s ease-in-out infinite;
}

/* 语音工具栏：网格分组，窄屏自动收拢，避免换行错乱 */
.voice-toolbar {
  flex: none;
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  align-items: center;
  gap: 10px 12px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed rgba(148, 163, 184, 0.14);
}

.voice-field {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.voice-field-speak {
  grid-column: 1 / -1;
  justify-content: space-between;
}

.voice-speak-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.voice-select {
  flex: 1;
  width: 100%;
  min-width: 0;
}

.voice-select .el-select__wrapper {
  background: rgba(148, 163, 184, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 10px;
  box-shadow: none !important;
  min-height: 28px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.voice-select .el-select__wrapper.is-focused {
  border-color: rgba(34, 211, 238, 0.55);
  box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.14) !important;
}

.voice-select .el-select__placeholder {
  color: #8b95c9;
  font-size: 12px;
}

.voice-select .el-select__selected-item {
  font-size: 12.5px;
  color: #e2e8f0;
}

.voice-toolbar-label {
  font-size: 12px;
  color: #94a3b8;
  white-space: nowrap;
}

.voice-toolbar .el-switch {
  --el-switch-on-color: #06b6d4;
  --el-switch-off-color: rgba(148, 163, 184, 0.3);
}

.voice-toolbar .el-button--primary.is-link {
  color: #67e8f9;
  font-size: 12px;
  text-decoration: none;
  transition: color 0.2s ease;
}

.voice-toolbar .el-button--primary.is-link:hover {
  color: #a5f3fc;
}

/* 音色下拉面板（teleport 至 body） */
.voice-select-popper {
  background: rgba(10, 14, 24, 0.94);
  border: 1px solid rgba(99, 102, 241, 0.28);
  border-radius: 12px;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 14px 36px rgba(0, 0, 0, 0.45), 0 0 24px rgba(34, 211, 238, 0.1);
  padding: 4px;
}

.voice-select-popper .el-select-dropdown__item {
  border-radius: 8px;
  color: #cbd5e1;
  font-size: 12.5px;
  transition: background 0.15s ease, color 0.15s ease;
}

.voice-select-popper .el-select-dropdown__item.is-hovering {
  background: rgba(34, 211, 238, 0.12);
  color: #a5f3fc;
}

.voice-select-popper .el-select-dropdown__item.is-selected {
  background: rgba(34, 211, 238, 0.16);
  color: #67e8f9;
  font-weight: 600;
}

.voice-select-popper .el-popper__arrow {
  display: none;
}

/* 音色选项 */
.preset-opt {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
}

.preset-opt-desc {
  font-size: 11px;
  color: #64748b;
  white-space: nowrap;
}

/* 语音提示 */
.voice-hint {
  flex: none;
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 5px;
  margin-top: 8px;
  font-size: 11px;
  line-height: 1.5;
  color: #5b6474;
  text-align: left;
}

.voice-hint-icon {
  font-size: 11px;
  filter: drop-shadow(0 0 4px rgba(103, 232, 249, 0.4));
}

/* 窄屏：语音设置收为单列，弹窗高度自适应 */
@media (max-width: 420px) {
  .voice-toolbar {
    grid-template-columns: minmax(0, 1fr);
  }

  .pet-dialog .el-dialog {
    height: min(600px, 88vh);
  }
}

/* 动画 */
@keyframes petHeadDot {
  0%, 100% { opacity: 0.5; box-shadow: 0 0 4px rgba(52, 211, 153, 0.6); }
  50% { opacity: 1; box-shadow: 0 0 10px rgba(52, 211, 153, 1); }
}

@keyframes petRingBreath {
  0%, 100% { opacity: 0.72; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.04); }
}

@keyframes petRingSpin {
  to { transform: rotate(360deg); }
}

@keyframes chatMsgIn {
  from { opacity: 0; transform: translateY(5px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes micPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.55); }
  50% { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
}

@keyframes micRipple {
  0% { transform: scale(1); opacity: 0.75; }
  100% { transform: scale(1.9); opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .pet-head-dot,
  .pet-avatar-ring,
  .pet-avatar-ring::after,
  .pet-dialog .chat-msg,
  .pet-dialog .mic-btn.mic-active,
  .pet-dialog .mic-btn.mic-active::before,
  .pet-dialog .mic-btn.mic-active::after,
  .voice-dot,
  .pet-dialog .chat-input-row .el-button--primary::after {
    animation: none;
  }

  .pet-dialog .chat-input-row .el-button--primary::after {
    display: none;
  }
}
</style>