import request from './request'

export const petApi = {
  getStatus: () => request.get('/pet/status', { silentAuth: true }),
  harvest: () => request.post('/pet/harvest'),
  feed: () => request.post('/pet/feed'),

  setVoice: (voicePreset) => request.post('/pet/voice', { voice_preset: voicePreset }),
}