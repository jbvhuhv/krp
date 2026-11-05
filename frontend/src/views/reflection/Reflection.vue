<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import echarts from '@/utils/echarts'
import { ElMessage } from 'element-plus'
import { reflectionApi, notifyError } from '@/api'

const loading = ref(false)
const loadError = ref(false)
const generating = ref(false)
const questions = ref([])
const answers = reactive({})
const feedbacks = reactive({})
const submittingId = ref('')

const radarRefs = {}
const radarInstances = {}

const history = ref([])
const historyTotal = ref(0)
const historyLoading = ref(false)
const historyLoadError = ref(false)
const currentPage = ref(1)
const pageSize = ref(8)

const expandedItems = reactive({})
const voiceRecording = ref('')
const voiceSupported = ref(true)
const voiceInsecure = ref(false)
const voiceUsed = reactive({})
let recognition = null
let voiceTarget = ''
let voiceBaseline = ''

function setupRecognition() {
  if (!window.isSecureContext) {
    voiceSupported.value = false
    voiceInsecure.value = true
    return
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition
  voiceSupported.value = !!SR
  if (!SR) return
  recognition = new SR()
  recognition.lang = 'zh-CN'
  recognition.interimResults = true
  recognition.continuous = false
  recognition.onresult = (e) => {
    if (!voiceTarget) return
    let finalText = ''
    let interim = ''
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i]
      if (r.isFinal) finalText += r[0].transcript
      else interim += r[0].transcript
    }
    const text = (finalText || interim).trim()
    if (!text) return
    const prefix = voiceBaseline && voiceBaseline.trim() ? `${voiceBaseline.trimEnd()} ` : ''
    answers[voiceTarget] = prefix + text
    voiceUsed[voiceTarget] = true
  }
  recognition.onerror = (e) => {
    if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
      ElMessage.error('麦克风权限被拒绝，请在浏览器中允许访问后重试')
    } else if (e.error && e.error !== 'no-speech' && e.error !== 'aborted') {
      ElMessage.warning('语音识别出错，请重试')
    }
    voiceRecording.value = ''
    voiceTarget = ''
  }
  recognition.onend = () => {
    voiceRecording.value = ''
    voiceTarget = ''
  }
}

function startVoice(questionId) {
  voiceBaseline = answers[questionId] || ''
  voiceTarget = questionId
  try {
    recognition.start()
    voiceRecording.value = questionId
  } catch {
    voiceRecording.value = ''
    voiceTarget = ''
    ElMessage.warning('语音识别启动失败，请重试')
  }
}

function getMasteryColor(score) {
  const m = score || 0
  if (m < 60) return '#f85149'
  if (m <= 80) return '#d29922'
  return '#3fb950'
}

function masteryPercent(score) {
  return Math.round(score || 0)
}

async function loadTodayQuestions() {
  loading.value = true
  loadError.value = false
  try {
    questions.value = await reflectionApi.getTodayQuestions()
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

async function handleFetchQuestions() {
  generating.value = true
  try {
    questions.value = await reflectionApi.generateTodayQuestions()
    if (!questions.value.length) {
      ElMessage.info('暂无需要复习的知识点，请先上传笔记或前往知识图谱温习')
    } else {
      ElMessage.success(`已获取 ${questions.value.length} 个反思问题`)
    }
  } catch {
    notifyError('获取失败，请稍后重试')
  } finally {
    generating.value = false
  }
}

async function handleSubmit(questionId) {
  const answer = answers[questionId]
  if (!answer || !answer.trim()) {
    ElMessage.warning('请输入答案')
    return
  }
  submittingId.value = questionId
  try {
    const result = await reflectionApi.submitAnswer({
      question_id: questionId,
      answer: answer,
      is_voice: !!voiceUsed[questionId],
    })
    feedbacks[questionId] = result
    ElMessage.success('评估完成')
    await nextTick()
    initRadar(questionId, result)
  } catch {
  } finally {
    submittingId.value = ''
  }
}

function setRadarRef(el, questionId) {
  if (el) radarRefs[questionId] = el
}

function initRadar(questionId, feedback) {
  const container = radarRefs[questionId]
  if (!container) return
  if (radarInstances[questionId]) {
    radarInstances[questionId].dispose()
  }
  const chart = echarts.init(container)
  radarInstances[questionId] = chart
  chart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(17, 24, 39, 0.95)',
      borderColor: 'rgba(6, 182, 212, 0.4)',
      borderWidth: 1,
      textStyle: { color: '#e6edf3', fontSize: 12 },
      formatter: (params) => {
        const dims = ['概念准确性', '逻辑完整性', '举例合理性']
        const values = params.value || []
        const nums = dims.map((_, i) => Math.round(Number(values[i] || 0)))
        const avg = nums.length
          ? Math.round(nums.reduce((sum, v) => sum + v, 0) / nums.length)
          : 0
        const rows = dims.map((name, i) => `${name}：<b>${nums[i]}</b> 分`).join('<br/>')
        return `${rows}<br/>综合：<b>${avg}</b> 分`
      },
    },
    radar: {
      indicator: [
        { name: '概念准确性', max: 100 },
        { name: '逻辑完整性', max: 100 },
        { name: '举例合理性', max: 100 },
      ],
      shape: 'polygon',
      splitNumber: 5,
      radius: '60%',
      axisName: { color: '#8b949e', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(99, 102, 241, 0.15)' } },
      splitArea: { areaStyle: { color: ['rgba(255,255,255,0.01)', 'rgba(255,255,255,0.02)'] } },
      axisLine: { lineStyle: { color: 'rgba(99, 102, 241, 0.15)' } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: [
          Number(feedback.concept_accuracy || 0),
          Number(feedback.logic_completeness || 0),
          Number(feedback.example_reasonableness || 0),
        ],
        areaStyle: { color: 'rgba(6, 182, 212, 0.2)' },
        lineStyle: { color: '#06b6d4', width: 2, shadowBlur: 6, shadowColor: 'rgba(6, 182, 212, 0.5)' },
        itemStyle: { color: '#06b6d4', shadowBlur: 10, shadowColor: 'rgba(6, 182, 212, 0.6)' },
      }],
    }],
  })
}

