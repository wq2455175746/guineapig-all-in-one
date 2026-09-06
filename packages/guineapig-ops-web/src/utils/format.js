export function formatTime(t) {
  if (!t) return '-'
  return String(t).substring(0, 19).replace('T', ' ')
}