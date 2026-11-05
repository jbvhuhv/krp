import request from './request'

export const authApi = {
  sendCode: (phone) => request.post('/auth/send-code', { phone }),
  login: (data) => request.post('/auth/login', data),
  me: () => request.get('/auth/me'),
  updateMe: (data) => request.put('/auth/me', data),
  exportMyData: () => request.get('/auth/me/export'),
  deleteMe: () => request.delete('/auth/me'),
}