import { useNavigate } from 'react-router-dom'

const EVAL_REPORT = [
  { case_id:'TC001', case_name:'Wrong Document Uploaded',           matched:true, match_reason:'pipeline halted as expected', halt:true, halt_message:"Your CONSULTATION claim requires: HOSPITAL_BILL, PRESCRIPTION. Uploaded: PRESCRIPTION × 2. Missing: HOSPITAL_BILL.", expected_decision:null, actual_decision:null, approved_amount:null, confidence:null, rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:7,  claim_id:'EVAL-TC001-d86ba4' },
  { case_id:'TC002', case_name:'Unreadable Document',               matched:true, match_reason:'pipeline halted as expected', halt:true, halt_message:"'blurry_bill.jpg' (PHARMACY_BILL) could not be read. Please re-upload a clear, well-lit photo.", expected_decision:null, actual_decision:null, approved_amount:null, confidence:null, rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:6,  claim_id:'EVAL-TC002-f6a96c' },
  { case_id:'TC003', case_name:'Documents from Different Patients', matched:true, match_reason:'pipeline halted as expected', halt:true, halt_message:"Documents belong to different patients: PRESCRIPTION → 'Rajesh Kumar'; HOSPITAL_BILL → 'Arjun Mehta'.", expected_decision:null, actual_decision:null, approved_amount:null, confidence:null, rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:10, claim_id:'EVAL-TC003-45fd77' },
  { case_id:'TC004', case_name:'Clean Consultation – Full Approval',matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'APPROVED',      actual_decision:'APPROVED',      approved_amount:1350,  confidence:0.90, rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:28, claim_id:'EVAL-TC004-2662a6' },
  { case_id:'TC005', case_name:'Waiting Period – Diabetes',         matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'REJECTED',      actual_decision:'REJECTED',      approved_amount:0,     confidence:0.95, rejection_reasons:['WAITING_PERIOD'],    fraud_flags:[], degraded_components:[], trace_steps:24, claim_id:'EVAL-TC005-cd5fee' },
  { case_id:'TC006', case_name:'Dental Partial – Cosmetic Excluded',matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'PARTIAL',       actual_decision:'PARTIAL',       approved_amount:8000,  confidence:0.90, rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:27, claim_id:'EVAL-TC006-074b70' },
  { case_id:'TC007', case_name:'MRI Without Pre-Authorization',     matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'REJECTED',      actual_decision:'REJECTED',      approved_amount:0,     confidence:0.95, rejection_reasons:['PRE_AUTH_MISSING'],  fraud_flags:[], degraded_components:[], trace_steps:27, claim_id:'EVAL-TC007-c7752b' },
  { case_id:'TC008', case_name:'Per-Claim Limit Exceeded',          matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'REJECTED',      actual_decision:'REJECTED',      approved_amount:0,     confidence:0.95, rejection_reasons:['PER_CLAIM_EXCEEDED'],fraud_flags:[], degraded_components:[], trace_steps:22, claim_id:'EVAL-TC008-3b6314' },
  { case_id:'TC009', case_name:'Fraud – Multiple Same-Day Claims',  matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'MANUAL_REVIEW', actual_decision:'MANUAL_REVIEW', approved_amount:0,     confidence:0.70, rejection_reasons:[], fraud_flags:['SAME_DAY_CLAIMS: 4 on 2024-10-30 (limit: 2)'], degraded_components:[], trace_steps:26, claim_id:'EVAL-TC009-dde0ba' },
  { case_id:'TC010', case_name:'Network Hospital Discount',         matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'APPROVED',      actual_decision:'APPROVED',      approved_amount:3240,  confidence:0.90, rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:28, claim_id:'EVAL-TC010-32f967' },
  { case_id:'TC011', case_name:'Component Failure – Graceful Degradation',matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'APPROVED', actual_decision:'APPROVED', approved_amount:4000, confidence:0.297, rejection_reasons:[], fraud_flags:[], degraded_components:['ExtractionAgent(degraded)','ExtractionAgent(degraded)'], trace_steps:29, claim_id:'EVAL-TC011-0ac86a' },
  { case_id:'TC012', case_name:'Excluded Treatment (Bariatric)',    matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'REJECTED',      actual_decision:'REJECTED',      approved_amount:0,     confidence:0.92, rejection_reasons:['EXCLUDED_CONDITION'],fraud_flags:[], degraded_components:[], trace_steps:21, claim_id:'EVAL-TC012-f8fb52' },
]

