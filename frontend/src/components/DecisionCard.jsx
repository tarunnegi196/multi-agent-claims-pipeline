const DECISION_META = {
  APPROVED:      { color: '#34d399', bg: '#022c22', border: '#065f46', icon: '✓', label: 'Approved'      },
  PARTIAL:       { color: '#FBBF24', bg: '#1C1400', border: '#78350F', icon: '◑', label: 'Partial'        },
  REJECTED:      { color: '#F87171', bg: '#2D0A0A', border: '#7F1D1D', icon: '✕', label: 'Rejected'       },
  MANUAL_REVIEW: { color: '#FB923C', bg: '#1C0800', border: '#7C2D12', icon: '⚑', label: 'Manual Review'  },
}

const fmt = (n) => n == null ? '—' : '₹' + Number(n).toLocaleString('en-IN')

function ConfidencePill({ value }) {
  const pct = Math.round((value ?? 0) * 100)
  const color = pct >= 80 ? '#34d399' : pct >= 50 ? '#FBBF24' : '#F87171'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 rounded-full h-1.5" style={{ background: '#2A2550' }}>
        <div style={{ width: `${pct}%`, background: color, transition: 'width 1s ease' }} className="h-1.5 rounded-full" />
      </div>
      <span style={{ color }} className="text-xs font-mono font-bold w-9 text-right">{pct}%</span>
    </div>
  )
}

function AmountRow({ label, value, isFinal = false, deduction = false }) {
  return (
    <div className={`flex justify-between text-sm py-1 ${isFinal ? 'font-bold border-t pt-2 mt-1' : ''}`}
      style={isFinal ? { borderColor: '#2A2550' } : {}}>
      <span style={{ color: '#8B87B5' }}>{label}</span>
      <span style={{ color: deduction ? '#F87171' : isFinal ? '#34d399' : '#F2F0FF' }}>
        {deduction && value > 0 ? '−' : ''}{fmt(value)}
      </span>
    </div>
  )
}

