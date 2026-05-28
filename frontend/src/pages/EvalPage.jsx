import { useNavigate } from 'react-router-dom'

const EVAL_REPORT = [
  { case_id:'TC001', case_name:'Wrong Document Uploaded',           matched:true, match_reason:'pipeline halted as expected (no decision)', halt:true, halt_message:"Your CONSULTATION claim requires: HOSPITAL_BILL, PRESCRIPTION. You uploaded: PRESCRIPTION × 2. Missing: HOSPITAL_BILL.", expected_decision:null, actual_decision:null, approved_amount:null, confidence:null, rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:7,  claim_id:'EVAL-TC001-d86ba4' },
  { case_id:'TC002', case_name:'Unreadable Document',               matched:true, match_reason:'pipeline halted as expected (no decision)', halt:true, halt_message:"'blurry_bill.jpg' (PHARMACY_BILL) could not be read. Please re-upload a clear, well-lit photo.", expected_decision:null, actual_decision:null, approved_amount:null, confidence:null, rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:6,  claim_id:'EVAL-TC002-f6a96c' },
  { case_id:'TC003', case_name:'Documents from Different Patients', matched:true, match_reason:'pipeline halted as expected (no decision)', halt:true, halt_message:"Documents belong to different patients: PRESCRIPTION → 'Rajesh Kumar'; HOSPITAL_BILL → 'Arjun Mehta'. All documents must belong to the same patient.", expected_decision:null, actual_decision:null, approved_amount:null, confidence:null, rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:10, claim_id:'EVAL-TC003-45fd77' },
  { case_id:'TC004', case_name:'Clean Consultation – Full Approval',matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'APPROVED',      actual_decision:'APPROVED',      approved_amount:1350,   confidence:0.90,  rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:28, claim_id:'EVAL-TC004-2662a6' },
  { case_id:'TC005', case_name:'Waiting Period – Diabetes',         matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'REJECTED',      actual_decision:'REJECTED',      approved_amount:0,      confidence:0.95,  rejection_reasons:['WAITING_PERIOD'], fraud_flags:[], degraded_components:[], trace_steps:24, claim_id:'EVAL-TC005-cd5fee' },
  { case_id:'TC006', case_name:'Dental Partial – Cosmetic Excluded',matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'PARTIAL',       actual_decision:'PARTIAL',       approved_amount:8000,   confidence:0.90,  rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:27, claim_id:'EVAL-TC006-074b70' },
  { case_id:'TC007', case_name:'MRI Without Pre-Authorization',     matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'REJECTED',      actual_decision:'REJECTED',      approved_amount:0,      confidence:0.95,  rejection_reasons:['PRE_AUTH_MISSING'], fraud_flags:[], degraded_components:[], trace_steps:27, claim_id:'EVAL-TC007-c7752b' },
  { case_id:'TC008', case_name:'Per-Claim Limit Exceeded',          matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'REJECTED',      actual_decision:'REJECTED',      approved_amount:0,      confidence:0.95,  rejection_reasons:['PER_CLAIM_EXCEEDED'], fraud_flags:[], degraded_components:[], trace_steps:22, claim_id:'EVAL-TC008-3b6314' },
  { case_id:'TC009', case_name:'Fraud – Multiple Same-Day Claims',  matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'MANUAL_REVIEW', actual_decision:'MANUAL_REVIEW', approved_amount:0,      confidence:0.70,  rejection_reasons:[], fraud_flags:['SAME_DAY_CLAIMS: 4 on 2024-10-30 (limit: 2)'], degraded_components:[], trace_steps:26, claim_id:'EVAL-TC009-dde0ba' },
  { case_id:'TC010', case_name:'Network Hospital Discount',         matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'APPROVED',      actual_decision:'APPROVED',      approved_amount:3240,   confidence:0.90,  rejection_reasons:[], fraud_flags:[], degraded_components:[], trace_steps:28, claim_id:'EVAL-TC010-32f967' },
  { case_id:'TC011', case_name:'Component Failure – Graceful Degradation', matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'APPROVED', actual_decision:'APPROVED', approved_amount:4000, confidence:0.297, rejection_reasons:[], fraud_flags:[], degraded_components:['ExtractionAgent(degraded)','ExtractionAgent(degraded)'], trace_steps:29, claim_id:'EVAL-TC011-0ac86a' },
  { case_id:'TC012', case_name:'Excluded Treatment (Bariatric)',    matched:true, match_reason:'decision and amount matched', halt:false, halt_message:null, expected_decision:'REJECTED',      actual_decision:'REJECTED',      approved_amount:0,      confidence:0.92,  rejection_reasons:['EXCLUDED_CONDITION'], fraud_flags:[], degraded_components:[], trace_steps:21, claim_id:'EVAL-TC012-f8fb52' },
]

