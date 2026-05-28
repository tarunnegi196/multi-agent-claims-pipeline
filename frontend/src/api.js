const BASE = import.meta.env.VITE_API_URL || ''

export async function submitClaim(data) {
  const res = await fetch(`${BASE}/api/claims`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const text = await res.text()
    let detail = `HTTP ${res.status}`
    try { detail = JSON.parse(text).detail || text } catch {}
    throw new Error(detail)
  }
  return res.json()
}

export async function getClaim(id) {
  const res = await fetch(`${BASE}/api/claims/${id}`)
  if (!res.ok) throw new Error(`Claim '${id}' not found`)
  return res.json()
}

export async function listClaims(limit = 50) {
  const res = await fetch(`${BASE}/api/claims?limit=${limit}`)
  if (!res.ok) throw new Error('Failed to load claims list')
  return res.json()
}

export async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/api/files`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
  return res.json()
}

/**
 * Stream replayed trace events for a completed claim.
 * Returns a cleanup function that closes the EventSource.
 */
export function replayTrace(claimId, { onEvent, onDone, onError, speed = 2.0 }) {
  const url = `${BASE}/api/claims/${claimId}/trace/replay?speed=${speed}`
  const es = new EventSource(url)

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data.done) {
        es.close()
        onDone?.()
      } else if (data.error) {
        es.close()
        onError?.(data.error)
      } else {
        onEvent?.(data)
      }
    } catch {
      // ignore malformed events
    }
  }

  es.onerror = () => {
    es.close()
    onError?.('SSE connection failed')
  }

  return () => es.close()
}