const DEC_COLOR = { APPROVED:'#92bd33', PARTIAL:'#ffbf21', REJECTED:'#ff4052', MANUAL_REVIEW:'#ffbf21', HALT:'#bea0b3' }

function Tag({ text, color }) {
  return (
    <span style={{ fontSize: 11, fontFamily: 'monospace', padding: '1px 6px', borderRadius: 4,
      color, background: `${color}12`, border: `1px solid ${color}44` }}>
      {text}
    </span>
  )
}

export default function EvalPage() {
  const navigate = useNavigate()
  const passed   = EVAL_REPORT.filter((t) => t.matched).length
  const totalEvt = EVAL_REPORT.reduce((s, t) => s + t.trace_steps, 0)
  const confs    = EVAL_REPORT.filter((t) => t.confidence != null)
  const avgPct   = Math.round(confs.reduce((s, t) => s + t.confidence, 0) / confs.length * 100)

  const cardStyle = { background: '#1d0716', border: '1px solid #2c0b21', borderRadius: 16, padding: 20, transition: 'border-color 0.15s' }

  return (
    <div className="plum-container" style={{ paddingTop: 32, paddingBottom: 32, fontFamily: 'Inter, Arial, sans-serif' }}>

      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h4 style={{ color: '#d8c5d1', margin: 0, marginBottom: 6 }}>Eval Report</h4>
        <p style={{ fontSize: 13, color: '#9e708c', margin: 0 }}>
          All 12 test cases from{' '}
          <code style={{ fontSize: 11, padding: '1px 6px', borderRadius: 4,
            background: 'rgba(123,64,103,0.15)', color: '#bea0b3', border: '1px solid #570e40',
            fontFamily: 'monospace' }}>test_cases.json</code>{' '}
          run through the full pipeline.
        </p>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 32 }}>
        {[
          { value: `${passed}/${EVAL_REPORT.length}`, label: 'Test cases passed', color: '#92bd33' },
          { value: '100%',   label: 'Pass rate',          color: '#92bd33'  },
          { value: totalEvt, label: 'Total trace events',  color: '#bea0b3'  },
          { value: `${avgPct}%`, label: 'Avg confidence',  color: '#ffbf21'  },
        ].map(({ value, label, color }) => (
          <div key={label} style={cardStyle}>
            <div style={{ fontSize: 28, fontWeight: 800, color, marginBottom: 4 }}>{value}</div>
            <div style={{ fontSize: 12, color: '#9e708c' }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {EVAL_REPORT.map((tc) => {
          const dec      = tc.halt ? 'HALT' : (tc.actual_decision || '—')
          const decColor = DEC_COLOR[dec] || '#9e708c'

          return (
            <div key={tc.case_id} style={{ ...cardStyle, cursor: 'default' }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#570e40' }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#2c0b21' }}>

              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12 }}>

                {/* Pass + case id */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  <span style={{ width: 20, height: 20, borderRadius: '50%', display: 'flex',
                    alignItems: 'center', justifyContent: 'center', fontSize: 11,
                    background: 'rgba(146,189,51,0.1)', border: '1.5px solid #92bd33', color: '#92bd33' }}>
                    ✓
                  </span>
                  <code style={{ fontSize: 11, padding: '1px 8px', borderRadius: 4,
                    background: 'rgba(123,64,103,0.15)', color: '#bea0b3', border: '1px solid #570e40',
                    fontFamily: 'monospace' }}>
                    {tc.case_id}
                  </code>
                </div>

                {/* Name */}
                <div style={{ flex: 1, minWidth: 180 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: '#d8c5d1' }}>{tc.case_name}</div>
                  <div style={{ fontSize: 11, color: '#9e708c', marginTop: 2 }}>{tc.match_reason}</div>
                </div>

                {/* Decision badge */}
                <div style={{ flexShrink: 0, textAlign: 'right' }}>
                  <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 12px', borderRadius: 30,
                    color: decColor, background: `${decColor}12`, border: `1px solid ${decColor}44` }}>
                    {dec}
                  </span>
                  {tc.approved_amount != null && !tc.halt && (
                    <div style={{ fontSize: 11, marginTop: 4, color: decColor }}>
                      ₹{Number(tc.approved_amount).toLocaleString('en-IN')}
                    </div>
                  )}
                </div>

                {/* Confidence */}
                <div style={{ flexShrink: 0, width: 110 }}>
                  {tc.confidence != null ? (
                    <div>
                      <div style={{ fontSize: 11, color: '#9e708c', marginBottom: 4 }}>Confidence</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ flex: 1, background: '#340926', borderRadius: 99, height: 5 }}>
                          <div style={{
                            width: `${Math.round(tc.confidence * 100)}%`,
                            background: tc.confidence >= 0.8 ? '#92bd33' : tc.confidence >= 0.5 ? '#ffbf21' : '#ff4052',
                            height: 5, borderRadius: 99,
                          }} />
                        </div>
                        <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#9e708c' }}>
                          {Math.round(tc.confidence * 100)}%
                        </span>
                      </div>
                    </div>
                  ) : <span style={{ fontSize: 11, color: '#9e708c' }}>—</span>}
                </div>

                {/* Events */}
                <div style={{ flexShrink: 0, textAlign: 'center', width: 52 }}>
                  <div style={{ fontSize: 11, color: '#9e708c' }}>Events</div>
                  <div style={{ fontSize: 13, fontFamily: 'monospace', color: '#bea0b3' }}>{tc.trace_steps}</div>
                </div>

                {/* Replay */}
                <button onClick={() => navigate(`/claims/${tc.claim_id}`)}
                  className="btn-action"
                  style={{ flexShrink: 0, fontSize: 11, fontFamily: 'Inter, Arial, sans-serif' }}>
                  ↻ Replay
                </button>
              </div>

              {/* Gate message */}
              {tc.halt_message && (
                <div style={{ marginTop: 10, padding: '8px 12px', borderRadius: 8, fontSize: 12, lineHeight: '16px',
                  background: 'rgba(123,64,103,0.08)', border: '1px solid #570e40', color: '#d8c5d1' }}>
                  <span style={{ fontWeight: 700, color: '#bea0b3' }}>Gate: </span>{tc.halt_message}
                </div>
              )}

              {/* Tags */}
              {(tc.rejection_reasons?.length > 0 || tc.fraud_flags?.length > 0 || tc.degraded_components?.length > 0) && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                  {tc.rejection_reasons.map((r) => <Tag key={r} text={r} color="#ff4052" />)}
                  {tc.fraud_flags.map((f)       => <Tag key={f} text={f} color="#ffbf21" />)}
                  {tc.degraded_components.map((d) => <Tag key={d} text={d} color="#ffbf21" />)}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer notes */}
      <div style={{ ...cardStyle, marginTop: 24 }}>
        <h5 style={{ color: '#d8c5d1', margin: '0 0 12px' }}>Notes</h5>
        <ul style={{ fontSize: 13, color: '#9e708c', margin: 0, paddingLeft: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <li>• <strong style={{ color: '#bea0b3' }}>TC001–TC003</strong> test early doc detection. Gate fires before any LLM extraction.</li>
          <li>• <strong style={{ color: '#bea0b3' }}>TC010</strong> tests calculation order: network discount applied before co-pay (₹4,500 → ₹3,600 → ₹3,240).</li>
          <li>• <strong style={{ color: '#bea0b3' }}>TC011</strong> tests graceful degradation — pipeline continues at confidence 0.297 after component failure.</li>
          <li>• Click <strong style={{ color: '#bea0b3' }}>↻ Replay</strong> on any case to animate its trace in the pipeline graph.</li>
        </ul>
      </div>
    </div>
  )
}
