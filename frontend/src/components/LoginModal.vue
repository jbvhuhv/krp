<script setup>
import { ref, reactive, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { resetAuthError } from '@/api/request'

const userStore = useUserStore()

const loading = ref(false)
const sendingCode = ref(false)
const countdown = ref(0)
let timer = null

const isDebug = import.meta.env.DEV
// 开发态预填账号由本地 env 注入（frontend/.env.development.local），
// 生产构建 DEV=false 时不生效，且源码中不再硬编码真实手机号/验证码。
const DEBUG_PHONE = isDebug ? import.meta.env.VITE_DEBUG_PHONE || '' : ''
const DEBUG_CODE = isDebug ? import.meta.env.VITE_DEBUG_CODE || '' : ''
// 演示环境（如 Render 免费档一键部署）会在构建期把 VITE_DEMO_MODE 置为 true，
// 登录框额外显示一个可直接使用的演示账号，方便体验者立刻看到完整数据。
const demoMode = import.meta.env.VITE_DEMO_MODE === 'true'
const DEMO_PHONE = import.meta.env.VITE_DEMO_PHONE || '13900000001'
const DEMO_CODE = import.meta.env.VITE_DEMO_CODE || '123456'

const loginForm = reactive({
  phone: isDebug ? DEBUG_PHONE : '',
  code: isDebug ? DEBUG_CODE : '',
})

const loginRules = {
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' },
  ],
  code: [
    { required: true, message: '请输入验证码', trigger: 'blur' },
    { len: 6, message: '验证码为6位数字', trigger: 'blur' },
  ],
}

const loginFormRef = ref()

watch(() => userStore.isLoginModalVisible, (visible) => {
  if (!visible) {
    loginForm.phone = isDebug ? DEBUG_PHONE : ''
    loginForm.code = isDebug ? DEBUG_CODE : ''
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    countdown.value = 0
  }
})

async function handleSendCode() {
  try {
    await loginFormRef.value.validateField('phone')
  } catch {
    return
  }
  sendingCode.value = true
  try {
    await userStore.sendCode(loginForm.phone)
    ElMessage.success('验证码已发送')
    startCountdown()
  } catch {
    // 错误已在拦截器中提示
  } finally {
    sendingCode.value = false
  }
}

function startCountdown() {
  countdown.value = 60
  timer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) {
      clearInterval(timer)
      timer = null
    }
  }, 1000)
}

async function handleLogin() {
  try {
    await loginFormRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await userStore.login(loginForm)
    await userStore.fetchMe()
    resetAuthError()
    userStore.closeLoginModal()
    ElMessage.success('登录成功')
    userStore.requestRefresh()
  } catch {
    // 错误已在拦截器中提示
  } finally {
    loading.value = false
  }
}


onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <el-dialog
    v-model="userStore.isLoginModalVisible"
    width="440px"
    append-to-body
    :show-close="true"
    class="login-modal"
    align-center
  >
    <template #header>
      <div class="modal-header">
        <div class="brand-glow"></div>
        <div class="brand-icon">
          <el-icon size="24"><School /></el-icon>
        </div>
        <h2>知识反思平台</h2>
        <p>面向终身学习者的知识引擎</p>
      </div>
    </template>

    <div class="form-body">
      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        label-position="top"
        class="login-form"
      >
        <el-form-item label="手机号" prop="phone" class="form-item">
          <el-input
            v-model="loginForm.phone"
            placeholder="请输入手机号"
            maxlength="11"
            class="dark-input"
            size="large"
          >
            <template #prepend>
              <span class="prefix-label">+86</span>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item label="验证码" prop="code" class="form-item">
          <div class="code-row">
            <el-input
              v-model="loginForm.code"
              placeholder="6 位验证码"
              maxlength="6"
              class="dark-input"
              size="large"
              @keyup.enter="handleLogin"
            />
            <button
              type="button"
              class="code-btn"
              :disabled="countdown > 0 || sendingCode"
              @click="handleSendCode"
            >
              <span v-if="sendingCode" class="btn-spinner"></span>
              {{ countdown > 0 ? `${countdown}s` : '获取验证码' }}
            </button>
          </div>
        </el-form-item>

        <button
          type="button"
          class="submit-btn"
          :disabled="loading"
          @click="handleLogin"
        >
          <span v-if="loading" class="btn-spinner"></span>
          <span v-else>登录 / 一键注册</span>
        </button>
      </el-form>

      <div class="tip-bar">
        <el-icon size="14"><InfoFilled /></el-icon>
        <span>未注册的手机号验证成功后将自动创建账号</span>
      </div>

      <div v-if="demoMode" class="tip-bar demo-tip">
        <el-icon size="14"><InfoFilled /></el-icon>
        <span>
          演示环境：手机号 <b>{{ DEMO_PHONE }}</b> / 验证码 <b>{{ DEMO_CODE }}</b>，登录即可查看完整示例数据
        </span>
      </div>

    </div>
  </el-dialog>
</template>

<style scoped>
/* ===== Header ===== */
.modal-header {
  text-align: center;
  padding: 4px 0 20px;
  position: relative;
  overflow: hidden;
}

.brand-glow {
  position: absolute;
  top: -40px;
  left: 50%;
  transform: translateX(-50%);
  width: 120px;
  height: 80px;
  background: radial-gradient(ellipse, rgba(6, 182, 212, 0.15) 0%, transparent 70%);
  pointer-events: none;
}

.brand-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.12) 0%, rgba(0, 120, 212, 0.06) 100%);
  border: 1px solid rgba(6, 182, 212, 0.2);
  color: #06b6d4;
  box-shadow: 0 0 20px rgba(6, 182, 212, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.05);
  margin-bottom: 14px;
}

