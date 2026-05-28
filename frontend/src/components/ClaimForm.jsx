import { useState } from 'react'
import { TEST_CASES } from '../testCases'

const CATEGORIES = ['CONSULTATION', 'DIAGNOSTIC', 'PHARMACY', 'DENTAL', 'VISION', 'ALTERNATIVE_MEDICINE']
const DOC_TYPES  = ['PRESCRIPTION', 'HOSPITAL_BILL', 'LAB_REPORT', 'PHARMACY_BILL', 'DISCHARGE_SUMMARY', 'DENTAL_REPORT']
const QUALITY_OPTS = ['GOOD', 'DEGRADED', 'UNREADABLE']
const MEMBERS    = ['EMP001','EMP002','EMP003','EMP004','EMP005','EMP006','EMP007','EMP008','EMP009','EMP010']

const DEFAULT_FORM = {
  member_id: 'EMP001',
  policy_id: 'PLUM_GHI_2024',
  claim_category: 'CONSULTATION',
  treatment_date: '2024-11-01',
  claimed_amount: 1500,
  hospital_name: '',
  ytd_claims_amount: 0,
  simulate_component_failure: false,
  documents: [
    { file_id: 'F001', file_name: 'prescription.jpg',  actual_type: 'PRESCRIPTION',  quality: 'GOOD', patient_name_on_doc: '', content: '' },
    { file_id: 'F002', file_name: 'hospital_bill.jpg', actual_type: 'HOSPITAL_BILL', quality: 'GOOD', patient_name_on_doc: '', content: '' },
  ],
}

const genFileId = () => 'F' + Math.floor(Math.random() * 9000 + 1000)

/* ── Shared primitives ─────────────────────────────────────────── */
const borderColor  = '#2A2550'
const bgInput      = '#0C0A1C'
const textMuted    = '#6B6896'
const textLabel    = '#9491C0'

function Label({ children }) {
  return <label style={{ color: textLabel }} className="block text-xs font-medium mb-1">{children}</label>
}

function Input({ className = '', ...props }) {
  return (
    <input
      {...props}
      style={{ background: bgInput, borderColor, color: '#F2F0FF' }}
      className={`w-full border rounded-lg px-3 py-1.5 text-sm placeholder-[#3A3568]
        focus:outline-none focus:border-plum-500 focus:ring-1 focus:ring-plum-500/50 transition-colors ${className}`}
    />
  )
}

function Select({ children, className = '', ...props }) {
  return (
    <select
      {...props}
      style={{ background: bgInput, borderColor, color: '#F2F0FF' }}
      className={`w-full border rounded-lg px-3 py-1.5 text-sm
        focus:outline-none focus:border-plum-500 focus:ring-1 focus:ring-plum-500/50 transition-colors ${className}`}
    >
      {children}
    </select>
  )
}

