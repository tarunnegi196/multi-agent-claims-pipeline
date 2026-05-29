import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { listClaims } from '../api'

/* Plum exact brand colours */
const DECISION_META = {
  APPROVED:      { color: '#92bd33', bg: 'rgba(146,189,51,0.10)', border: 'rgba(146,189,51,0.25)', label: 'Approved'     },
  PARTIAL:       { color: '#ffbf21', bg: 'rgba(255,191,33,0.10)', border: 'rgba(255,191,33,0.25)', label: 'Partial'       },
  REJECTED:      { color: '#ff4052', bg: 'rgba(255,64,82,0.10)',  border: 'rgba(255,64,82,0.25)',  label: 'Rejected'      },
  MANUAL_REVIEW: { color: '#ffbf21', bg: 'rgba(255,191,33,0.10)', border: 'rgba(255,191,33,0.25)', label: 'Manual Review' },
}

function DecisionBadge({ type }) {
  if (!type) return (
    <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
      color: '#bea0b3', background: 'rgba(190,160,179,0.1)', border: '1px solid rgba(190,160,179,0.3)' }}>
      Halted
    </span>
  )
  const m = DECISION_META[type] || DECISION_META.MANUAL_REVIEW
  return (
    <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
      color: m.color, background: m.bg, border: `1px solid ${m.border}` }}>
      {m.label}
    </span>
  )
}

function ConfBar({ value }) {
  if (value == null) return <span style={{ color: '#9e708c', fontSize: 12 }}>—</span>
  const pct   = Math.round(value * 100)
  const color = pct >= 80 ? '#92bd33' : pct >= 50 ? '#ffbf21' : '#ff4052'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 60, background: '#340926', borderRadius: 99, height: 5 }}>
        <div style={{ width: `${pct}%`, background: color, height: 5, borderRadius: 99 }} />
      </div>
      <span style={{ fontSize: 11, fontFamily: 'monospace', color }}>{pct}%</span>
    </div>
  )
}

