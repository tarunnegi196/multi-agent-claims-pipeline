import { useState, useRef } from 'react'
import { TEST_CASES } from '../testCases'
import { uploadFile } from '../api'

const CATEGORIES   = ['CONSULTATION','DIAGNOSTIC','PHARMACY','DENTAL','VISION','ALTERNATIVE_MEDICINE']
const DOC_TYPES    = ['PRESCRIPTION','HOSPITAL_BILL','LAB_REPORT','PHARMACY_BILL','DISCHARGE_SUMMARY','DENTAL_REPORT']
const QUALITY_OPTS = ['GOOD','DEGRADED','UNREADABLE']
const MEMBERS      = ['EMP001','EMP002','EMP003','EMP004','EMP005','EMP006','EMP007','EMP008','EMP009','EMP010']
const ACCEPT       = 'image/jpeg,image/jpg,image/png,image/webp,application/pdf'

const BLANK_DOC = {
  file_id: '', file_name: 'document.jpg',
  actual_type: 'PRESCRIPTION', quality: 'GOOD',
  patient_name_on_doc: '', content: '',
  file_path: null, uploading: false, upload_error: null, auto_detect: false,
}

const DEFAULT_FORM = {
  member_id: 'EMP001', policy_id: 'PLUM_GHI_2024',
  claim_category: 'CONSULTATION', treatment_date: '2024-11-01',
  claimed_amount: 1500, hospital_name: '', ytd_claims_amount: 0,
  simulate_component_failure: false,
  documents: [
    { ...BLANK_DOC, file_id: 'F001', file_name: 'prescription.jpg',  actual_type: 'PRESCRIPTION'  },
    { ...BLANK_DOC, file_id: 'F002', file_name: 'hospital_bill.jpg', actual_type: 'HOSPITAL_BILL' },
  ],
}

const genId = () => 'F' + Math.floor(Math.random() * 9000 + 1000)

