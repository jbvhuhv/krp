import request from './request'

export const notesApi = {
  list: () => request.get('/notes'),
  upload: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/notes/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  get: (noteId) => request.get(`/notes/${noteId}`),
  reExtract: (noteId) => request.post(`/notes/${noteId}/re-extract`),
  remove: (noteId) => request.delete(`/notes/${noteId}`),
}