/* ── Main component ────────────────────────────────────────────── */
export default function ClaimForm({ onSubmit, isSubmitting }) {
  const [form, setForm]               = useState(DEFAULT_FORM)
  const [selectedPreset, setPreset]   = useState('')
  const [showAdvanced, setAdvanced]   = useState(false)

  function loadPreset(caseId) {
    const tc = TEST_CASES.find((t) => t.id === caseId)
    if (!tc) return
    setPreset(caseId)
    const docs = tc.input.documents.map((d) => ({
      file_id: d.file_id || genFileId(),
      file_name: d.file_name || 'document.jpg',
      actual_type: d.actual_type || 'PRESCRIPTION',
      quality: d.quality || 'GOOD',
      patient_name_on_doc: d.patient_name_on_doc || '',
      content: d.content ? JSON.stringify(d.content, null, 2) : '',
    }))
    setForm({
      member_id:                tc.input.member_id     || 'EMP001',
      policy_id:                tc.input.policy_id     || 'PLUM_GHI_2024',
      claim_category:           tc.input.claim_category || 'CONSULTATION',
      treatment_date:           tc.input.treatment_date || '',
      claimed_amount:           tc.input.claimed_amount || 0,
      hospital_name:            tc.input.hospital_name  || '',
      ytd_claims_amount:        tc.input.ytd_claims_amount || 0,
      simulate_component_failure: tc.input.simulate_component_failure || false,
      claims_history:           tc.input.claims_history || [],
      documents: docs,
    })
    setAdvanced(!!(tc.input.hospital_name || tc.input.ytd_claims_amount || tc.input.simulate_component_failure || tc.input.claims_history?.length))
  }

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const setDoc   = (i, k, v) => setForm((f) => {
    const docs = [...f.documents]; docs[i] = { ...docs[i], [k]: v }; return { ...f, documents: docs }
  })
  const addDoc    = () => setForm((f) => ({ ...f, documents: [...f.documents, { file_id: genFileId(), file_name: 'document.jpg', actual_type: 'PRESCRIPTION', quality: 'GOOD', patient_name_on_doc: '', content: '' }] }))
  const removeDoc = (i) => setForm((f) => ({ ...f, documents: f.documents.filter((_, idx) => idx !== i) }))

  function handleSubmit(e) {
    e.preventDefault()
    const docs = form.documents.map((d) => {
      const doc = { file_id: d.file_id, file_name: d.file_name, actual_type: d.actual_type }
      if (d.quality && d.quality !== 'GOOD') doc.quality = d.quality
      if (d.patient_name_on_doc) doc.patient_name_on_doc = d.patient_name_on_doc
      if (d.content) { try { doc.content = JSON.parse(d.content) } catch {} }
      return doc
    })
    const payload = {
      member_id: form.member_id,
      policy_id: form.policy_id,
      claim_category: form.claim_category,
      treatment_date: form.treatment_date,
      claimed_amount: parseFloat(form.claimed_amount) || 0,
      ytd_claims_amount: parseFloat(form.ytd_claims_amount) || 0,
      simulate_component_failure: form.simulate_component_failure,
      documents: docs,
    }
    if (form.hospital_name) payload.hospital_name = form.hospital_name
    if (form.claims_history?.length) payload.claims_history = form.claims_history
    onSubmit(payload)
  }

  const presetTc = selectedPreset ? TEST_CASES.find((t) => t.id === selectedPreset) : null

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 text-sm">

      {/* Preset loader */}
      <div>
        <Label>Quick-load test case</Label>
        <Select value={selectedPreset} onChange={(e) => loadPreset(e.target.value)}>
          <option value="">— choose a preset —</option>
          {TEST_CASES.map((tc) => (
            <option key={tc.id} value={tc.id}>{tc.name}</option>
          ))}
        </Select>
        {presetTc && (
          <div
            className="mt-1.5 text-xs px-2.5 py-1.5 rounded-lg border"
            style={{ background: 'rgba(124,92,252,0.1)', borderColor: 'rgba(124,92,252,0.3)', color: '#B8A9FF' }}
          >
            Expected outcome: <span className="font-semibold">{presetTc.expectedOutcome}</span>
          </div>
        )}
      </div>

      <div style={{ borderColor }} className="border-t" />

      {/* Core fields */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Member ID</Label>
          <Select value={form.member_id} onChange={(e) => setField('member_id', e.target.value)}>
            {MEMBERS.map((m) => <option key={m}>{m}</option>)}
          </Select>
        </div>
        <div>
          <Label>Claim Category</Label>
          <Select value={form.claim_category} onChange={(e) => setField('claim_category', e.target.value)}>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Treatment Date</Label>
          <Input type="date" value={form.treatment_date} onChange={(e) => setField('treatment_date', e.target.value)} required />
        </div>
        <div>
          <Label>Claimed Amount (₹)</Label>
          <Input type="number" min="1" step="1" value={form.claimed_amount} onChange={(e) => setField('claimed_amount', e.target.value)} required />
        </div>
      </div>

      {/* Advanced toggle */}
      <button
        type="button"
        onClick={() => setAdvanced((v) => !v)}
        style={{ color: textMuted }}
        className="text-xs text-left flex items-center gap-1 hover:text-plum-300 transition-colors"
      >
        <span className="font-mono text-xs">{showAdvanced ? '▾' : '▸'}</span>
        Advanced options
      </button>

      {showAdvanced && (
        <div
          className="flex flex-col gap-3 rounded-xl p-3 border"
          style={{ background: '#0C0A1C', borderColor }}
        >
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Hospital Name</Label>
              <Input type="text" placeholder="e.g. Apollo Hospitals" value={form.hospital_name || ''} onChange={(e) => setField('hospital_name', e.target.value)} />
            </div>
            <div>
              <Label>YTD Claims Amount (₹)</Label>
              <Input type="number" min="0" value={form.ytd_claims_amount} onChange={(e) => setField('ytd_claims_amount', e.target.value)} />
            </div>
          </div>
          <label className="flex items-center gap-2 cursor-pointer" style={{ color: textMuted }}>
            <input
              type="checkbox"
              checked={form.simulate_component_failure}
              onChange={(e) => setField('simulate_component_failure', e.target.checked)}
              className="rounded"
              style={{ accentColor: '#7C5CFC' }}
            />
            <span className="text-xs">Simulate component failure (TC011)</span>
          </label>
        </div>
      )}

      {/* Documents */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <Label>Documents ({form.documents.length})</Label>
          <button
            type="button"
            onClick={addDoc}
            style={{ color: '#7C5CFC' }}
            className="text-xs hover:text-plum-400 font-semibold transition-colors"
          >
            + Add document
          </button>
        </div>

        <div className="flex flex-col gap-2.5">
          {form.documents.map((doc, i) => (
            <div key={i} className="rounded-xl p-3 border relative" style={{ background: '#0C0A1C', borderColor }}>
              <button
                type="button"
                onClick={() => removeDoc(i)}
                style={{ color: '#3A3568' }}
                className="absolute top-2.5 right-2.5 hover:text-red-400 text-xs transition-colors"
              >
                ✕
              </button>

              <div className="grid grid-cols-2 gap-2 mb-2">
                <div>
                  <Label>File Name</Label>
                  <Input type="text" value={doc.file_name} onChange={(e) => setDoc(i, 'file_name', e.target.value)} placeholder="document.jpg" />
                </div>
                <div>
                  <Label>Document Type</Label>
                  <Select value={doc.actual_type} onChange={(e) => setDoc(i, 'actual_type', e.target.value)}>
                    {DOC_TYPES.map((t) => <option key={t}>{t}</option>)}
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 mb-2">
                <div>
                  <Label>Quality</Label>
                  <Select value={doc.quality || 'GOOD'} onChange={(e) => setDoc(i, 'quality', e.target.value)}>
                    {QUALITY_OPTS.map((q) => <option key={q}>{q}</option>)}
                  </Select>
                </div>
                <div>
                  <Label>Patient name on doc</Label>
                  <Input type="text" value={doc.patient_name_on_doc || ''} onChange={(e) => setDoc(i, 'patient_name_on_doc', e.target.value)} placeholder="auto-detect" />
                </div>
              </div>

              <div>
                <Label>Structured content (JSON) — replaces file upload</Label>
                <textarea
                  value={doc.content || ''}
                  onChange={(e) => setDoc(i, 'content', e.target.value)}
                  rows={doc.content ? 4 : 1}
                  placeholder='{"doctor_name": "Dr. Smith", "diagnosis": "Fever", ...}'
                  style={{ background: '#070518', borderColor, color: '#C4B5FD', resize: 'vertical' }}
                  className="w-full border rounded-lg px-3 py-1.5 text-xs font-mono placeholder-[#3A3568]
                    focus:outline-none focus:border-plum-500 focus:ring-1 focus:ring-plum-500/50 transition-colors"
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={isSubmitting}
        style={isSubmitting
          ? { background: '#1D1840', color: '#4B4878', border: '1px solid #2A2550' }
          : { background: 'linear-gradient(135deg, #7C5CFC 0%, #6540F0 100%)', border: '1px solid #7C5CFC', color: 'white' }
        }
        className="w-full font-semibold py-2.5 rounded-xl text-sm transition-all
          hover:shadow-lg hover:shadow-plum-500/20 flex items-center justify-center gap-2 disabled:cursor-not-allowed"
      >
        {isSubmitting ? (
          <>
            <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z" />
            </svg>
            Processing claim…
          </>
        ) : (
          <>
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
            </svg>
            Submit Claim
          </>
        )}
      </button>
    </form>
  )
}
