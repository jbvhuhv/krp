import request from './request'

export const notificationsApi = {
  list: (params) => request.get('/notifications', { params, silent: true }),
  markRead: (id) => request.put(`/notifications/${id}/read`, null, { silent: true }),
}