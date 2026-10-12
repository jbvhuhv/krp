import request from './request'

export const avatarApi = {
  publish: (data) => request.post('/avatar/publish', data),
  updateConfig: (data) => request.put('/avatar/config', data),
  unpublish: () => request.post('/avatar/unpublish'),
  getMine: () => request.get('/avatar/me', { silent: true }),
  getById: (avatarId) => request.get(`/avatar/${avatarId}`),
  getStats: (avatarId) => request.get(`/avatar/${avatarId}/stats`),
  getConversations: (avatarId) => request.get(`/avatar/${avatarId}/conversations`),
  getConversation: (avatarId, visitorId) =>
    request.get(`/avatar/${avatarId}/conversations/${encodeURIComponent(visitorId)}`),
  uploadImage: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/avatar/avatar-image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}