function handleResize() {
  Object.values(radarInstances).forEach((chart) => chart?.resize())
}

function handleVoice(questionId) {
  if (voiceInsecure.value) {
    ElMessage.warning('麦克风仅在安全上下文可用，请通过 http://localhost:5173 访问（勿用局域网 IP）')
    return
  }
  if (!voiceSupported.value || !recognition) {
    ElMessage.warning('当前浏览器不支持语音输入，请使用 Chrome 或 Edge')
    return
  }
  const stopCurrent = voiceRecording.value === questionId
  if (voiceRecording.value) {
    try {
      recognition.stop()
    } catch {
      /* ignore */
    }
    voiceRecording.value = ''
    voiceTarget = ''
    if (stopCurrent) return
    setTimeout(() => startVoice(questionId), 250)
    return
  }
  startVoice(questionId)
}

async function loadHistory() {
  historyLoading.value = true
  historyLoadError.value = false
  try {
    const offset = (currentPage.value - 1) * pageSize.value
    const data = await reflectionApi.getHistory({ limit: pageSize.value, offset })
    history.value = data?.items ?? []
    historyTotal.value = data?.total ?? 0
  } catch {
    historyLoadError.value = true
  } finally {
    historyLoading.value = false
  }
}

function handlePageChange(page) {
  currentPage.value = page
  loadHistory()
}

function toggleExpand(id) {
  expandedItems[id] = !expandedItems[id]
}

// ===== 提醒设置 =====
const scheduleDialogVisible = ref(false)
const scheduleLoading = ref(false)
const scheduleSaving = ref(false)
const scheduleFrequency = ref('daily')
const scheduleStart = ref(new Date())
const scheduleEnd = ref(new Date())

const FREQUENCY_OPTIONS = [
  { value: 'daily', label: '每天' },
  { value: 'workdays', label: '工作日（周一至周五）' },
  { value: 'weekly', label: '每周' },
]

function parseTimeWindow(tw) {
  const [s, e] = (tw || '20:00-21:00').split('-')
  const [sh, sm] = (s || '20:00').split(':').map(Number)
  const [eh, em] = (e || '21:00').split(':').map(Number)
  const sd = new Date(); sd.setHours(sh, sm, 0, 0)
  const ed = new Date(); ed.setHours(eh, em, 0, 0)
  return [sd, ed]
}

function formatTimeWindow() {
  const fmt = (d) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  return `${fmt(scheduleStart.value)}-${fmt(scheduleEnd.value)}`
}

async function openScheduleDialog() {
  scheduleDialogVisible.value = true
  scheduleLoading.value = true
  try {
    const data = await reflectionApi.getSchedule()
    scheduleFrequency.value = data.frequency || 'daily'
    const [s, e] = parseTimeWindow(data.time_window)
    scheduleStart.value = s
    scheduleEnd.value = e
  } catch {
    const [s, e] = parseTimeWindow('20:00-21:00')
    scheduleFrequency.value = 'daily'
    scheduleStart.value = s
    scheduleEnd.value = e
  } finally {
    scheduleLoading.value = false
  }
}

