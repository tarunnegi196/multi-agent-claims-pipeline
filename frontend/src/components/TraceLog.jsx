/* Plum exact brand colours */
const STATUS_META = {
  PASS: { color: '#92bd33', bg: 'rgba(146,189,51,0.10)', label: 'PASS' },
  FAIL: { color: '#ff4052', bg: 'rgba(255,64,82,0.10)',  label: 'FAIL' },
  WARN: { color: '#ffbf21', bg: 'rgba(255,191,33,0.10)', label: 'WARN' },
  SKIP: { color: '#9e708c', bg: 'rgba(158,112,140,0.10)',label: 'SKIP' },
}

const AGENT_SHORT = {
  IntakeAgent:           'Intake',
  DocClassifierAgent:    'Classifier',
  DocVerifierAgent:      'Verifier',
  ExtractionAgent:       'Extractor',
  FraudScreenAgent:      'Fraud',
  DecisionComposerAgent: 'Composer',
}

const AGENT_COLOR = {
  IntakeAgent:           '#bea0b3',
  DocClassifierAgent:    '#d8c5d1',
  DocVerifierAgent:      '#9e708c',
  ExtractionAgent:       '#7b4067',
  FraudScreenAgent:      '#ffbf21',
  DecisionComposerAgent: '#ff4052',
}

function StatusBadge({ status }) {
  const m = STATUS_META[status] || STATUS_META.SKIP
  return (
    <span style={{ background: m.bg, color: m.color, border: `1px solid ${m.color}44`,
      fontSize: 11, fontWeight: 700, padding: '1px 6px', borderRadius: 4, fontFamily: 'monospace',
      flexShrink: 0, letterSpacing: '0.02em' }}>
      {m.label}
    </span>
  )
}

function ConfBar({ value }) {
  if (value == null) return null
  const pct   = Math.round(value * 100)
  const color = pct >= 80 ? '#92bd33' : pct >= 50 ? '#ffbf21' : '#ff4052'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
      <div style={{ flex: 1, background: '#340926', borderRadius: 99, height: 4 }}>
        <div style={{ width: `${pct}%`, background: color, height: 4, borderRadius: 99, transition: 'width 0.5s' }} />
      </div>
      <span style={{ fontSize: 11, fontFamily: 'monospace', color }}>{pct}%</span>
    </div>
  )
}

function TraceEventRow({ event, isNew }) {
  const agentShort = AGENT_SHORT[event.agent] || event.agent
  const agentColor = AGENT_COLOR[event.agent] || '#bea0b3'
  return (
    <div style={{
      padding: '10px 12px',
      borderBottom: '1px solid #340926',
      background: isNew ? 'rgba(255,64,82,0.06)' : 'rgba(0,0,0,0.15)',
      transition: 'background-color 0.4s cubic-bezier(0.47, 0, 0.745, 0.715)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, flexWrap: 'nowrap' }}>
        <StatusBadge status={event.status} />
        <span style={{ fontSize: 11, fontWeight: 700, color: agentColor, flexShrink: 0 }}>{agentShort}</span>
        <span style={{ fontSize: 11, color: '#9e708c', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
          {event.step_id}
        </span>
        {event.duration_ms != null && (
          <span style={{ fontSize: 11, color: '#9e708c', flexShrink: 0 }}>{event.duration_ms}ms</span>
        )}
      </div>

      {event.detail && (
        <p style={{ fontSize: 12, color: '#d8c5d1', lineHeight: '16px', margin: '2px 0 0' }}>{event.detail}</p>
      )}
      {event.output_summary && event.output_summary !== event.detail && (
        <p style={{ fontSize: 11, color: '#9e708c', fontStyle: 'italic', margin: '2px 0 0' }}>{event.output_summary}</p>
      )}
      {event.rule_reference && (
        <span style={{ fontSize: 11, fontFamily: 'monospace', padding: '1px 6px', borderRadius: 4,
          background: 'rgba(123,64,103,0.15)', color: '#bea0b3', border: '1px solid #570e40',
          display: 'inline-block', marginTop: 4 }}>
          {event.rule_reference}
        </span>
      )}
      {event.error && (
        <p style={{ fontSize: 11, fontFamily: 'monospace', marginTop: 4, padding: '3px 8px',
          background: '#ffdddd', color: '#ea384c', borderRadius: 4, wordBreak: 'break-all' }}>
          {event.error}
        </p>
      )}
      <ConfBar value={event.confidence} />
    </div>
  )
}

export default function TraceLog({ events = [], filterAgent = null, replayActive = false }) {
  const displayed  = filterAgent ? events.filter((e) => e.agent === filterAgent) : events
  const agentLabel = filterAgent ? (AGENT_SHORT[filterAgent] || filterAgent) : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#2c0b21', borderLeft: '2px solid #460932' }}>
      {/* Header */}
      <div style={{ padding: '10px 14px', borderBottom: '1px solid #460932', background: '#340926',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: '#9e708c', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {agentLabel ? `${agentLabel} — trace` : 'Pipeline Trace'}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {replayActive && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#bea0b3' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#92bd33',
                animation: 'api-glow 1s ease-in-out infinite', display: 'inline-block' }} />
              live
            </span>
          )}
          <span style={{ fontSize: 11, color: '#7b5068' }}>{displayed.length} events</span>
        </div>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', background: '#2c0b21' }}>
        {displayed.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            height: 120, gap: 8, color: '#9e708c' }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="28" height="28" style={{ opacity: 0.4 }}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <span style={{ fontSize: 12 }}>{replayActive ? 'Waiting for events…' : 'Submit a claim to see the trace'}</span>
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
