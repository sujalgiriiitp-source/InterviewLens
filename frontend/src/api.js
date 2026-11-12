// Thin API client for the InterviewLens backend (FastAPI, port 8000).
// All data comes from the API — this module never invents questions,
// skills, or summaries. Errors are surfaced verbatim, never swallowed.

async function handleResponse(res) {
  let data = null
  try {
    data = await res.json()
  } catch {
    // Non-JSON response (e.g. a proxy/connection error page).
  }
  if (!res.ok) {
    const detail =
      (data && (data.detail || data.message || data.error)) ||
      `Request failed with status ${res.status}`
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data
}

export async function fetchRoles() {
  const res = await fetch('/api/roles')
  return handleResponse(res)
}

export async function createSession(file, role) {
  const form = new FormData()
  form.append('resume', file)
  form.append('role', role)
  const res = await fetch('/api/sessions', { method: 'POST', body: form })
  return handleResponse(res)
}

export async function submitAnswer(sessionId, questionId, answer) {
  const res = await fetch(`/api/sessions/${sessionId}/answers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question_id: questionId, answer }),
  })
  return handleResponse(res)
}

export async function finishSession(sessionId) {
  const res = await fetch(`/api/sessions/${sessionId}/finish`, {
    method: 'POST',
  })
  return handleResponse(res)
}

export async function fetchSummary(sessionId) {
  const res = await fetch(`/api/sessions/${sessionId}/summary`)
  return handleResponse(res)
}
