import request from './request'

export const notesApi = {
  list: () => request.get('/notes'),
  upload: (file, subject) => {
    const formData = new FormData()
    formData.append('file', file)
    // 留空表示交给模型自动判断学科
    if (subject) formData.append('subject', subject)
    return request.post('/notes/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  get: (noteId) => request.get(`/notes/${noteId}`),
  update: (noteId, payload) => request.patch(`/notes/${noteId}`, payload),
  reExtract: (noteId) => request.post(`/notes/${noteId}/re-extract`),
  remove: (noteId) => request.delete(`/notes/${noteId}`),
}