/* ── File upload widget ──────────────────────────────────────────── */
function FileUploadCell({ doc, onUploaded }) {
  const inputRef   = useRef(null)
  const isUploaded = !!doc.file_path && !doc.uploading

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    onUploaded({ uploading: true, upload_error: null })
    try {
      const res = await uploadFile(file)
      onUploaded({ file_id: res.file_id, file_name: res.file_name, file_path: res.file_path, content: '', uploading: false, upload_error: null })
    } catch (err) {
      onUploaded({ uploading: false, upload_error: err.message })
    }
    e.target.value = ''
  }

  return (
    <div>
      <label style={{ fontWeight: 700, marginBottom: 4, display: 'block', fontSize: 11, color: '#570e40' }}>
        Upload file <span style={{ color: '#a0a5ab', fontWeight: 400 }}>JPG · PNG · PDF · WebP</span>
      </label>
      <input ref={inputRef} type="file" accept={ACCEPT} onChange={handleFile} style={{ display: 'none' }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" onClick={() => inputRef.current?.click()} disabled={doc.uploading}
          style={{
            background: isUploaded ? '#d4e5b2' : '#eae1e7',
            border: `1px solid ${isUploaded ? '#92bd33' : '#ced5dd'}`,
            color: isUploaded ? '#4a7a10' : '#570e40',
            borderRadius: 30,
            padding: '5px 14px',
            fontSize: 12,
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            transition: 'background-color 0.1s',
            opacity: doc.uploading ? 0.5 : 1,
            fontFamily: 'Inter, Arial, sans-serif',
          }}>
          {doc.uploading ? (
            <><svg style={{ animation: '0.8s linear infinite spin', width: 12, height: 12 }} viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" strokeOpacity="0.25"/>
              <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z"/>
            </svg>Uploading…</>
          ) : isUploaded ? '✓ Uploaded' : <>
            <svg viewBox="0 0 20 20" fill="currentColor" width="13" height="13">
              <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clipRule="evenodd"/>
            </svg>Choose file
          </>}
        </button>

        {isUploaded && (
          <>
            <span style={{ fontSize: 11, color: '#4a7a10', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {doc.file_name}
            </span>
            <button type="button" onClick={() => inputRef.current?.click()}
              style={{ fontSize: 11, color: '#9e708c', background: 'none', border: 'none', cursor: 'pointer', transition: 'color 0.1s' }}>
              re-upload
            </button>
          </>
        )}
      </div>

      {/* Auto-detect toggle */}
      {isUploaded && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, cursor: 'pointer', userSelect: 'none' }}>
          <input type="checkbox" checked={doc.auto_detect || false}
            onChange={(e) => onUploaded({ auto_detect: e.target.checked })}
            style={{ accentColor: '#7b4067' }} />
          <span style={{ fontSize: 11, color: doc.auto_detect ? '#570e40' : '#9e708c' }}>
            Let Gemini auto-detect type
            {doc.auto_detect && (
              <span style={{ marginLeft: 6, padding: '1px 6px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                background: '#ffebdb', color: '#570e40', border: '1px solid #ced5dd' }}>
                Gemini will classify
              </span>
            )}
          </span>
        </label>
      )}

      {doc.upload_error && (
        <p style={{ fontSize: 11, color: '#ea384c', marginTop: 4, background: '#ffdddd', padding: '4px 8px', borderRadius: 4 }}>
          Upload failed: {doc.upload_error}
        </p>
      )}
    </div>
  )
}

/* ── Main form ────────────────────────────────────────────────────── */
export default function ClaimForm({ onSubmit, isSubmitting }) {
  const [form, setForm]           = useState(DEFAULT_FORM)
  const [selectedPreset, setPreset] = useState('')
  const [showAdvanced, setAdvanced] = useState(false)

  function loadPreset(caseId) {
    const tc = TEST_CASES.find((t) => t.id === caseId)
    if (!tc) return
    setPreset(caseId)
    setForm({
      member_id: tc.input.member_id || 'EMP001',
      policy_id: tc.input.policy_id || 'PLUM_GHI_2024',
      claim_category: tc.input.claim_category || 'CONSULTATION',
      treatment_date: tc.input.treatment_date || '',
      claimed_amount: tc.input.claimed_amount || 0,
      hospital_name: tc.input.hospital_name || '',
      ytd_claims_amount: tc.input.ytd_claims_amount || 0,
      simulate_component_failure: tc.input.simulate_component_failure || false,
      claims_history: tc.input.claims_history || [],
      documents: tc.input.documents.map((d) => ({
        ...BLANK_DOC,
        file_id: d.file_id || genId(),
        file_name: d.file_name || 'document.jpg',
        actual_type: d.actual_type || 'PRESCRIPTION',
        quality: d.quality || 'GOOD',
        patient_name_on_doc: d.patient_name_on_doc || '',
        content: d.content ? JSON.stringify(d.content, null, 2) : '',
      })),
    })
    setAdvanced(!!(tc.input.hospital_name || tc.input.ytd_claims_amount || tc.input.simulate_component_failure || tc.input.claims_history?.length))
  }

  const setField    = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const setDoc      = (i, k, v) => setForm((f) => { const d = [...f.documents]; d[i] = { ...d[i], [k]: v }; return { ...f, documents: d } })
  const setDocMulti = (i, p)    => setForm((f) => { const d = [...f.documents]; d[i] = { ...d[i], ...p }; return { ...f, documents: d } })
  const addDoc      = () => setForm((f) => ({ ...f, documents: [...f.documents, { ...BLANK_DOC, file_id: genId() }] }))
  const removeDoc   = (i) => setForm((f) => ({ ...f, documents: f.documents.filter((_, idx) => idx !== i) }))

  function handleSubmit(e) {
    e.preventDefault()
    const docs = form.documents.map((d) => {
      const doc = { file_id: d.file_id, file_name: d.file_name }
      if (!(d.file_path && d.auto_detect)) doc.actual_type = d.actual_type
      if (d.file_path) doc.file_path = d.file_path
      if (d.quality && d.quality !== 'GOOD') doc.quality = d.quality
      if (d.patient_name_on_doc) doc.patient_name_on_doc = d.patient_name_on_doc
      if (d.content && !d.file_path) { try { doc.content = JSON.parse(d.content) } catch {} }
      return doc
    })
    const payload = {
      member_id: form.member_id, policy_id: form.policy_id,
      claim_category: form.claim_category, treatment_date: form.treatment_date,
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

  /* Light-panel form colours — warm white Plum section */
  const inputStyle = {
    color: '#2d2d2d',
    background: '#ffffff',
    border: '1px solid #ced5dd',
    borderRadius: 6,
    padding: '8px 12px',
    fontSize: 14,
    lineHeight: '1.42857',
    width: '100%',
    height: 38,
    fontFamily: 'Inter, Arial, sans-serif',
    transition: 'border-color 0.1s',
  }

  const divider = { borderTop: '1px solid #ced5dd', margin: '4px 0' }

  /* Semantic colours for the light form panel */
  const labelStyle = { fontWeight: 700, marginBottom: 5, display: 'block', fontSize: 12, color: '#570e40' }
  const mutedStyle = { fontWeight: 400, color: '#9e708c' }
  const sectionBg  = { background: '#fff8f1', border: '1px solid #ced5dd', borderRadius: 10, padding: 10 }
  const docRowBg   = { background: '#fffbf7', border: '1px solid #ced5dd', borderRadius: 10, padding: 10, position: 'relative' }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14, fontFamily: 'Inter, Arial, sans-serif' }}>

      {/* Preset loader */}
      <div>
        <label style={labelStyle}>Quick-load test case</label>
        <select value={selectedPreset} onChange={(e) => loadPreset(e.target.value)} style={inputStyle}>
          <option value="">— choose a preset —</option>
          {TEST_CASES.map((tc) => <option key={tc.id} value={tc.id}>{tc.name}</option>)}
        </select>
        {presetTc && (
          <div style={{ marginTop: 6, fontSize: 12, padding: '6px 10px', borderRadius: 6,
            background: '#ffebdb', border: '1px solid #ced5dd', color: '#570e40' }}>
            Expected: <strong>{presetTc.expectedOutcome}</strong>
          </div>
        )}
      </div>

      <div style={divider} />

      {/* Core fields */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div>
          <label style={labelStyle}>Member ID</label>
          <select value={form.member_id} onChange={(e) => setField('member_id', e.target.value)} style={inputStyle}>
            {MEMBERS.map((m) => <option key={m}>{m}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Category</label>
          <select value={form.claim_category} onChange={(e) => setField('claim_category', e.target.value)} style={inputStyle}>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div>
          <label style={labelStyle}>Treatment Date</label>
          <input type="date" value={form.treatment_date} onChange={(e) => setField('treatment_date', e.target.value)} required style={inputStyle} />
        </div>
        <div>
          <label style={labelStyle}>Amount (₹)</label>
          <input type="number" min="1" value={form.claimed_amount} onChange={(e) => setField('claimed_amount', e.target.value)} required style={inputStyle} />
        </div>
      </div>

      {/* Advanced toggle */}
      <button type="button" onClick={() => setAdvanced((v) => !v)}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9e708c', fontSize: 12,
          display: 'flex', alignItems: 'center', gap: 4, fontFamily: 'Inter, Arial, sans-serif',
          transition: 'color 0.1s', padding: 0, textAlign: 'left' }}>
        <span style={{ fontFamily: 'monospace' }}>{showAdvanced ? '▾' : '▸'}</span> Advanced options
      </button>

      {showAdvanced && (
        <div style={sectionBg}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={labelStyle}>Hospital Name</label>
              <input type="text" placeholder="e.g. Apollo Hospitals" value={form.hospital_name || ''}
                onChange={(e) => setField('hospital_name', e.target.value)} style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>YTD Claims (₹)</label>
              <input type="number" min="0" value={form.ytd_claims_amount}
                onChange={(e) => setField('ytd_claims_amount', e.target.value)} style={inputStyle} />
            </div>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 12, color: '#55657d', marginTop: 8 }}>
            <input type="checkbox" checked={form.simulate_component_failure}
              onChange={(e) => setField('simulate_component_failure', e.target.checked)}
              style={{ accentColor: '#7b4067' }} />
            Simulate component failure (TC011)
          </label>
        </div>
      )}

      {/* Documents */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <label style={{ ...labelStyle, margin: 0 }}>Documents ({form.documents.length})</label>
          <button type="button" onClick={addDoc}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#570e40',
              fontSize: 12, fontWeight: 700, transition: 'color 0.1s', fontFamily: 'Inter, Arial, sans-serif' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#ff4052' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#570e40' }}>
            + Add document
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {form.documents.map((doc, i) => (
            <div key={i} style={docRowBg}>
              <button type="button" onClick={() => removeDoc(i)}
                style={{ position: 'absolute', top: 8, right: 8, background: 'none', border: 'none',
                  cursor: 'pointer', color: '#a0a5ab', fontSize: 12, transition: 'color 0.1s',
                  fontFamily: 'Inter, Arial, sans-serif' }}
                onMouseEnter={(e) => { e.currentTarget.style.color = '#ff4052' }}
                onMouseLeave={(e) => { e.currentTarget.style.color = '#a0a5ab' }}>✕
              </button>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
                <div>
                  <label style={labelStyle}>
                    Doc Type
                    {doc.auto_detect && doc.file_path && (
                      <span style={{ marginLeft: 4, fontWeight: 400, color: '#9e708c', fontSize: 10 }}>← Gemini</span>
                    )}
                  </label>
                  <select value={doc.actual_type} onChange={(e) => setDoc(i, 'actual_type', e.target.value)}
                    disabled={!!(doc.auto_detect && doc.file_path)}
                    style={{ ...inputStyle, opacity: doc.auto_detect && doc.file_path ? 0.4 : 1, fontSize: 12 }}>
                    {DOC_TYPES.map((t) => <option key={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Quality</label>
                  <select value={doc.quality || 'GOOD'} onChange={(e) => setDoc(i, 'quality', e.target.value)}
                    style={{ ...inputStyle, fontSize: 12 }}>
                    {QUALITY_OPTS.map((q) => <option key={q}>{q}</option>)}
                  </select>
                </div>
              </div>

              <div style={{ marginBottom: 8 }}>
                <FileUploadCell doc={doc} onUploaded={(patch) => setDocMulti(i, patch)} />
              </div>

              {/* Divider */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '8px 0' }}>
                <div style={{ flex: 1, borderTop: '1px solid #ced5dd' }} />
                <span style={{ fontSize: 10, color: '#a0a5ab' }}>or structured JSON</span>
                <div style={{ flex: 1, borderTop: '1px solid #ced5dd' }} />
              </div>

              <div>
                <label style={{ ...labelStyle, color: '#9e708c' }}>
                  Content JSON
                  {doc.file_path && <span style={{ fontWeight: 400, marginLeft: 4, color: '#a0a5ab' }}>— ignored</span>}
                </label>
                <textarea value={doc.content || ''} onChange={(e) => setDoc(i, 'content', e.target.value)}
                  rows={doc.content ? 3 : 1} disabled={!!doc.file_path}
                  placeholder='{"doctor_name": "Dr. Smith", ...}'
                  style={{ ...inputStyle, height: 'auto', minHeight: 32, fontFamily: 'monospace', fontSize: 11,
                    resize: 'vertical', color: doc.file_path ? '#a0a5ab' : '#2d2d2d',
                    opacity: doc.file_path ? 0.5 : 1 }} />
              </div>

              <div style={{ marginTop: 6 }}>
                <label style={{ ...labelStyle, color: '#9e708c' }}>Patient name <span style={{ fontWeight: 400 }}>(optional)</span></label>
                <input type="text" value={doc.patient_name_on_doc || ''} onChange={(e) => setDoc(i, 'patient_name_on_doc', e.target.value)}
                  placeholder="auto-detect" style={{ ...inputStyle, fontSize: 12 }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Submit CTA */}
      <button type="submit" disabled={isSubmitting}
        className="btn-cta"
        style={{
          background: isSubmitting ? '#340926' : '#ff4052',
          color: isSubmitting ? '#9e708c' : '#fff',
          border: isSubmitting ? '1px solid #460932' : 'none',
          borderRadius: 30,
          padding: '10px 24px',
          fontSize: 14,
          fontWeight: 700,
          cursor: isSubmitting ? 'not-allowed' : 'pointer',
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          boxShadow: isSubmitting ? 'none' : 'rgba(0,0,0,0.1) 2px 4px 20px 5px',
          transition: 'background-color 0.1s',
          fontFamily: 'Inter, Arial, sans-serif',
        }}
        onMouseEnter={(e) => { if (!isSubmitting) e.currentTarget.style.backgroundColor = '#e23744' }}
        onMouseLeave={(e) => { if (!isSubmitting) e.currentTarget.style.backgroundColor = '#ff4052' }}>
        {isSubmitting ? (
          <><svg style={{ animation: '0.8s linear infinite spin', width: 16, height: 16 }} viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" strokeOpacity="0.25"/>
            <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z"/>
          </svg>Processing…</>
        ) : 'Submit Claim'}
      </button>

    </form>
  )
}