async function saveSchedule() {
  scheduleSaving.value = true
  try {
    await reflectionApi.updateSchedule({
      frequency: scheduleFrequency.value,
      time_window: formatTimeWindow(),
    })
    ElMessage.success('提醒设置已保存')
    scheduleDialogVisible.value = false
  } catch {
    notifyError('保存失败，请稍后重试')
  } finally {
    scheduleSaving.value = false
  }
}


function formatDate(time) {
  if (!time) return ''
  let value = time
  if (
    typeof value === 'string' &&
    value.includes('T') &&
    !/(Z|[+-]\d{2}:?\d{2})$/.test(value)
  ) {
    value = `${value}Z`
  }
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

onMounted(() => {
  setupRecognition()
  loadTodayQuestions()
  loadHistory()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (recognition) {
    try {
      recognition.abort()
    } catch {
      /* ignore */
    }
  }
  Object.values(radarInstances).forEach((chart) => chart?.dispose())
})
</script>

<template>
  <div class="reflection-page" v-loading="loading">
    <!-- ===== 今日反思区域 ===== -->
    <section class="today-section">
      <div class="section-header">
        <div class="section-title-wrap">
          <span class="title-accent"></span>
          <h2 class="section-title">今日反思</h2>
        </div>
        <div class="header-actions">
          <el-button
            size="small"
            plain
            @click="openScheduleDialog"
            class="schedule-btn"
          >
            <el-icon><AlarmClock /></el-icon>
            提醒设置
          </el-button>
          <el-button
            size="small"
            plain
            :loading="loading"
            @click="loadTodayQuestions"
            class="refresh-btn"
          >
            <el-icon><Refresh /></el-icon>
            刷新问题
          </el-button>
        </div>
      </div>

      <div class="today-card">
        <template v-if="questions.length">
          <div
            v-for="(q, idx) in questions"
            :key="q.id"
            class="question-item"
            :class="{ 'is-answered': q.answered }"
          >
            <div class="question-head">
              <span class="q-badge">第 {{ idx + 1 }} 题</span>
              <el-tag v-if="q.node_name" size="small" effect="plain" class="q-tag">
                {{ q.node_name }}
              </el-tag>
              <el-tag v-if="q.answered" size="small" type="success" class="q-tag">
                已作答
              </el-tag>
            </div>
            <p class="question-text">{{ q.question }}</p>

            <el-input
              v-model="answers[q.id]"
              type="textarea"
              :rows="4"
              :disabled="q.answered"
              placeholder="在此输入你的理解和思考..."
              class="answer-input"
            />
            <div class="answer-actions">
              <el-button
                size="small"
                :type="voiceRecording === q.id ? 'danger' : 'default'"
                :disabled="q.answered"
                @click="handleVoice(q.id)"
              >
                <el-icon><Microphone /></el-icon>
                {{ voiceRecording === q.id ? '停止' : '语音' }}
              </el-button>
              <el-button
                size="small"
                type="primary"
                :loading="submittingId === q.id"
                :disabled="q.answered"
                @click="handleSubmit(q.id)"
              >
                提交答案
              </el-button>
            </div>

            <!-- AI 评估反馈 -->
            <div v-if="feedbacks[q.id]" class="ai-feedback-block">
              <div class="ai-feedback-head">
                <span class="ai-icon">🤖</span>
                <span class="ai-label">AI 评估反馈</span>
              </div>
              <div class="feedback-body">
                <div class="feedback-radar">
                  <div :ref="(el) => setRadarRef(el, q.id)" class="radar-container"></div>
                </div>
                <div class="feedback-scores">
                  <div class="score-item">
                    <span class="score-label">掌握度</span>
                    <el-progress
                      :percentage="Number(masteryPercent(feedbacks[q.id].mastery_score))"
                      :color="getMasteryColor(feedbacks[q.id].mastery_score)"
                      :stroke-width="10"
                    />
                  </div>
                  <div class="score-row">
                    <span class="score-label">概念准确性</span>
                    <span class="score-value">{{ masteryPercent(feedbacks[q.id].concept_accuracy) }}%</span>
                  </div>
                  <div class="score-row">
                    <span class="score-label">逻辑完整性</span>
                    <span class="score-value">{{ masteryPercent(feedbacks[q.id].logic_completeness) }}%</span>
                  </div>
                  <div class="score-row">
                    <span class="score-label">举例合理性</span>
                    <span class="score-value">{{ masteryPercent(feedbacks[q.id].example_reasonableness) }}%</span>
                  </div>
                </div>
                <div v-if="feedbacks[q.id].suggestion" class="feedback-suggestion">
                  {{ feedbacks[q.id].suggestion }}
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- 空状态 -->
        <div v-else class="empty-today">
          <template v-if="loadError">
            <el-empty :image-size="120" description="" />
            <p class="empty-text">今日问题加载失败，请稍后重试</p>
            <el-button type="primary" @click="loadTodayQuestions" class="generate-btn">
              重新加载
            </el-button>
          </template>
          <template v-else>
            <el-empty :image-size="120" description="" />
            <p class="empty-text">今日暂无反思，点击获取今日问题或前往知识图谱温习</p>
            <el-button
              type="primary"
              :loading="generating"
              @click="handleFetchQuestions"
              class="generate-btn"
            >
              <el-icon><MagicStick /></el-icon>
              获取今日问题
            </el-button>
          </template>
        </div>
      </div>
    </section>

    <!-- ===== 反思时间线 ===== -->
    <section class="timeline-section" v-loading="historyLoading">
      <div class="section-header">
        <div class="section-title-wrap">
          <span class="title-accent"></span>
          <h2 class="section-title">反思时间线</h2>
        </div>
        <span class="timeline-count">共 {{ historyTotal }} 条</span>
      </div>

      <div v-if="history.length" class="timeline-list">
        <div
          v-for="item in history"
          :key="item.id"
          class="history-card"
        >
          <!-- 卡片头部：时间 + 星级 -->
          <div class="history-card-head">
            <span class="history-time">{{ formatDate(item.answered_at) }}</span>
            <div v-if="item.mastery_score != null" class="history-rate">
              <span
                v-for="n in 5"
                :key="n"
                class="star"
                :class="{ filled: n <= Math.round((item.mastery_score || 0) / 20) }"
              >★</span>
              <span class="rate-score">{{ masteryPercent(item.mastery_score) }}分</span>
            </div>
          </div>

          <!-- 主标题 + 标签 -->
          <div class="history-card-title">
            <h3 class="history-question">{{ item.question }}</h3>
            <el-tag v-if="item.node_name" size="small" effect="plain" class="node-tag">
              {{ item.node_name }}
            </el-tag>
          </div>

          <!-- 用户回答（折叠） -->
          <div v-if="item.answer" class="history-answer-area">
            <div class="answer-label">我的回答</div>
            <p
              class="answer-text"
              :class="{ expanded: expandedItems[item.id] }"
            >{{ item.answer }}</p>
            <button
              v-if="item.answer.length > 100"
              class="expand-btn"
              @click="toggleExpand(item.id)"
            >
              {{ expandedItems[item.id] ? '收起' : '展开' }}
            </button>
          </div>

          <!-- AI 反馈独立块 -->
          <div v-if="item.feedback" class="ai-feedback-block history-feedback">
            <div class="ai-feedback-head">
              <span class="ai-icon">🤖</span>
              <span class="ai-label">AI 反馈</span>
            </div>
            <p class="ai-feedback-text">{{ item.feedback }}</p>
          </div>
        </div>
      </div>

      <el-empty
        v-else-if="historyLoadError"
        description="反思记录加载失败"
        :image-size="80"
        class="timeline-empty"
      >
        <el-button size="small" @click="loadHistory">重新加载</el-button>
      </el-empty>

      <el-empty v-else description="暂无反思记录" :image-size="80" class="timeline-empty" />

      <!-- 分页 -->
      <div v-if="historyTotal > pageSize" class="pagination-wrap">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="historyTotal"
          layout="prev, pager, next"
          background
          @current-change="handlePageChange"
        />
      </div>
    </section>

    <!-- ===== 提醒设置弹窗 ===== -->
    <el-dialog
      v-model="scheduleDialogVisible"
      title="反思提醒设置"
      width="440px"
      class="schedule-dialog"
      :close-on-click-modal="false"
    >
      <div v-loading="scheduleLoading" class="schedule-form">
        <div class="schedule-row">
          <label class="schedule-label">提醒频率</label>
          <el-select v-model="scheduleFrequency" class="schedule-select">
            <el-option
              v-for="opt in FREQUENCY_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <div class="schedule-row">
          <label class="schedule-label">提醒时段</label>
          <div class="time-window-pickers">
            <el-time-picker
              v-model="scheduleStart"
              format="HH:mm"
              :clearable="false"
              class="time-picker"
            />
            <span class="time-sep">至</span>
            <el-time-picker
              v-model="scheduleEnd"
              format="HH:mm"
              :clearable="false"
              class="time-picker"
            />
          </div>
        </div>
        <p class="schedule-hint">系统会在所选时段内，按频率自动为你生成反思问题。</p>
      </div>
      <template #footer>
        <el-button @click="scheduleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="scheduleSaving" @click="saveSchedule">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped src="./Reflection.css"></style>