export default function DecisionCard({ result, processingMs }) {
  if (!result) return null
  const { decision, claim_id, member_id, claim_category, degraded_components } = result
  const meta = DECISION_META[decision.decision_type] || DECISION_META.MANUAL_REVIEW
  const bd   = decision.amount_breakdown

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-4 animate-fade-in"
      style={{ background: meta.bg, border: `1.5px solid ${meta.border}` }}
    >
      {/* Decision header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span
              className="text-sm font-bold px-3 py-1 rounded-full"
              style={{ color: meta.color, background: `${meta.color}18`, border: `1px solid ${meta.border}` }}
            >
              {meta.icon} {meta.label}
            </span>
          </div>
          <p className="text-xs" style={{ color: '#6B6896' }}>
            {member_id} · {claim_category}
            {claim_id && <> · <span className="font-mono">{claim_id.slice(0, 8)}</span></>}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-2xl font-bold" style={{ color: meta.color }}>{fmt(decision.approved_amount)}</div>
          <div className="text-xs" style={{ color: '#6B6896' }}>of {fmt(decision.claimed_amount)} claimed</div>
        </div>
      </div>

      {/* Confidence */}
      <div>
        <div className="text-xs mb-1" style={{ color: '#6B6896' }}>Confidence</div>
        <ConfidencePill value={decision.confidence} />
      </div>

      {/* Amount breakdown */}
      {bd && (
        <div className="rounded-xl p-3" style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid #2A2550' }}>
          <div className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: '#6B6896' }}>Amount Breakdown</div>
          <AmountRow label="Claimed"                                         value={bd.claimed} />
          {bd.network_discount_amount > 0 && <>
            <AmountRow label={`Network discount (${bd.network_discount_percent}%)`} value={bd.network_discount_amount} deduction />
            <AmountRow label="After network discount"                               value={bd.after_network_discount} />
          </>}
          {bd.copay_amount > 0 && (
            <AmountRow label={`Co-pay (${bd.copay_percent}%)`} value={bd.copay_amount} deduction />
          )}
          {bd.sub_limit_applied    != null && <AmountRow label="Sub-limit applied"    value={bd.sub_limit_applied} />}
          {bd.per_claim_limit_applied != null && <AmountRow label="Per-claim limit"   value={bd.per_claim_limit_applied} />}
          <AmountRow label="Final approved" value={bd.final_approved} isFinal />
        </div>
      )}

      {/* Line items (dental) */}
      {decision.line_item_decisions?.length > 0 && (
        <div className="rounded-xl p-3" style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid #2A2550' }}>
          <div className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: '#6B6896' }}>Line Items</div>
          {decision.line_item_decisions.map((li, i) => (
            <div key={i} className="flex items-start justify-between text-sm gap-2 py-1">
              <div className="flex items-center gap-2 min-w-0">
                <span style={{ color: li.status === 'APPROVED' ? '#34d399' : '#F87171' }}>
                  {li.status === 'APPROVED' ? '✓' : '✕'}
                </span>
                <span className="truncate" style={{ color: '#C4B5FD' }}>{li.description}</span>
              </div>
              <div className="text-right shrink-0">
                <div style={{ color: li.status === 'APPROVED' ? '#34d399' : '#F87171',
                  textDecoration: li.status !== 'APPROVED' ? 'line-through' : 'none' }}>
                  {fmt(li.claimed_amount)}
                </div>
                {li.reason && <div className="text-xs" style={{ color: '#6B6896' }}>{li.reason}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Explanation */}
      <div>
        <div className="text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: '#6B6896' }}>Explanation</div>
        <p className="text-sm leading-relaxed" style={{ color: '#E9E6FF' }}>{decision.explanation}</p>
      </div>

      {/* Rejection reasons */}
      {decision.rejection_reasons?.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {decision.rejection_reasons.map((r) => (
            <span key={r} className="text-xs font-mono px-2 py-0.5 rounded"
              style={{ background: '#2D0A0A', color: '#F87171', border: '1px solid #7F1D1D' }}>
              {r}
            </span>
          ))}
        </div>
      )}

      {/* Fraud flags */}
      {decision.fraud_flags?.length > 0 && (
        <div className="rounded-xl p-3" style={{ background: 'rgba(251,146,60,0.06)', border: '1px solid #7C2D12' }}>
          <div className="text-xs font-semibold mb-1.5" style={{ color: '#FB923C' }}>⚠ Fraud Signals</div>
          {decision.fraud_flags.map((f, i) => (
            <div key={i} className="text-xs" style={{ color: '#FED7AA' }}>{f}</div>
          ))}
        </div>
      )}

      {/* Degraded components */}
      {degraded_components?.length > 0 && (
        <div className="rounded-xl p-3" style={{ background: 'rgba(251,191,36,0.05)', border: '1px solid #78350F' }}>
          <div className="text-xs font-semibold mb-1" style={{ color: '#FBBF24' }}>⚡ Degraded — pipeline continued with partial state</div>
          <div className="text-xs" style={{ color: '#FDE68A' }}>{degraded_components.join(', ')}</div>
          {decision.manual_review_note && (
            <div className="text-xs mt-1" style={{ color: '#FBBF24' }}>{decision.manual_review_note}</div>
          )}
        </div>
      )}

      {/* Standalone manual review note */}
      {decision.manual_review_note && !degraded_components?.length && (
        <div className="text-xs rounded-lg p-2.5" style={{ background: 'rgba(251,146,60,0.08)', border: '1px solid #7C2D12', color: '#FB923C' }}>
          {decision.manual_review_note}
        </div>
      )}

      {/* Footer */}
      {processingMs != null && (
        <div className="text-xs text-right" style={{ color: '#3A3568' }}>
          {(processingMs / 1000).toFixed(1)}s · {result.trace?.length ?? 0} trace events
        </div>
      )}
    </div>
  )
}
