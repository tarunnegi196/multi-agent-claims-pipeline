const STATUS_META = {
  PASS: { color: '#34d399', bg: '#022c22', label: 'PASS' },
  FAIL: { color: '#F87171', bg: '#2D0A0A', label: 'FAIL' },
  WARN: { color: '#FBBF24', bg: '#2D1A00', label: 'WARN' },
  SKIP: { color: '#6B6896', bg: '#141130', label: 'SKIP' },
}

const AGENT_SHORT = {
  IntakeAgent:           'Intake',
  DocClassifierAgent:    'Classifier',
  DocVerifierAgent:      'Verifier',
  ExtractionAgent:       'Extractor',
  FraudScreenAgent:      'Fraud',
  DecisionComposerAgent: 'Composer',
}

/* Plum purple per-agent accent */
const AGENT_COLOR = {
  IntakeAgent:           '#9B82FD',
  DocClassifierAgent:    '#B8A9FF',
  DocVerifierAgent:      '#C4B5FD',
  ExtractionAgent:       '#A78BFA',
  FraudScreenAgent:      '#8B7FF5',
  DecisionComposerAgent: '#7C5CFC',
}

function StatusBadge({ status }) {
  const m = STATUS_META[status] || STATUS_META.SKIP
  return (
    <span
      style={{ background: m.bg, color: m.color, border: `1px solid ${m.color}44` }}
      className="text-xs font-bold px-1.5 py-0.5 rounded font-mono shrink-0"
    >
      {m.label}
    </span>
  )
}

function ConfBar({ value }) {
  if (value == null) return null
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? '#34d399' : pct >= 50 ? '#FBBF24' : '#F87171'
  return (
    <div className="flex items-center gap-1.5 mt-1.5">
      <div className="flex-1 rounded-full h-1" style={{ background: '#2A2550' }}>
        <div style={{ width: `${pct}%`, background: color }} className="h-1 rounded-full transition-all duration-500" />
      </div>
      <span className="text-xs font-mono" style={{ color }}>{pct}%</span>
    </div>
  )
}

function TraceEventRow({ event, isNew }) {
  const agentShort = AGENT_SHORT[event.agent] || event.agent
  const agentColor = AGENT_COLOR[event.agent] || '#9B82FD'
  return (
    <div
      className="px-3 py-2.5 border-b transition-colors"
      style={{
        borderColor: '#1D1840',
        background: isNew ? 'rgba(124,92,252,0.06)' : 'transparent',
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <StatusBadge status={event.status} />
        <span className="text-xs font-semibold shrink-0" style={{ color: agentColor }}>{agentShort}</span>
        <span className="text-xs truncate" style={{ color: '#3A3568' }}>{event.step_id}</span>
        {event.duration_ms != null && (
          <span className="text-xs ml-auto shrink-0" style={{ color: '#3A3568' }}>{event.duration_ms}ms</span>
        )}
      </div>

      {event.detail && (
        <p className="text-xs leading-relaxed" style={{ color: '#C4B5FD' }}>{event.detail}</p>
      )}

      {event.output_summary && event.output_summary !== event.detail && (
        <p className="text-xs mt-0.5 italic" style={{ color: '#6B6896' }}>{event.output_summary}</p>
      )}

      {event.rule_reference && (
        <span
          className="text-xs font-mono rounded px-1.5 py-0.5 mt-1 inline-block"
          style={{ background: 'rgba(124,92,252,0.15)', color: '#B8A9FF', border: '1px solid rgba(124,92,252,0.3)' }}
        >
          {event.rule_reference}
        </span>
      )}

      {event.error && (
        <p className="text-xs mt-1 rounded px-2 py-1 font-mono break-all" style={{ color: '#F87171', background: '#2D0A0A' }}>
          {event.error}
        </p>
      )}

      <ConfBar value={event.confidence} />
    </div>
  )
}

export default function TraceLog({ events = [], filterAgent = null, replayActive = false }) {
  const displayed = filterAgent ? events.filter((e) => e.agent === filterAgent) : events
  const agentLabel = filterAgent ? (AGENT_SHORT[filterAgent] || filterAgent) : null

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="px-3 py-2.5 border-b flex items-center justify-between shrink-0"
        style={{ borderColor: '#2A2550', background: '#141130' }}
      >
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#6B6896' }}>
          {agentLabel ? `${agentLabel} — trace` : 'Pipeline Trace'}
        </span>
        <div className="flex items-center gap-2">
          {replayActive && (
            <span className="flex items-center gap-1 text-xs" style={{ color: '#7C5CFC' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-plum-500 animate-pulse" style={{ background: '#7C5CFC' }} />
              live
            </span>
          )}
          <span className="text-xs" style={{ color: '#3A3568' }}>{displayed.length} events</span>
        </div>
      </div>

      {/* Event list */}
      <div className="flex-1 overflow-y-auto">
        {displayed.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2" style={{ color: '#3A3568' }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-7 h-7 opacity-40">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <span className="text-xs">{replayActive ? 'Waiting for events…' : 'Submit a claim to see the trace'}</span>
          </div>
        ) : (
          [...displayed].reverse().map((evt, i) => (
            <TraceEventRow key={`${evt.step_id}-${i}`} event={evt} isNew={i === 0 && replayActive} />
          ))
        )}
      </div>
    </div>
  )
}
