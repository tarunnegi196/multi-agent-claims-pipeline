import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import PipelineGraph from '../components/PipelineGraph'
import ClaimForm     from '../components/ClaimForm'
import TraceLog      from '../components/TraceLog'
import DecisionCard  from '../components/DecisionCard'
import DocumentRegionViewer from '../components/DocumentRegionViewer'
import { submitClaim, getClaim, replayTrace, streamLiveTrace } from '../api'

const AGENTS = [
  'IntakeAgent', 'DocClassifierAgent', 'DocVerifierAgent',
  'ExtractionAgent', 'ConsistencyAgent', 'FraudScreenAgent',
  'DecisionComposerAgent', 'ReportAgent',
]
const IDLE_STATES = Object.fromEntries(AGENTS.map((a) => [a, 'idle']))
const IDLE_EVENTS = Object.fromEntries(AGENTS.map((a) => [a, []]))
const deriveStatus = (s) => s === 'PASS' ? 'pass' : s === 'FAIL' ? 'fail' : s === 'WARN' ? 'warn' : 'skip'

// Reduce a list of events for one agent down to its terminal status, preserving
// the "worst" signal (fail > warn > pass > skip). Used to finalise the light
// when the pipeline moves past an agent so it never gets stuck on "Running".
function reduceAgentStatus(events) {
  if (!events || events.length === 0) return 'idle'
  let result = 'skip'
  for (const e of events) {
    const s = deriveStatus(e.status)
    if (s === 'fail') return 'fail'
    if (s === 'warn' && result !== 'fail') result = 'warn'
    else if (s === 'pass' && result !== 'fail' && result !== 'warn') result = 'pass'
  }
  return result
}

const AGENT_META = {
  IntakeAgent:           { step: 1, label: 'Intake',            isLLM: false, desc: 'Validates that the employee ID is in the policy roster and at least one document was uploaded. No LLM call — pure rule check.' },
  DocClassifierAgent:    { step: 2, label: 'Classifier Agent',  isLLM: true,  desc: 'Gemini classifies every uploaded file into a document type (PRESCRIPTION, HOSPITAL_BILL, LAB_REPORT…) and rates image readability.' },
  DocVerifierAgent:      { step: 3, label: 'Verifier',          isLLM: false, desc: 'THE GATE — confirms every required document type for this claim category is present and readable. Halts with a precise actionable message if not.' },
  ExtractionAgent:       { step: 4, label: 'Extraction Agent',  isLLM: true,  desc: 'Gemini Vision pulls structured fields (patient, doctor, diagnosis, amounts, dates) and bounding boxes from every document in parallel.' },
  ConsistencyAgent:      { step: 5, label: 'Consistency Agent', isLLM: true,  desc: 'Gemini compares patient, doctor, hospital and date across all documents to catch semantic mismatches a string compare would miss.' },
  FraudScreenAgent:      { step: 6, label: 'Fraud Screen',      isLLM: false, desc: 'Deterministic signals: same-day claim count, monthly count, high-value threshold, document alteration flags, and cross-doc consistency warnings.' },
  DecisionComposerAgent: { step: 7, label: 'Decision',          isLLM: false, desc: 'Deterministic policy engine — applies waiting periods, exclusions, network discount, copay, sub-limits to produce verdict + amount.' },
  ReportAgent:           { step: 8, label: 'Report Agent',      isLLM: true,  desc: 'Gemini synthesises a human-readable narrative, a confidence-reasoning paragraph and a prioritised list of next-best-actions.' },
}

const STATUS_DOT = {
  idle:   { color: '#9e708c', label: 'Idle'     },
  active: { color: '#bea0b3', label: 'Running…' },
  pass:   { color: '#92bd33', label: 'Passed'   },
  fail:   { color: '#ff4052', label: 'Halted'   },
  warn:   { color: '#ffbf21', label: 'Warning'  },
  skip:   { color: '#7b5068', label: 'Skipped'  },
}

