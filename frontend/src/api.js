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
 * Subscribe to the LIVE trace stream for a claim that is currently processing.
 * Connect BEFORE calling submitClaim so events arrive in real time.
 * Returns a cleanup function that closes the EventSource.
 */
export function streamLiveTrace(claimId, { onEvent, onDone, onError }) {
  const base = import.meta.env.VITE_API_URL || ''
  const es = new EventSource(`${base}/api/claims/${claimId}/trace`)

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data.done) { es.close(); onDone?.() }
      else if (data.error) { es.close(); onError?.(data.error) }
      else { onEvent?.(data) }
    } catch { /* ignore malformed */ }
  }
  es.onerror = () => { es.close(); onError?.('SSE connection failed') }
  return () => es.close()
}

/**
 * Returns the URL to display an uploaded file (for <img src> or <object>).
 * No network call — just constructs the URL.
 */
export function getFileUrl(fileId) {
  const base = import.meta.env.VITE_API_URL || ''
  return `${base}/api/files/${fileId}`
}

/**
 * Download the PDF report for a completed claim. Triggers a browser
 * download via a temporary <a download> element.
 */
export async function downloadClaimReport(claimId) {
  const base = import.meta.env.VITE_API_URL || ''
  const res = await fetch(`${base}/api/claims/${claimId}/report`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Report download failed: ${res.status}`)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `plum_claim_${claimId.slice(0, 8)}.pdf`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/**
 * Fetch bounding-box regions for an uploaded document.
 * Completely separate from the claim pipeline — only called on user request.
 * Returns {file_id, doc_type, regions: [{field, value, bbox, category}]}
 */
export async function getDocumentRegions(fileId, docType = 'UNKNOWN') {
  const base = import.meta.env.VITE_API_URL || ''
  const res = await fetch(`${base}/api/files/${fileId}/regions?doc_type=${docType}`)
  if (!res.ok) throw new Error(`Regions fetch failed: ${res.status}`)
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
