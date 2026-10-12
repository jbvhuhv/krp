import request from './request'

export const communityApi = {
  listPosts: (params) => request.get('/community/posts', { params }),
  getPost: (id) => request.get(`/community/posts/${id}`),
  createPost: (data) => request.post('/community/posts', data),
  uploadCover: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/community/cover', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  likePost: (id) => request.post(`/community/posts/${id}/like`),
  forkPost: (id) => request.post(`/community/posts/${id}/fork`),
  myPosts: () => request.get('/community/my-posts'),
  setPostVisibility: (id, isPublic) =>
    request.post(`/community/posts/${id}/visibility`, { is_public: isPublic }),
  deletePost: (id) => request.delete(`/community/posts/${id}`),
  listComments: (postId) => request.get(`/community/posts/${postId}/comments`),
  createComment: (postId, content, parentId = null) =>
    request.post(`/community/posts/${postId}/comments`, {
      content,
      parent_id: parentId,
    }),
  deleteComment: (commentId) => request.delete(`/community/comments/${commentId}`),
}