.modal-header h2 {
  margin: 0 0 6px;
  color: #e6edf3;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.modal-header p {
  margin: 0;
  color: #6e7681;
  font-size: 13px;
  letter-spacing: 0.3px;
}

/* ===== Form Body ===== */
.form-body {
  padding: 4px 28px 28px;
}

.login-form {
  margin-top: 4px;
}

.form-item {
  margin-bottom: 20px;
}

/* ===== Code Row ===== */
.code-row {
  display: flex;
  gap: 10px;
  width: 100%;
}

.code-row :deep(.el-input) {
  flex: 1;
}

/* ===== Code Button ===== */
.code-btn {
  flex-shrink: 0;
  width: 110px;
  height: 40px;
  border-radius: 8px;
  border: 1px solid rgba(6, 182, 212, 0.2);
  background: rgba(6, 182, 212, 0.06);
  color: #06b6d4;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.code-btn:hover:not(:disabled) {
  background: rgba(6, 182, 212, 0.12);
  border-color: rgba(6, 182, 212, 0.35);
  box-shadow: 0 0 12px rgba(6, 182, 212, 0.1);
}

.code-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ===== Submit Button ===== */
.submit-btn {
  width: 100%;
  height: 46px;
  border-radius: 10px;
  border: none;
  background: linear-gradient(135deg, #06b6d4 0%, #0078d4 100%);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.5px;
  cursor: pointer;
  transition: all 0.25s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 4px;
  position: relative;
  overflow: hidden;
}

.submit-btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.15), transparent);
  transition: left 0.5s ease;
}

.submit-btn:hover::before {
  left: 100%;
}

.submit-btn:hover {
  box-shadow: 0 0 24px rgba(6, 182, 212, 0.35), 0 4px 12px rgba(0, 120, 212, 0.2);
  transform: translateY(-1px);
}

.submit-btn:active {
  transform: translateY(0);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* ===== Spinner ===== */
.btn-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ===== Tip Bar ===== */
.tip-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 18px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  color: #6e7681;
  font-size: 12px;
}

/* 演示环境提示：仅当构建期 VITE_DEMO_MODE=true 时出现 */
.demo-tip {
  margin-top: 10px;
  background: rgba(56, 189, 248, 0.08);
  border-color: rgba(56, 189, 248, 0.25);
  color: #7dd3fc;
}

.demo-tip b {
  color: #e0f2fe;
  font-weight: 600;
}

.tip-bar :deep(.el-icon) {
  color: #3b82f6;
}


/* ===== Prefix Label ===== */
.prefix-label {
  font-size: 14px;
  font-weight: 500;
}
</style>

<style>
/* ===== Dialog Container ===== */
.login-modal .el-dialog {
  background: rgba(13, 17, 23, 0.95) !important;
  backdrop-filter: blur(28px) saturate(1.2);
  -webkit-backdrop-filter: blur(28px) saturate(1.2);
  border: 1px solid rgba(6, 182, 212, 0.15) !important;
  border-radius: 20px !important;
  box-shadow:
    0 0 60px rgba(6, 182, 212, 0.08),
    0 20px 60px rgba(0, 0, 0, 0.5) !important;
  overflow: hidden;
}

.login-modal .el-dialog__header {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding: 24px 28px 0 !important;
  margin-right: 0 !important;
}

.login-modal .el-dialog__body {
  padding: 0 !important;
}

.login-modal .el-dialog__headerbtn {
  top: 16px !important;
  right: 16px !important;
  width: 32px !important;
  height: 32px !important;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  transition: all 0.2s ease;
}

.login-modal .el-dialog__headerbtn:hover {
  background: rgba(255, 255, 255, 0.08);
}

.login-modal .el-dialog__headerbtn .el-dialog__close {
  color: #6e7681;
  font-size: 16px;
}

.login-modal .el-dialog__headerbtn:hover .el-dialog__close {
  color: #06b6d4;
}

/* ===== Form Labels ===== */
.login-modal .el-form-item__label {
  color: #8b949e !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  padding-bottom: 6px !important;
}

/* ===== Dark Inputs ===== */
.login-modal .dark-input .el-input__wrapper {
  background: rgba(255, 255, 255, 0.04) !important;
  border: 1px solid rgba(48, 54, 61, 0.6) !important;
  border-radius: 10px !important;
  box-shadow: none !important;
  transition: all 0.2s ease !important;
}

.login-modal .dark-input .el-input__wrapper:hover {
  border-color: rgba(6, 182, 212, 0.25) !important;
  background: rgba(255, 255, 255, 0.05) !important;
}

.login-modal .dark-input .el-input__wrapper.is-focus {
  border-color: rgba(6, 182, 212, 0.4) !important;
  box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.08) !important;
  background: rgba(255, 255, 255, 0.06) !important;
}

.login-modal .dark-input .el-input__inner {
  color: #e6edf3 !important;
  font-size: 14px !important;
  height: 40px !important;
}

.login-modal .dark-input .el-input__inner::placeholder {
  color: #484f58;
}

/* ===== Prepend ===== */
.login-modal .el-input-group__prepend {
  background: rgba(255, 255, 255, 0.03) !important;
  border-color: rgba(48, 54, 61, 0.6) !important;
  border-radius: 10px 0 0 10px !important;
  color: #8b949e !important;
  font-size: 14px !important;
}

.login-modal .el-input-group--prepend .el-input__wrapper {
  border-radius: 0 10px 10px 0 !important;
}

/* ===== Overlay ===== */
.login-modal .el-overlay {
  background: rgba(0, 0, 0, 0.6) !important;
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}
</style>