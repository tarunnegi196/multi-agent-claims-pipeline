/* Plum exact brand colours */
const DECISION_META = {
  APPROVED:      { color: '#92bd33', bg: 'rgba(146,189,51,0.08)', border: 'rgba(146,189,51,0.25)', icon: '✓', label: 'Approved'     },
  PARTIAL:       { color: '#ffbf21', bg: 'rgba(255,191,33,0.08)', border: 'rgba(255,191,33,0.25)', icon: '◑', label: 'Partial'       },
  REJECTED:      { color: '#ff4052', bg: 'rgba(255,64,82,0.08)',  border: 'rgba(255,64,82,0.25)',  icon: '✕', label: 'Rejected'      },
  MANUAL_REVIEW: { color: '#ffbf21', bg: 'rgba(255,191,33,0.08)', border: 'rgba(255,191,33,0.25)', icon: '⚑', label: 'Manual Review' },
}

const fmt = (n) => n == null ? '—' : '₹' + Number(n).toLocaleString('en-IN')

function ConfidencePill({ value }) {
  const pct   = Math.round((value ?? 0) * 100)
  const color = pct >= 80 ? '#92bd33' : pct >= 50 ? '#ffbf21' : '#ff4052'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, background: '#340926', borderRadius: 99, height: 6 }}>
        <div style={{ width: `${pct}%`, background: color, height: 6, borderRadius: 99, transition: 'width 1s ease' }} />
      </div>
      <span style={{ fontSize: 11, fontFamily: 'monospace', fontWeight: 700, color, minWidth: 30, textAlign: 'right' }}>{pct}%</span>
    </div>
  )
}

