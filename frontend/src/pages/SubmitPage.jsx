import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import PipelineGraph from '../components/PipelineGraph'
import ClaimForm from '../components/ClaimForm'
import TraceLog from '../components/TraceLog'
import DecisionCard from '../components/DecisionCard'
import { submitClaim, getClaim, replayTrace } from '../api'

const AGENTS = [
  'IntakeAgent','DocClassifierAgent','DocVerifierAgent',
  'ExtractionAgent','FraudScreenAgent','DecisionComposerAgent',
]
const IDLE_NODE_STATES = Object.fromEntries(AGENTS.map((a) => [a, 'idle']))
const IDLE_NODE_EVENTS = Object.fromEntries(AGENTS.map((a) => [a, []]))

const deriveStatus = (s) =>
  s === 'PASS' ? 'pass' : s === 'FAIL' ? 'fail' : s === 'WARN' ? 'warn' : 'skip'

/* ── Panel wrapper ──────────────────────────────────────────────── */
function Panel({ title, subtitle, action, children, className = '' }) {
  return (
    <div className={`flex flex-col ${className}`} style={{ background: '#0C0A1C' }}>
      <div
        className="px-4 py-3 border-b flex items-center justify-between shrink-0"
        style={{ borderColor: '#2A2550', background: '#141130' }}
      >
        <div>
          <h2 className="text-sm font-semibold" style={{ color: '#E9E6FF' }}>{title}</h2>
          {subtitle && <p className="text-xs mt-0.5" style={{ color: '#6B6896' }}>{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className="flex-1 overflow-y-auto p-4">{children}</div>
    </div>
  )
}

/* ── Legend chip ────────────────────────────────────────────────── */
function LegendChip({ label, color }) {
  return (
    <span
      className="text-xs px-2 py-0.5 rounded-full font-medium"
      style={{ color, border: `1px solid ${color}44`, background: `${color}18` }}
    >
      {label}
    </span>
  )
}

/* ── Main page ──────────────────────────────────────────────────── */
export default function SubmitPage() {
  const { id: routeId } = useParams()
  const navigate        = useNavigate()

  const [isSubmitting,  setSubmitting]  = useState(false)
  const [error,         setError]       = useState(null)
  const [result,        setResult]      = useState(null)
  const [allEvents,     setAllEvents]   = useState([])
  const [nodeStates,    setNodeStates]  = useState(IDLE_NODE_STATES)
  const [nodeEvents,    setNodeEvents]  = useState(IDLE_NODE_EVENTS)
  const [currentAgent,  setCurrent]     = useState(null)
  const [replayActive,  setReplayActive]= useState(false)
  const [selectedAgent, setSelected]   = useState(null)

  const cleanupRef = useRef(null)

  const loadAndReplay = useCallback(async (claimId, preloaded = null) => {
    let data = preloaded
    if (!data) {
      try { data = await getClaim(claimId) }
      catch (e) { setError(e.message); return }
    }

    setResult(data)
    setAllEvents([])
    setNodeStates(IDLE_NODE_STATES)
    setNodeEvents(IDLE_NODE_EVENTS)
    setCurrent(null)
    setReplayActive(true)

    await new Promise((r) => setTimeout(r, 120))

    const cleanup = replayTrace(claimId, {
      speed: 2.0,
      onEvent(evt) {
        setAllEvents((p) => [...p, evt])
        setCurrent(evt.agent)
        setNodeEvents((p) => ({ ...p, [evt.agent]: [...(p[evt.agent] || []), evt] }))
        setNodeStates((p) => ({ ...p, [evt.agent]: 'active' }))
      },
      onDone() {
        setAllEvents((prev) => {
          const final = { ...IDLE_NODE_STATES }
          prev.forEach((e) => { final[e.agent] = deriveStatus(e.status) })
          setNodeStates(final)
          return prev
        })
        setCurrent(null)
        setReplayActive(false)
      },
      onError(msg) { console.warn('SSE replay error:', msg); setReplayActive(false) },
    })
    cleanupRef.current = cleanup
  }, [])

  useEffect(() => {
    if (routeId) loadAndReplay(routeId)
    return () => cleanupRef.current?.()
  }, [routeId, loadAndReplay])

  async function handleSubmit(payload) {
    setSubmitting(true)
    setError(null)
    setResult(null)
    setAllEvents([])
    setNodeStates(IDLE_NODE_STATES)
    setNodeEvents(IDLE_NODE_EVENTS)
    setCurrent(null)
    setSelected(null)
    cleanupRef.current?.()

    try {
      const data = await submitClaim(payload)
      navigate(`/claims/${data.claim_id}`, { replace: true })
      await loadAndReplay(data.claim_id, data)
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  function handleReset() {
    cleanupRef.current?.()
    setResult(null); setAllEvents([]); setNodeStates(IDLE_NODE_STATES)
    setNodeEvents(IDLE_NODE_EVENTS); setCurrent(null); setSelected(null)
    setReplayActive(false); setError(null)
    navigate('/', { replace: true })
  }

  const displayStates = currentAgent
    ? { ...nodeStates, [currentAgent]: 'active' }
    : nodeStates

  return (
    <div className="flex" style={{ height: 'calc(100vh - 56px)' }}>

      {/* ── Left panel: form / result ─────────────────────────── */}
      <aside
        className="w-80 min-w-72 border-r flex flex-col shrink-0"
        style={{ borderColor: '#2A2550' }}
      >
        <Panel
          title={result ? 'Decision' : 'Submit Claim'}
          subtitle={
            result
              ? `${result.member_id} · ${result.claim_category}`
              : 'Fill the form or choose a test case preset'
          }
          action={
            result && (
              <button
                onClick={handleReset}
                className="text-xs transition-colors hover:text-plum-300"
                style={{ color: '#6B6896' }}
              >
                ↺ New claim
              </button>
            )
          }
        >
          {result
            ? <DecisionCard result={result} processingMs={result.processing_time_ms} />
            : <ClaimForm onSubmit={handleSubmit} isSubmitting={isSubmitting} />
          }
        </Panel>
      </aside>

      {/* ── Centre: pipeline graph ────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden" style={{ background: '#0C0A1C' }}>

        {/* Graph area */}
        <div className="flex-1 relative" style={{ minHeight: 200 }}>

          {/* Legend */}
          <div className="absolute top-3 left-3 z-10 flex flex-wrap gap-1.5 pointer-events-none">
            <LegendChip label="Idle"        color="#3A3568" />
            <LegendChip label="Processing"  color="#7C5CFC" />
            <LegendChip label="Pass"        color="#34d399" />
            <LegendChip label="Halt / Fail" color="#F87171" />
            <LegendChip label="Warn"        color="#FBBF24" />
          </div>

          {/* Action buttons top-right */}
          <div className="absolute top-3 right-3 z-10 flex gap-2">
            {result && !replayActive && (
              <button
                onClick={() => loadAndReplay(result.claim_id, result)}
                className="text-xs border px-3 py-1.5 rounded-lg transition-all hover:shadow-lg"
                style={{
                  background: 'rgba(124,92,252,0.1)', borderColor: 'rgba(124,92,252,0.4)',
                  color: '#B8A9FF', boxShadow: 'none',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 0 12px rgba(124,92,252,0.3)' }}
                onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none' }}
              >
                ↻ Replay
              </button>
            )}
            {replayActive && (
              <span
                className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full"
                style={{ background: 'rgba(124,92,252,0.12)', border: '1px solid rgba(124,92,252,0.35)', color: '#B8A9FF' }}
              >
                <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#7C5CFC' }} />
                Replaying trace…
              </span>
            )}
          </div>

          {/* Submitting overlay */}
          {isSubmitting && (
            <div className="absolute inset-0 flex items-center justify-center z-20" style={{ background: 'rgba(12,10,28,0.85)' }}>
              <div
                className="rounded-2xl px-8 py-6 text-center border"
                style={{ background: '#141130', borderColor: '#2A2550', boxShadow: '0 0 40px rgba(124,92,252,0.15)' }}
              >
                <div className="relative w-12 h-12 mx-auto mb-4">
                  <svg className="animate-spin w-12 h-12 absolute inset-0" viewBox="0 0 48 48" fill="none">
                    <circle cx="24" cy="24" r="20" stroke="#2A2550" strokeWidth="4" />
                    <path d="M24 4a20 20 0 0120 20" stroke="#7C5CFC" strokeWidth="4" strokeLinecap="round" />
                  </svg>
                  {/* Shield icon in center */}
                  <div className="absolute inset-0 flex items-center justify-center">
                    <svg width="18" height="18" viewBox="0 0 30 30" fill="none">
                      <path d="M15 3C15 3 7 6 7 13C7 19.5 11 24 15 26.5C19 24 23 19.5 23 13C23 6 15 3 15 3Z" fill="#7C5CFC" />
                    </svg>
                  </div>
                </div>
                <p className="text-sm font-semibold" style={{ color: '#C4B5FD' }}>Running pipeline…</p>
                <p className="text-xs mt-1" style={{ color: '#6B6896' }}>LLM extraction may take 10–20 s</p>
              </div>
            </div>
          )}

          <PipelineGraph
            nodeStates={displayStates}
            nodeEvents={nodeEvents}
            selectedAgent={selectedAgent}
            onNodeClick={(agent) => setSelected((p) => p === agent ? null : agent)}
          />
        </div>

        {/* Node detail strip */}
        {selectedAgent && (
          <div
            className="border-t flex flex-col"
            style={{ height: 180, borderColor: '#2A2550', background: '#0C0A1C' }}
          >
            <div
              className="flex items-center justify-between px-4 py-2 border-b shrink-0"
              style={{ borderColor: '#2A2550', background: '#141130' }}
            >
              <span className="text-xs font-semibold" style={{ color: '#C4B5FD' }}>
                {selectedAgent} — click node to inspect
              </span>
              <button onClick={() => setSelected(null)} style={{ color: '#6B6896' }} className="text-xs hover:text-white transition-colors">
                ✕ close
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <TraceLog events={allEvents} filterAgent={selectedAgent} replayActive={replayActive} />
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div
            className="mx-4 mb-3 rounded-xl p-3 text-sm border"
            style={{ background: '#2D0A0A', borderColor: '#7F1D1D', color: '#F87171' }}
          >
            <strong>Error: </strong>{error}
          </div>
        )}
      </main>

      {/* ── Right panel: trace log ────────────────────────────── */}
      <aside
        className="w-80 min-w-64 border-l flex flex-col shrink-0"
        style={{ borderColor: '#2A2550' }}
      >
        <TraceLog events={allEvents} replayActive={replayActive} />
      </aside>
    </div>
  )
}
