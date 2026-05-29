import { useState } from 'react'
import DocumentRegionViewer from './DocumentRegionViewer'
import { downloadClaimReport } from '../api'

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

export default function DecisionCard({ result, processingMs, onNewClaim }) {
  const [regionViewer, setRegionViewer] = useState(null) // {fileId, docType, fileName}
  const [downloading, setDownloading]   = useState(false)
  const [dlError, setDlError]           = useState(null)

  if (!result) return null
  const { decision, claim_id, member_id, claim_category, degraded_components, documents } = result
  const meta = DECISION_META[decision.decision_type] || DECISION_META.MANUAL_REVIEW
  const bd   = decision.amount_breakdown

  async function handleDownload() {
    if (!claim_id) return
    setDownloading(true); setDlError(null)
    try { await downloadClaimReport(claim_id) }
    catch (err) { setDlError(err.message) }
    finally    { setDownloading(false) }
  }

  const panelStyle = { background: 'rgba(0,0,0,0.25)', border: '1px solid #340926', borderRadius: 12, padding: 12, marginTop: 4 }

  return (
    <div style={{ background: meta.bg, border: `1.5px solid ${meta.border}`, borderRadius: 16,
      padding: 16, display: 'flex', flexDirection: 'column', gap: 14,
      animation: 'fade-in 0.2s ease-out both', fontFamily: 'Inter, Arial, sans-serif' }}>

      {/* Top action bar — compact back arrow + download, always visible */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {onNewClaim && (
          <button
            onClick={onNewClaim}
            title="Back to claim form"
            style={{
              flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 34, height: 34, borderRadius: '50%',
              background: 'rgba(190,160,179,0.10)', border: '1px solid #460932',
              color: '#bea0b3', cursor: 'pointer',
              transition: 'background 0.12s, color 0.12s, border-color 0.12s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(190,160,179,0.20)'; e.currentTarget.style.color = '#e8d8e4'; e.currentTarget.style.borderColor = '#7b4067' }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(190,160,179,0.10)'; e.currentTarget.style.color = '#bea0b3'; e.currentTarget.style.borderColor = '#460932' }}
          >
            <svg viewBox="0 0 20 20" fill="currentColor" width="15" height="15">
              <path fillRule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clipRule="evenodd"/>
            </svg>
          </button>
        )}
        {claim_id && (
          <button
            onClick={handleDownload}
            disabled={downloading}
            title="Download the full PDF report"
            style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: 8, height: 34, padding: '0 14px', borderRadius: 30,
              background: downloading ? 'rgba(146,189,51,0.22)' : 'rgba(146,189,51,0.14)',
              border: '1px solid rgba(146,189,51,0.45)',
              color: '#92bd33', fontSize: 12.5, fontWeight: 700, cursor: downloading ? 'wait' : 'pointer',
              transition: 'background 0.12s',
              fontFamily: 'Inter, Arial, sans-serif',
            }}
            onMouseEnter={(e) => { if (!downloading) e.currentTarget.style.background = 'rgba(146,189,51,0.24)' }}
            onMouseLeave={(e) => { if (!downloading) e.currentTarget.style.background = 'rgba(146,189,51,0.14)' }}
          >
            {downloading ? (
              <>
                <svg style={{ animation: '0.8s linear infinite spin', width: 13, height: 13 }} viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" strokeOpacity="0.25"/>
                  <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z"/>
                </svg>
                Preparing PDF…
              </>
            ) : (
              <>
                <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14">
                  <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm6.293-14.707a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414-1.414l3-3z" clipRule="evenodd" transform="rotate(180 10 10)"/>
                </svg>
                Download PDF Report
              </>
            )}
          </button>
        )}
      </div>
      {dlError && (
        <p style={{ fontSize: 11, color: '#ff4052', margin: '-6px 0 0', textAlign: 'center' }}>
          {dlError}
        </p>
      )}

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

      {/* Narrative — LLM-synthesised summary */}
      {decision.narrative && (
        <div style={{
          background: 'linear-gradient(135deg, rgba(123,64,103,0.10), rgba(70,9,50,0.20))',
          border: '1px solid rgba(190,160,179,0.25)',
          borderRadius: 12, padding: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <span style={{
              background: '#570e40', color: '#fff', borderRadius: 4,
              padding: '1px 7px', fontSize: 9, fontWeight: 800, letterSpacing: 0.5,
            }}>AI</span>
            <span style={{ fontSize: 11, fontWeight: 700, color: '#bea0b3', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Summary
            </span>
          </div>
          <p style={{ fontSize: 13, color: '#d8c5d1', lineHeight: '19px', margin: 0 }}>
            {decision.narrative}
          </p>
        </div>
      )}

      {/* Next best actions */}
      {decision.next_best_actions?.length > 0 && (
        <div style={panelStyle}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#9e708c', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Next Best Action{decision.next_best_actions.length > 1 ? 's' : ''}
          </div>
          <ol style={{ margin: 0, paddingLeft: 0, listStyle: 'none' }}>
            {decision.next_best_actions.map((action, i) => (
              <li key={i} style={{
                display: 'flex', alignItems: 'flex-start', gap: 8,
                fontSize: 13, color: '#d8c5d1', lineHeight: '18px',
                padding: '6px 0',
                borderTop: i === 0 ? 'none' : '1px solid rgba(70,9,50,0.6)',
              }}>
                <span style={{
                  flexShrink: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: 20, height: 20, borderRadius: '50%',
                  background: meta.color + '22', color: meta.color,
                  fontSize: 11, fontWeight: 800, marginTop: 1,
                }}>{i + 1}</span>
                <span>{action}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Confidence reasoning */}
      {decision.confidence_reasoning && (
        <div style={{
          background: 'rgba(0,0,0,0.18)', border: '1px solid #340926',
          borderRadius: 10, padding: '10px 12px',
        }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#9e708c', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
            Why this confidence
          </div>
          <p style={{ fontSize: 12, color: '#bea0b3', lineHeight: '16px', margin: 0, fontStyle: 'italic' }}>
            {decision.confidence_reasoning}
          </p>
        </div>
      )}

      {/* Explanation (policy engine output) */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#9e708c', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
          Policy Reasoning
        </div>
        <p style={{ fontSize: 13, color: '#d8c5d1', lineHeight: '18px', margin: 0 }}>{decision.explanation}</p>
      </div>

      {/* Cross-document consistency flags */}
      {decision.consistency_flags?.length > 0 && (
        <div style={{ background: 'rgba(255,191,33,0.06)', border: '1px solid rgba(255,191,33,0.3)', borderRadius: 12, padding: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#ffbf21', marginBottom: 6 }}>⚐ Cross-Document Signals</div>
          {decision.consistency_flags.map((f, i) => (
            <div key={i} style={{ fontSize: 12, color: '#d8c5d1', paddingLeft: 14, position: 'relative' }}>
              <span style={{ position: 'absolute', left: 0, top: 0, color: '#ffbf21' }}>•</span>
              {f}
            </div>
          ))}
        </div>
      )}

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

      {/* Documents processed — "View regions" only for real uploaded files */}
      {documents?.length > 0 && (
        <div style={panelStyle}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#9e708c',
            textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Documents Processed
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {documents.map((doc) => {
              const qualityColor = doc.quality === 'UNREADABLE' ? '#ff4052'
                : doc.quality === 'DEGRADED' ? '#ffbf21' : '#92bd33'
              const qualityBg = doc.quality === 'UNREADABLE' ? 'rgba(255,64,82,0.1)'
                : doc.quality === 'DEGRADED' ? 'rgba(255,191,33,0.1)' : 'rgba(146,189,51,0.1)'
              return (
                <div key={doc.file_id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <div style={{ minWidth: 0, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                    {/* doc type */}
                    <span style={{
                      fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
                      background: 'rgba(190,160,179,0.1)', border: '1px solid #460932',
                      color: '#bea0b3', textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap',
                    }}>
                      {doc.doc_type}
                    </span>
                    {/* quality badge — only shown for real uploaded files */}
                    {doc.viewable && (
                      <span style={{
                        fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
                        background: qualityBg, border: `1px solid ${qualityColor}44`,
                        color: qualityColor, whiteSpace: 'nowrap',
                      }}>
                        {doc.quality || 'GOOD'}
                      </span>
                    )}
                    <span style={{ fontSize: 11, color: '#9e708c', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {doc.file_name}
                    </span>
                  </div>

                  {doc.viewable ? (
                    <button
                      onClick={() => setRegionViewer({ fileId: doc.file_id, docType: doc.doc_type, fileName: doc.file_name })}
                      title="View extracted regions in this document"
                      style={{
                        flexShrink: 0, display: 'flex', alignItems: 'center', gap: 4,
                        background: 'rgba(74,144,226,0.08)', border: '1px solid rgba(74,144,226,0.28)',
                        borderRadius: 99, padding: '3px 10px', cursor: 'pointer',
                        fontSize: 10, fontWeight: 700, color: '#4a90e2',
                        transition: 'background 0.1s, border-color 0.1s',
                        fontFamily: 'Inter, Arial, sans-serif', whiteSpace: 'nowrap',
                      }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(74,144,226,0.18)'; e.currentTarget.style.borderColor = 'rgba(74,144,226,0.55)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(74,144,226,0.08)'; e.currentTarget.style.borderColor = 'rgba(74,144,226,0.28)' }}
                    >
                      &#9681; Regions
                    </button>
                  ) : (
                    <span style={{ fontSize: 10, color: '#340926', flexShrink: 0 }}>stub</span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Footer */}
      {processingMs != null && (
        <div style={{ fontSize: 11, textAlign: 'right', color: '#9e708c' }}>
          {(processingMs / 1000).toFixed(1)}s · {result.trace?.length ?? 0} trace events
        </div>
      )}

      {/* Region viewer — opened on user request, tied to this claim's processed documents */}
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