export default function HistoryPage() {
  const [claims,  setClaims]  = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [query,   setQuery]   = useState('')
  const navigate = useNavigate()

  const load = () => {
    setLoading(true)
    listClaims(100).then(setClaims).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }
  useEffect(load, [])

  // Client-side filter: search across claim_id, member_id, category, date, decision.
  const q = query.trim().toLowerCase()
  const filtered = q === '' ? claims : claims.filter((c) => (
    (c.claim_id        || '').toLowerCase().includes(q) ||
    (c.member_id       || '').toLowerCase().includes(q) ||
    (c.claim_category  || '').toLowerCase().includes(q) ||
    (c.treatment_date  || '').toLowerCase().includes(q) ||
    (c.decision_type   || '').toLowerCase().includes(q)
  ))

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 240, color: '#9e708c' }}>
      <svg style={{ animation: '0.8s linear infinite spin', width: 20, height: 20, marginRight: 8, color: '#7b4067' }}
        viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" strokeOpacity="0.25"/>
        <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z"/>
      </svg>
      Loading claims…
    </div>
  )

  const thStyle = { padding: '10px 16px', fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
    letterSpacing: '0.06em', color: '#9e708c', textAlign: 'left' }
  const thRStyle = { ...thStyle, textAlign: 'right' }

  return (
    <div className="plum-container" style={{ paddingTop: 32, paddingBottom: 32, fontFamily: 'Inter, Arial, sans-serif' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16, gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h4 style={{ color: '#d8c5d1', margin: 0, marginBottom: 4 }}>Claims History</h4>
          <p style={{ fontSize: 13, color: '#9e708c', margin: 0 }}>
            {q
              ? `${filtered.length} of ${claims.length} match "${query.trim()}"`
              : `${claims.length} claim${claims.length !== 1 ? 's' : ''} processed`}
          </p>
        </div>
        <button onClick={load} className="btn-action" style={{ fontFamily: 'Inter, Arial, sans-serif' }}>↻ Refresh</button>
      </div>

      {/* Search bar */}
      <div style={{ position: 'relative', marginBottom: 20 }}>
        <svg
          viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2"
          width="14" height="14"
          style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: '#7b5068', pointerEvents: 'none' }}
        >
          <circle cx="9" cy="9" r="6" />
          <path strokeLinecap="round" d="M14 14l4 4" />
        </svg>
        <input
          type="text"
          placeholder="Search by claim ID, employee ID, category, date or decision…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{
            width: '100%', padding: '10px 14px 10px 38px', fontSize: 13,
            background: '#11040d', border: '1px solid #340926', borderRadius: 10,
            color: '#d8c5d1', outline: 'none',
            fontFamily: 'Inter, Arial, sans-serif',
            transition: 'border-color 0.15s, box-shadow 0.15s',
          }}
          onFocus={(e) => { e.currentTarget.style.borderColor = '#7b4067'; e.currentTarget.style.boxShadow = '0 0 0 3px rgba(123,64,103,0.18)' }}
          onBlur={(e)  => { e.currentTarget.style.borderColor = '#340926'; e.currentTarget.style.boxShadow = 'none' }}
        />
        {query && (
          <button
            onClick={() => setQuery('')}
            title="Clear search"
            style={{
              position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
              background: 'rgba(70,9,50,0.4)', border: 'none', color: '#bea0b3',
              cursor: 'pointer', fontSize: 12, lineHeight: 1, padding: '4px 8px', borderRadius: 6,
            }}
          >
            ✕
          </button>
        )}
      </div>

      {error && (
        <div style={{ background: '#ffdddd', border: '1px solid #ff4052', borderRadius: 8, padding: '10px 14px',
          marginBottom: 20, fontSize: 13, color: '#ea384c' }}>
          {error}
        </div>
      )}

      {claims.length === 0 ? (
        <div style={{ textAlign: 'center', paddingTop: 80, color: '#9e708c' }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="48" height="48"
            style={{ margin: '0 auto 16px', display: 'block', opacity: 0.3 }}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          <p style={{ fontSize: 13 }}>No claims yet. Submit your first claim.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', paddingTop: 60, color: '#9e708c' }}>
          <p style={{ fontSize: 13 }}>
            No claims match "<span style={{ color: '#bea0b3' }}>{query}</span>". Try a different search term.
          </p>
        </div>
      ) : (
        <div style={{ border: '1px solid #340926', borderRadius: 16, overflow: 'hidden', background: '#11040d' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#1d0716', borderBottom: '1px solid #340926' }}>
                <th style={thStyle}>Claim ID</th>
                <th style={thStyle}>Member</th>
                <th style={thStyle}>Category</th>
                <th style={thStyle}>Date</th>
                <th style={thStyle}>Decision</th>
                <th style={thRStyle}>Claimed</th>
                <th style={thRStyle}>Approved</th>
                <th style={thStyle}>Confidence</th>
                <th style={thStyle}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c, idx) => (
                <tr key={c.claim_id} onClick={() => navigate(`/claims/${c.claim_id}`)}
                  style={{ borderBottom: '1px solid #2c0b21', cursor: 'pointer',
                    background: idx % 2 === 0 ? '#11040d' : '#1d0716',
                    transition: 'background-color 0.1s' }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = '#2c0b21' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = idx % 2 === 0 ? '#11040d' : '#1d0716' }}>
                  <td style={{ padding: '10px 16px' }}>
                    <span style={{ fontFamily: 'monospace', fontSize: 11, color: '#bea0b3' }}>{c.claim_id?.slice(0, 8)}…</span>
                  </td>
                  <td style={{ padding: '10px 16px', fontWeight: 700, color: '#d8c5d1' }}>{c.member_id}</td>
                  <td style={{ padding: '10px 16px', fontSize: 12, color: '#9e708c' }}>{c.claim_category}</td>
                  <td style={{ padding: '10px 16px', fontSize: 12, color: '#9e708c' }}>{c.treatment_date}</td>
                  <td style={{ padding: '10px 16px' }}><DecisionBadge type={c.decision_type} /></td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', color: '#bea0b3' }}>
                    ₹{Number(c.claimed_amount).toLocaleString('en-IN')}
                  </td>
                  <td style={{ padding: '10px 16px', textAlign: 'right' }}>
                    {c.approved_amount != null
                      ? <span style={{ fontWeight: 700, color: '#92bd33' }}>₹{Number(c.approved_amount).toLocaleString('en-IN')}</span>
                      : <span style={{ color: '#9e708c' }}>—</span>}
                  </td>
                  <td style={{ padding: '10px 16px' }}><ConfBar value={c.confidence} /></td>
                  <td style={{ padding: '10px 16px' }}>
                    <button onClick={(e) => { e.stopPropagation(); navigate(`/claims/${c.claim_id}`) }}
                      className="btn-action"
                      style={{ fontSize: 11, fontFamily: 'Inter, Arial, sans-serif' }}>
                      ↻ Replay
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