/* ── Left panel ─────────────────────────────────────────────────── */
function LeftPanel({ title, subtitle, action, children, dark = false }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%',
      background: dark ? '#11040d' : '#fffaf2' }}>
      <div style={{
        padding: '12px 18px',
        borderBottom: `1px solid ${dark ? '#2c0b21' : '#ced5dd'}`,
        background: dark ? '#150410' : '#fff8f1',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0,
      }}>
        <div>
          <h5 style={{ color: dark ? '#d8c5d1' : '#41495e', margin: 0, fontSize: 13, fontWeight: 700 }}>{title}</h5>
          {subtitle && <p style={{ color: dark ? '#9e708c' : '#55657d', margin: 0, fontSize: 11, marginTop: 2 }}>{subtitle}</p>}
        </div>
        {action}
      </div>
      <div style={{
        flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '16px 18px',
        scrollbarWidth: 'thin',
        scrollbarColor: dark ? '#340926 #11040d' : '#d8c5d1 #fffaf2',
      }}>
        {children}
      </div>
    </div>
  )
}

/* ── Agent Inspector (shown inside the modal) ───────────────────── */
function AgentInspector({ selectedAgent, nodeStates, nodeEvents, documents, onPreviewRegions, onClose }) {
  const meta   = AGENT_META[selectedAgent] || { step: '?', label: selectedAgent, desc: '' }
  const status = nodeStates[selectedAgent] || 'idle'
  const events = nodeEvents[selectedAgent] || []
  const sd     = STATUS_DOT[status] || STATUS_DOT.idle

  // For ExtractionAgent: index documents by file_id so events can offer a region preview.
  const docByFileId = {}
  ;(documents || []).forEach((d) => { if (d.viewable) docByFileId[d.file_id] = d })

  const lastConf  = events.length > 0 ? events[events.length - 1].confidence : null
  const totalMs   = events.reduce((s, e) => s + (e.duration_ms || 0), 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* Modal header */}
      <div style={{
        padding: '16px 24px', borderBottom: '1px solid #2c0b21', flexShrink: 0,
        background: 'rgba(0,0,0,0.3)',
        display: 'flex', alignItems: 'flex-start', gap: 12,
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <span style={{
              fontSize: 11, fontWeight: 800, color: '#bea0b3',
              background: 'rgba(190,160,179,0.12)', border: '1px solid #460932',
              borderRadius: 99, padding: '2px 10px',
            }}>
              Step {meta.step} of 8
              {meta.isLLM && (
                <span style={{
                  background: '#570e40', color: '#fff', borderRadius: 4,
                  padding: '1px 6px', fontSize: 9, fontWeight: 800, letterSpacing: 0.4,
                  marginLeft: 6,
                }}>LLM</span>
              )}
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: sd.color, fontWeight: 600 }}>
              <span style={{
                width: 7, height: 7, borderRadius: '50%', background: sd.color,
                boxShadow: status === 'active' ? `0 0 8px ${sd.color}` : 'none',
              }} />
              {sd.label}
            </span>
          </div>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#d8c5d1', marginBottom: 4 }}>{meta.label}</div>
          <div style={{ fontSize: 13, color: '#9e708c', lineHeight: '18px' }}>{meta.desc}</div>
        </div>

        {/* Quick stats */}
        <div style={{ display: 'flex', gap: 20, flexShrink: 0, textAlign: 'right', alignItems: 'flex-start' }}>
          {lastConf != null && (
            <div>
              <div style={{ fontSize: 22, fontWeight: 800, color: lastConf >= 0.8 ? '#92bd33' : lastConf >= 0.5 ? '#ffbf21' : '#ff4052' }}>
                {Math.round(lastConf * 100)}%
              </div>
              <div style={{ fontSize: 10, color: '#9e708c', textTransform: 'uppercase', letterSpacing: '0.06em' }}>confidence</div>
            </div>
          )}
          {totalMs > 0 && (
            <div>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#bea0b3' }}>{totalMs}ms</div>
              <div style={{ fontSize: 10, color: '#9e708c', textTransform: 'uppercase', letterSpacing: '0.06em' }}>total time</div>
            </div>
          )}
          <div>
            <div style={{ fontSize: 22, fontWeight: 800, color: '#d8c5d1' }}>{events.length}</div>
            <div style={{ fontSize: 10, color: '#9e708c', textTransform: 'uppercase', letterSpacing: '0.06em' }}>events</div>
          </div>
        </div>

        {/* Close button */}
        <button
          onClick={onClose}
          style={{
            background: 'rgba(255,255,255,0.04)', border: '1px solid #340926',
            borderRadius: 8, color: '#9e708c', cursor: 'pointer',
            fontSize: 16, lineHeight: 1, padding: '6px 10px',
            transition: 'color 0.15s, background 0.15s', flexShrink: 0,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#d8c5d1'; e.currentTarget.style.background = 'rgba(255,255,255,0.08)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = '#9e708c'; e.currentTarget.style.background = 'rgba(255,255,255,0.04)' }}
        >
          ✕
        </button>
      </div>

      {/* Event list */}
      <div style={{ flex: 1, overflowY: 'auto', scrollbarWidth: 'thin', scrollbarColor: '#340926 #11040d' }}>
        {events.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 80,
            fontSize: 13, color: '#9e708c', fontStyle: 'italic' }}>
            No events yet — submit a claim to watch this agent run
          </div>
        ) : (
          events.map((evt, i) => {
            const statusColors = { PASS: '#92bd33', FAIL: '#ff4052', WARN: '#ffbf21', SKIP: '#9e708c' }
            const c = statusColors[evt.status] || '#9e708c'
            // Detect extraction events tied to an uploaded file → offer region preview
            const extractMatch = selectedAgent === 'ExtractionAgent' && /^extract\.([^.]+)$/.exec(evt.step_id || '')
            const previewDoc = extractMatch ? docByFileId[extractMatch[1]] : null
            return (
              <div key={i} style={{ padding: '10px 24px', borderBottom: '1px solid #2c0b21',
                display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                <div style={{ flexShrink: 0, marginTop: 2 }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, fontFamily: 'monospace',
                    color: c, background: `${c}15`, border: `1px solid ${c}44`,
                    padding: '2px 7px', borderRadius: 4,
                  }}>
                    {evt.status}
                  </span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, color: '#9e708c', fontFamily: 'monospace', marginBottom: 3 }}>
                    {evt.step_id}
                  </div>
                  {evt.detail && (
                    <div style={{ fontSize: 13, color: '#d8c5d1', lineHeight: '17px' }}>{evt.detail}</div>
                  )}
                  {previewDoc && (
                    <button
                      onClick={() => onPreviewRegions?.(previewDoc)}
                      title="Show this document with bounding boxes around each extracted field"
                      style={{
                        marginTop: 6,
                        display: 'inline-flex', alignItems: 'center', gap: 5,
                        background: 'rgba(74,144,226,0.08)', border: '1px solid rgba(74,144,226,0.35)',
                        borderRadius: 99, padding: '3px 10px', cursor: 'pointer',
                        fontSize: 10, fontWeight: 700, color: '#4a90e2',
                        transition: 'background 0.1s, border-color 0.1s',
                        fontFamily: 'Inter, Arial, sans-serif',
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(74,144,226,0.18)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(74,144,226,0.08)' }}
                    >
                      &#9681; Preview extracted regions
                    </button>
                  )}
                  {evt.error && (
                    <div style={{ fontSize: 12, color: '#ff4052', marginTop: 3, fontFamily: 'monospace',
                      background: 'rgba(255,64,82,0.08)', padding: '3px 8px', borderRadius: 4 }}>
                      {evt.error}
                    </div>
                  )}
                  {evt.rule_reference && (
                    <span style={{
                      fontSize: 10, fontFamily: 'monospace', padding: '2px 6px', borderRadius: 4,
                      background: 'rgba(123,64,103,0.15)', color: '#bea0b3', border: '1px solid #460932',
                      display: 'inline-block', marginTop: 3,
                    }}>
                      {evt.rule_reference}
                    </span>
                  )}
                </div>
                {evt.duration_ms != null && (
                  <div style={{ flexShrink: 0, fontSize: 11, color: '#9e708c', fontFamily: 'monospace', marginTop: 2 }}>
                    {evt.duration_ms}ms
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

/* ── Main page ────────────────────────────────────────────────────── */
export default function SubmitPage() {
  const { id: routeId } = useParams()
  const navigate        = useNavigate()

  const [isSubmitting,  setSubmitting]  = useState(false)
  const [error,         setError]       = useState(null)
  const [result,        setResult]      = useState(null)
  const [allEvents,     setAllEvents]   = useState([])
  const [nodeStates,    setNodeStates]  = useState(IDLE_STATES)
  const [nodeEvents,    setNodeEvents]  = useState(IDLE_EVENTS)
  const [currentAgent,  setCurrent]     = useState(null)
  const [replayActive,  setReplayActive]= useState(false)
  const [selectedAgent, setSelected]   = useState(null)
  const [regionViewer, setRegionViewer]= useState(null) // {fileId, docType, fileName}
  const cleanupRef   = useRef(null)
  const skipReplayRef = useRef(false) // true when live SSE already updated the graph

  const loadAndReplay = useCallback(async (claimId, preloaded = null) => {
    let data = preloaded
    if (!data) { try { data = await getClaim(claimId) } catch (e) { setError(e.message); return } }

    setResult(data); setAllEvents([]); setNodeStates(IDLE_STATES)
    setNodeEvents(IDLE_EVENTS); setCurrent(null); setReplayActive(true)
    await new Promise((r) => setTimeout(r, 120))

    const cleanup = replayTrace(claimId, {
      speed: 2.0,
      onEvent(evt) {
        setAllEvents((p) => [...p, evt])
        setNodeEvents((p) => {
          const nextEvents = { ...p, [evt.agent]: [...(p[evt.agent] || []), evt] }
          // Finalise EVERY other agent's state from its accumulated events so
          // a previously-active agent never gets stuck on the "Running" light
          // when the pipeline moves past it.
          setNodeStates((ps) => {
            const next = { ...ps }
            for (const a of AGENTS) {
              if (a === evt.agent) {
                next[a] = 'active'
              } else if (nextEvents[a]?.length) {
                next[a] = reduceAgentStatus(nextEvents[a])
              }
            }
            return next
          })
          return nextEvents
        })
        setCurrent(evt.agent)
      },
      onDone() {
        setNodeEvents((nev) => {
          const final = { ...IDLE_STATES }
          for (const a of AGENTS) {
            if (nev[a]?.length) final[a] = reduceAgentStatus(nev[a])
          }
          setNodeStates(final)
          return nev
        })
        setCurrent(null); setReplayActive(false)
      },
      onError() { setReplayActive(false) },
    })
    cleanupRef.current = cleanup
  }, [])

  useEffect(() => {
    // Skip replay when live SSE already updated the graph (fresh submission)
    if (routeId && !skipReplayRef.current) loadAndReplay(routeId)
    skipReplayRef.current = false
    return () => cleanupRef.current?.()
  }, [routeId, loadAndReplay])

  async function handleSubmit(payload) {
    // Generate claim ID client-side so we can subscribe to the live SSE stream
    // before the POST reaches the server — this is the key to real-time agent updates.
    const claimId = crypto.randomUUID()

    cleanupRef.current?.()
    setSubmitting(true); setError(null); setResult(null)
    setAllEvents([]); setNodeStates(IDLE_STATES); setNodeEvents(IDLE_EVENTS)
    setSelected(null)

    // Optimistic kick — IntakeAgent starts pulsing immediately so the user
    // sees motion the moment they click Submit, before the first SSE event lands.
    setCurrent('IntakeAgent')
    setNodeStates({ ...IDLE_STATES, IntakeAgent: 'active' })

    // 1. Subscribe to live SSE FIRST
    const sseCleanup = streamLiveTrace(claimId, {
      onEvent(evt) {
        setAllEvents((p) => [...p, evt])
        setNodeEvents((p) => {
          const nextEvents = { ...p, [evt.agent]: [...(p[evt.agent] || []), evt] }
          // For every other agent that has finished emitting events, lock in
          // its terminal status (pass/warn/fail) — only the currently-active
          // agent stays on the "Running" light.
          setNodeStates((ps) => {
            const next = { ...ps }
            for (const a of AGENTS) {
              if (a === evt.agent) {
                next[a] = 'active'
              } else if (nextEvents[a]?.length) {
                next[a] = reduceAgentStatus(nextEvents[a])
              }
            }
            return next
          })
          return nextEvents
        })
        setCurrent(evt.agent)
      },
      onDone() {
        setNodeEvents((nev) => {
          const final = { ...IDLE_STATES }
          for (const a of AGENTS) {
            if (nev[a]?.length) final[a] = reduceAgentStatus(nev[a])
          }
          setNodeStates(final)
          return nev
        })
        setCurrent(null)
      },
      onError() { /* non-fatal — HTTP response still carries the result */ },
    })
    cleanupRef.current = sseCleanup

    try {
      // 2. Submit — pipeline runs server-side while SSE pushes events to us
      const data = await submitClaim({ ...payload, claim_id: claimId })
      setResult(data)
      // 3. Navigate to the claim URL; tell the useEffect not to trigger a replay
      //    since the graph is already live-updated
      skipReplayRef.current = true
      navigate(`/claims/${data.claim_id}`, { replace: true })
    } catch (e) {
      setError(e.message)
      sseCleanup()
    } finally {
      setSubmitting(false)
    }
  }

  function handleReset() {
    cleanupRef.current?.()
    setResult(null); setAllEvents([]); setNodeStates(IDLE_STATES)
    setNodeEvents(IDLE_EVENTS); setCurrent(null); setSelected(null)
    setReplayActive(false); setError(null)
    navigate('/', { replace: true })
  }

  const displayStates = currentAgent ? { ...nodeStates, [currentAgent]: 'active' } : nodeStates

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 56px)', overflow: 'hidden' }}>

      {/* ── Left: form / decision ────────────────────────── */}
      <aside style={{ width: 320, minWidth: 280, borderRight: '1px solid #ced5dd',
        display: 'flex', flexDirection: 'column', flexShrink: 0, height: '100%', overflow: 'hidden',
        boxShadow: '6px 0 28px rgba(0,0,0,0.5)', zIndex: 1 }}>
        <LeftPanel
          title={result ? 'Decision' : 'Submit Claim'}
          subtitle={result ? `${result.member_id} · ${result.claim_category}` : 'Fill the form or load a test case'}
          dark={!!result}
          action={result && (
            <button onClick={handleReset}
              style={{ background: 'none', border: 'none', cursor: 'pointer',
                color: '#9e708c', fontSize: 11, fontWeight: 600,
                transition: 'color 0.1s', fontFamily: 'Inter, Arial, sans-serif' }}
              onMouseEnter={(e) => { e.currentTarget.style.color = '#ff4052' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = '#9e708c' }}>
              ↺ New claim
            </button>
          )}
        >
          {result
            ? <DecisionCard result={result} processingMs={result.processing_time_ms} onNewClaim={handleReset} />
            : <ClaimForm onSubmit={handleSubmit} isSubmitting={isSubmitting} />
          }
        </LeftPanel>
      </aside>

      {/* ── Centre: pipeline graph (full height) ─────────────── */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden', background: '#11040d' }}>

        {/* Centre header */}
        <div style={{ padding: '10px 16px', borderBottom: '1px solid #2c0b21', background: '#150410',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <div>
            <span style={{ fontWeight: 700, fontSize: 13, color: '#d8c5d1' }}>Claims Processing Pipeline</span>
            <span style={{ fontSize: 11, color: '#9e708c', marginLeft: 10 }}>
              {result
                ? `${result.member_id} · ${result.claim_category}`
                : 'Select a test case on the left, then click Submit Claim'}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {isSubmitting && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11,
                background: 'rgba(146,189,51,0.08)', border: '1px solid rgba(146,189,51,0.3)',
                borderRadius: 30, padding: '4px 12px', color: '#92bd33' }}>
                <svg style={{ animation: '0.7s linear infinite spin', width: 10, height: 10, flexShrink: 0 }}
                  viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" strokeOpacity="0.25"/>
                  <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z"/>
                </svg>
                Pipeline running…
              </span>
            )}
            {replayActive && !isSubmitting && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11,
                background: 'rgba(123,64,103,0.12)', border: '1px solid #460932', borderRadius: 30,
                padding: '3px 10px', color: '#bea0b3' }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#7b4067',
                  animation: '0.8s linear infinite spin', display: 'inline-block' }} />
                Replaying…
              </span>
            )}
            {result && !replayActive && !isSubmitting && (
              <button onClick={() => loadAndReplay(result.claim_id, result)}
                className="btn-action" style={{ fontFamily: 'Inter, Arial, sans-serif' }}>
                ↻ Replay
              </button>
            )}
          </div>
        </div>

        {/* Pipeline graph — full remaining height */}
        <div style={{ flex: 1, position: 'relative', minHeight: 200 }}>

            <PipelineGraph
            nodeStates={displayStates} nodeEvents={nodeEvents}
            selectedAgent={selectedAgent}
            onNodeClick={(agent) => setSelected((p) => p === agent ? null : agent)}
          />
        </div>

        {/* Error */}
        {error && (
          <div style={{ margin: '0 16px 10px', background: '#ffdddd', border: '1px solid #ff4052',
            borderRadius: 8, padding: '8px 14px', fontSize: 13, color: '#ea384c', flexShrink: 0 }}>
            <strong>Error: </strong>{error}
          </div>
        )}
      </main>

      {/* ── Right: trace log ─────────────────────────────── */}
      <aside style={{ width: 290, minWidth: 230, display: 'flex', flexDirection: 'column', flexShrink: 0,
        boxShadow: '-6px 0 28px rgba(0,0,0,0.55)', zIndex: 1 }}>
        <TraceLog events={allEvents} replayActive={replayActive} />
      </aside>

      {/* ── Agent Inspector Modal ────────────────────────── */}
      {selectedAgent && (
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 50,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(11,3,9,0.88)',
            backdropFilter: 'blur(6px)',
          }}
          onClick={() => setSelected(null)}
        >
          <div
            style={{
              background: '#150410',
              border: '1px solid #340926',
              borderRadius: 20,
              width: 'min(88vw, 820px)',
              maxHeight: '80vh',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 32px 80px rgba(0,0,0,0.7), 0 0 0 1px rgba(70,9,50,0.4)',
              animation: 'fade-in 0.15s ease',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <AgentInspector
              selectedAgent={selectedAgent}
              nodeStates={displayStates}
              nodeEvents={nodeEvents}
              documents={result?.documents || []}
              onPreviewRegions={(d) => setRegionViewer({ fileId: d.file_id, docType: d.doc_type, fileName: d.file_name })}
              onClose={() => setSelected(null)}
            />
          </div>
        </div>
      )}

      {/* Region viewer launched from the Extraction agent inspector */}
      {regionViewer && (
        <DocumentRegionViewer
          fileId={regionViewer.fileId}
          docType={regionViewer.docType}
          fileName={regionViewer.fileName}
          onClose={() => setRegionViewer(null)}
        />
      )}
    </div>
  )
}