const DEC_COLOR = {
  APPROVED:'#34d399', PARTIAL:'#FBBF24', REJECTED:'#F87171',
  MANUAL_REVIEW:'#FB923C', HALT:'#9B82FD',
}

function Tag({ text, color }) {
  return (
    <span className="text-xs font-mono px-1.5 py-0.5 rounded"
      style={{ color, background:`${color}18`, border:`1px solid ${color}44` }}>
      {text}
    </span>
  )
}

export default function EvalPage() {
  const navigate = useNavigate()
  const passed   = EVAL_REPORT.filter((t) => t.matched).length
  const totalEvt = EVAL_REPORT.reduce((s, t) => s + t.trace_steps, 0)
  const avgConf  = EVAL_REPORT.filter((t) => t.confidence != null)
  const avgPct   = Math.round(avgConf.reduce((s, t) => s + t.confidence, 0) / avgConf.length * 100)

  return (
    <div className="max-w-screen-xl mx-auto px-6 py-8">

      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          {/* Plum shield */}
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'rgba(124,92,252,0.15)', border: '1px solid rgba(124,92,252,0.3)' }}>
            <svg width="20" height="20" viewBox="0 0 30 30" fill="none">
              <path d="M15 3C15 3 7 6 7 13C7 19.5 11 24 15 26.5C19 24 23 19.5 23 13C23 6 15 3 15 3Z" fill="#7C5CFC" />
              <path d="M15 8C15 8 10 10.5 10 14.5C10 17.9 12.5 20.5 15 22C17.5 20.5 20 17.9 20 14.5C20 10.5 15 8 15 8Z" fill="#141130" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold" style={{ color: '#F2F0FF' }}>Eval Report</h1>
        </div>
        <p className="text-sm" style={{ color: '#6B6896' }}>
          All 12 test cases from <code className="text-xs px-1 py-0.5 rounded font-mono"
            style={{ background: 'rgba(124,92,252,0.1)', color: '#B8A9FF', border: '1px solid rgba(124,92,252,0.2)' }}>
            test_cases.json
          </code> run through the full pipeline.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        {[
          { value: `${passed}/${EVAL_REPORT.length}`, label: 'Test cases passed', color: '#34d399' },
          { value: '100%',      label: 'Pass rate',         color: '#7C5CFC' },
          { value: totalEvt,   label: 'Total trace events', color: '#B8A9FF' },
          { value: `${avgPct}%`, label: 'Avg confidence',   color: '#FBBF24' },
        ].map(({ value, label, color }) => (
          <div key={label} className="rounded-2xl p-4 border"
            style={{ background: '#141130', borderColor: '#2A2550' }}>
            <div className="text-3xl font-bold mb-1" style={{ color }}>{value}</div>
            <div className="text-xs" style={{ color: '#6B6896' }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="flex flex-col gap-2.5">
        {EVAL_REPORT.map((tc) => {
          const dec      = tc.halt ? 'HALT' : (tc.actual_decision || '—')
          const decColor = DEC_COLOR[dec] || '#6B6896'

          return (
            <div
              key={tc.case_id}
              className="rounded-2xl border p-4 transition-colors"
              style={{ background: '#141130', borderColor: '#2A2550' }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(124,92,252,0.4)' }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#2A2550' }}
            >
              <div className="flex flex-wrap items-center gap-3">

                {/* Pass tick + case id */}
                <div className="flex items-center gap-2 shrink-0">
                  <span className="w-5 h-5 rounded-full flex items-center justify-center text-xs"
                    style={{ background: '#022c22', border: '1.5px solid #34d399', color: '#34d399' }}>
                    ✓
                  </span>
                  <span className="text-xs font-mono px-1.5 py-0.5 rounded"
                    style={{ background: 'rgba(124,92,252,0.1)', color: '#9B82FD', border: '1px solid rgba(124,92,252,0.2)' }}>
                    {tc.case_id}
                  </span>
                </div>

                {/* Name */}
                <div className="flex-1 min-w-48">
                  <div className="font-semibold text-sm" style={{ color: '#F2F0FF' }}>{tc.case_name}</div>
                  <div className="text-xs mt-0.5" style={{ color: '#6B6896' }}>{tc.match_reason}</div>
                </div>

                {/* Decision */}
                <div className="shrink-0 text-right">
                  <span className="text-xs font-bold px-2.5 py-1 rounded-full"
                    style={{ color: decColor, background: `${decColor}18`, border: `1px solid ${decColor}44` }}>
                    {dec}
                  </span>
                  {tc.approved_amount != null && !tc.halt && (
                    <div className="text-xs mt-1" style={{ color: decColor }}>
                      ₹{Number(tc.approved_amount).toLocaleString('en-IN')}
                    </div>
                  )}
                </div>

                {/* Confidence bar */}
                <div className="shrink-0 w-28">
                  {tc.confidence != null ? (
                    <div>
                      <div className="text-xs mb-1" style={{ color: '#6B6896' }}>Confidence</div>
                      <div className="flex items-center gap-1.5">
                        <div className="flex-1 rounded-full h-1.5" style={{ background: '#2A2550' }}>
                          <div style={{
                            width: `${Math.round(tc.confidence * 100)}%`,
                            background: tc.confidence >= 0.8 ? '#34d399' : tc.confidence >= 0.5 ? '#FBBF24' : '#F87171',
                          }} className="h-1.5 rounded-full" />
                        </div>
                        <span className="text-xs font-mono" style={{ color: '#9491C0' }}>
                          {Math.round(tc.confidence * 100)}%
                        </span>
                      </div>
                    </div>
                  ) : <span className="text-xs" style={{ color: '#3A3568' }}>—</span>}
                </div>

                {/* Events count */}
                <div className="shrink-0 text-center w-14">
                  <div className="text-xs" style={{ color: '#6B6896' }}>Events</div>
                  <div className="text-sm font-mono" style={{ color: '#C4B5FD' }}>{tc.trace_steps}</div>
                </div>

                {/* Replay */}
                <button
                  onClick={() => navigate(`/claims/${tc.claim_id}`)}
                  className="text-xs px-3 py-1.5 rounded-lg border transition-all shrink-0"
                  style={{ color: '#9B82FD', borderColor: 'rgba(124,92,252,0.35)', background: 'rgba(124,92,252,0.08)' }}
                >
                  ↻ Replay
                </button>
              </div>

              {/* Gate message */}
              {tc.halt_message && (
                <div className="mt-3 rounded-xl px-3 py-2 text-xs leading-relaxed"
                  style={{ background: 'rgba(155,130,253,0.08)', border: '1px solid rgba(124,92,252,0.3)', color: '#C4B5FD' }}>
                  <span className="font-semibold" style={{ color: '#9B82FD' }}>Gate: </span>
                  {tc.halt_message}
                </div>
              )}

              {/* Tags */}
              {(tc.rejection_reasons?.length > 0 || tc.fraud_flags?.length > 0 || tc.degraded_components?.length > 0) && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {tc.rejection_reasons.map((r) => <Tag key={r} text={r} color="#F87171" />)}
                  {tc.fraud_flags.map((f) => <Tag key={f} text={f} color="#FB923C" />)}
                  {tc.degraded_components.map((d) => <Tag key={d} text={d} color="#FBBF24" />)}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer notes */}
      <div className="mt-8 rounded-2xl border p-5" style={{ background: '#141130', borderColor: '#2A2550' }}>
        <h3 className="font-semibold mb-3 flex items-center gap-2" style={{ color: '#C4B5FD' }}>
          <span style={{ color: '#7C5CFC' }}>ℹ</span> Notes
        </h3>
        <ul className="space-y-1.5 text-sm" style={{ color: '#8B87B5' }}>
          <li>• <strong style={{ color: '#C4B5FD' }}>TC001–TC003</strong> test early doc detection. The gate fires before any LLM extraction call.</li>
          <li>• <strong style={{ color: '#C4B5FD' }}>TC010</strong> tests calculation order: network discount applied before co-pay (₹4,500 → ₹3,600 → ₹3,240).</li>
          <li>• <strong style={{ color: '#C4B5FD' }}>TC011</strong> tests graceful degradation — pipeline continues at confidence 0.297 after component failure.</li>
          <li>• Click <strong style={{ color: '#9B82FD' }}>↻ Replay</strong> on any case to animate its trace in the pipeline graph.</li>
        </ul>
      </div>
    </div>
  )
}
