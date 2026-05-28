import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { listClaims } from '../api'

const DECISION_META = {
  APPROVED:      { color: '#34d399', bg: '#022c22', border: '#065f46', label: 'Approved'      },
  PARTIAL:       { color: '#FBBF24', bg: '#1C1400', border: '#78350F', label: 'Partial'        },
  REJECTED:      { color: '#F87171', bg: '#2D0A0A', border: '#7F1D1D', label: 'Rejected'       },
  MANUAL_REVIEW: { color: '#FB923C', bg: '#1C0800', border: '#7C2D12', label: 'Manual Review'  },
}

function DecisionBadge({ type }) {
  if (!type) {
    return (
      <span className="text-xs font-bold px-2 py-0.5 rounded"
        style={{ color: '#9B82FD', background: 'rgba(124,92,252,0.12)', border: '1px solid rgba(124,92,252,0.3)' }}>
        Halted
      </span>
    )
  }
  const m = DECISION_META[type] || DECISION_META.MANUAL_REVIEW
  return (
    <span className="text-xs font-bold px-2 py-0.5 rounded"
      style={{ color: m.color, background: m.bg, border: `1px solid ${m.border}` }}>
      {m.label}
    </span>
  )
}

function ConfBar({ value }) {
  if (value == null) return <span className="text-xs" style={{ color: '#3A3568' }}>—</span>
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? '#34d399' : pct >= 50 ? '#FBBF24' : '#F87171'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 rounded-full h-1.5" style={{ background: '#2A2550' }}>
        <div style={{ width: `${pct}%`, background: color }} className="h-1.5 rounded-full" />
      </div>
      <span className="text-xs font-mono" style={{ color }}>{pct}%</span>
    </div>
  )
}

export default function HistoryPage() {
  const [claims,  setClaims]  = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const navigate = useNavigate()

  const load = () => {
    setLoading(true)
    listClaims(100)
      .then(setClaims)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64" style={{ color: '#6B6896' }}>
        <svg className="animate-spin w-5 h-5 mr-2" viewBox="0 0 24 24" fill="none" style={{ color: '#7C5CFC' }}>
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z" />
        </svg>
        Loading claims…
      </div>
    )
  }

  return (
    <div className="max-w-screen-xl mx-auto px-6 py-8">

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold" style={{ color: '#F2F0FF' }}>Claims History</h1>
          <p className="text-sm mt-1" style={{ color: '#6B6896' }}>
            {claims.length} claim{claims.length !== 1 ? 's' : ''} processed
          </p>
        </div>
        <button
          onClick={load}
          className="text-sm px-4 py-2 rounded-xl border transition-all"
          style={{ background: 'rgba(124,92,252,0.08)', borderColor: 'rgba(124,92,252,0.3)', color: '#B8A9FF' }}
        >
          ↻ Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-xl p-4 mb-6 text-sm border" style={{ background: '#2D0A0A', borderColor: '#7F1D1D', color: '#F87171' }}>
          {error}
        </div>
      )}

      {claims.length === 0 ? (
        <div className="text-center py-20" style={{ color: '#3A3568' }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-12 h-12 mx-auto mb-4 opacity-30">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          <p className="text-sm">No claims yet. Submit your first claim.</p>
        </div>
      ) : (
        <div className="rounded-2xl border overflow-hidden" style={{ borderColor: '#2A2550' }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: '#141130', borderBottom: '1px solid #2A2550' }}>
                {['Claim ID','Member','Category','Date','Decision','Claimed','Approved','Confidence',''].map((h) => (
                  <th key={h}
                    className={`px-4 py-3 text-xs font-semibold uppercase tracking-wider ${h === 'Claimed' || h === 'Approved' ? 'text-right' : 'text-left'}`}
                    style={{ color: '#6B6896' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {claims.map((c, idx) => (
                <tr
                  key={c.claim_id}
                  onClick={() => navigate(`/claims/${c.claim_id}`)}
                  className="cursor-pointer transition-colors"
                  style={{
                    borderBottom: '1px solid #1D1840',
                    background: idx % 2 === 0 ? '#0C0A1C' : '#0E0C22',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(124,92,252,0.05)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = idx % 2 === 0 ? '#0C0A1C' : '#0E0C22' }}
                >
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs" style={{ color: '#6B6896' }}>{c.claim_id?.slice(0, 8)}…</span>
                  </td>
                  <td className="px-4 py-3 font-semibold" style={{ color: '#E9E6FF' }}>{c.member_id}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#9491C0' }}>{c.claim_category}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#6B6896' }}>{c.treatment_date}</td>
                  <td className="px-4 py-3"><DecisionBadge type={c.decision_type} /></td>
                  <td className="px-4 py-3 text-right" style={{ color: '#C4B5FD' }}>
                    ₹{Number(c.claimed_amount).toLocaleString('en-IN')}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {c.approved_amount != null
                      ? <span className="font-semibold" style={{ color: '#34d399' }}>₹{Number(c.approved_amount).toLocaleString('en-IN')}</span>
                      : <span style={{ color: '#3A3568' }}>—</span>
                    }
                  </td>
                  <td className="px-4 py-3"><ConfBar value={c.confidence} /></td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={(e) => { e.stopPropagation(); navigate(`/claims/${c.claim_id}`) }}
                      className="text-xs px-2.5 py-1 rounded-lg border transition-all"
                      style={{ color: '#9B82FD', borderColor: 'rgba(124,92,252,0.35)', background: 'rgba(124,92,252,0.08)' }}
                    >
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