function AmountRow({ label, value, isFinal = false, deduction = false }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between',
      fontSize: 13, padding: '4px 0',
      fontWeight: isFinal ? 700 : 400,
      borderTop: isFinal ? '1px solid #340926' : 'none',
      marginTop: isFinal ? 4 : 0,
      paddingTop: isFinal ? 8 : 4,
    }}>
      <span style={{ color: '#9e708c' }}>{label}</span>
      <span style={{ color: deduction ? '#ff4052' : isFinal ? '#92bd33' : '#d8c5d1' }}>
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

  const panelStyle = { background: 'rgba(0,0,0,0.25)', border: '1px solid #340926', borderRadius: 12, padding: 12, marginTop: 4 }

  return (
    <div style={{ background: meta.bg, border: `1.5px solid ${meta.border}`, borderRadius: 16,
      padding: 16, display: 'flex', flexDirection: 'column', gap: 14,
      animation: 'fade-in 0.2s ease-out both', fontFamily: 'Inter, Arial, sans-serif' }}>

      {/* Decision header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <span style={{ color: meta.color, background: `${meta.color}18`, border: `1px solid ${meta.border}`,
            borderRadius: 30, padding: '4px 14px', fontSize: 13, fontWeight: 700, display: 'inline-block' }}>
            {meta.icon} {meta.label}
          </span>
          <p style={{ fontSize: 11, color: '#9e708c', marginTop: 6 }}>
            {member_id} · {claim_category}
            {claim_id && <> · <span style={{ fontFamily: 'monospace' }}>{claim_id.slice(0, 8)}</span></>}
          </p>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: meta.color }}>{fmt(decision.approved_amount)}</div>
          <div style={{ fontSize: 11, color: '#9e708c' }}>of {fmt(decision.claimed_amount)} claimed</div>
        </div>
      </div>

      {/* Confidence */}
      <div>
        <div style={{ fontSize: 11, color: '#9e708c', marginBottom: 4 }}>Confidence</div>
        <ConfidencePill value={decision.confidence} />
      </div>

      {/* Amount breakdown */}
      {bd && (
        <div style={panelStyle}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#9e708c', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
            Amount Breakdown
          </div>
          <AmountRow label="Claimed" value={bd.claimed} />
          {bd.network_discount_amount > 0 && <>
            <AmountRow label={`Network discount (${bd.network_discount_percent}%)`} value={bd.network_discount_amount} deduction />
            <AmountRow label="After network discount" value={bd.after_network_discount} />
          </>}
          {bd.copay_amount > 0 && <AmountRow label={`Co-pay (${bd.copay_percent}%)`} value={bd.copay_amount} deduction />}
          {bd.sub_limit_applied    != null && <AmountRow label="Sub-limit applied"    value={bd.sub_limit_applied} />}
          {bd.per_claim_limit_applied != null && <AmountRow label="Per-claim limit"   value={bd.per_claim_limit_applied} />}
          <AmountRow label="Final approved" value={bd.final_approved} isFinal />
        </div>
      )}

      {/* Line items */}
      {decision.line_item_decisions?.length > 0 && (
        <div style={panelStyle}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#9e708c', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
            Line Items
          </div>
          {decision.line_item_decisions.map((li, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', fontSize: 13, gap: 8, padding: '4px 0' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                <span style={{ color: li.status === 'APPROVED' ? '#92bd33' : '#ff4052' }}>{li.status === 'APPROVED' ? '✓' : '✕'}</span>
                <span style={{ color: '#d8c5d1', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{li.description}</span>
              </div>
              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <div style={{ color: li.status === 'APPROVED' ? '#92bd33' : '#ff4052',
                  textDecoration: li.status !== 'APPROVED' ? 'line-through' : 'none' }}>
                  {fmt(li.claimed_amount)}
                </div>
                {li.reason && <div style={{ fontSize: 11, color: '#9e708c' }}>{li.reason}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Explanation */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#9e708c', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
          Explanation
        </div>
        <p style={{ fontSize: 13, color: '#d8c5d1', lineHeight: '18px', margin: 0 }}>{decision.explanation}</p>
      </div>

      {/* Rejection reasons */}
      {decision.rejection_reasons?.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {decision.rejection_reasons.map((r) => (
            <span key={r} style={{ fontSize: 11, fontFamily: 'monospace', padding: '2px 8px', borderRadius: 4,
              background: 'rgba(255,64,82,0.1)', color: '#ff4052', border: '1px solid rgba(255,64,82,0.3)' }}>
              {r}
            </span>
          ))}
        </div>
      )}

      {/* Fraud flags */}
      {decision.fraud_flags?.length > 0 && (
        <div style={{ background: 'rgba(255,191,33,0.06)', border: '1px solid rgba(255,191,33,0.3)', borderRadius: 12, padding: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#ffbf21', marginBottom: 6 }}>⚠ Fraud Signals</div>
          {decision.fraud_flags.map((f, i) => <div key={i} style={{ fontSize: 12, color: '#d8c5d1' }}>{f}</div>)}
        </div>
      )}

      {/* Degraded */}
      {degraded_components?.length > 0 && (
        <div style={{ background: 'rgba(255,191,33,0.06)', border: '1px solid rgba(255,191,33,0.3)', borderRadius: 12, padding: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#ffbf21', marginBottom: 4 }}>⚡ Degraded — pipeline continued</div>
          <div style={{ fontSize: 12, color: '#d8c5d1' }}>{degraded_components.join(', ')}</div>
          {decision.manual_review_note && <div style={{ fontSize: 12, color: '#ffbf21', marginTop: 4 }}>{decision.manual_review_note}</div>}
        </div>
      )}

      {/* Standalone manual review note */}
      {decision.manual_review_note && !degraded_components?.length && (
        <div style={{ fontSize: 12, background: 'rgba(255,191,33,0.08)', border: '1px solid rgba(255,191,33,0.3)',
          borderRadius: 8, padding: '8px 10px', color: '#ffbf21' }}>
          {decision.manual_review_note}
        </div>
      )}

      {/* Footer */}
      {processingMs != null && (
        <div style={{ fontSize: 11, textAlign: 'right', color: '#9e708c' }}>
          {(processingMs / 1000).toFixed(1)}s · {result.trace?.length ?? 0} trace events
        </div>
      )}
    </div>
  )
}
