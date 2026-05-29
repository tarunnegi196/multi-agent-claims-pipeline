import { useState, useRef } from 'react'
import { uploadFile } from '../api'

const CATEGORIES   = ['CONSULTATION','DIAGNOSTIC','PHARMACY','DENTAL','VISION','ALTERNATIVE_MEDICINE']
const DOC_TYPES    = ['PRESCRIPTION','HOSPITAL_BILL','LAB_REPORT','PHARMACY_BILL','DISCHARGE_SUMMARY','DENTAL_REPORT']
const ACCEPT       = 'image/jpeg,image/jpg,image/png,image/webp,application/pdf'

const BLANK_DOC = {
  file_id: '', file_name: 'document.jpg',
  actual_type: 'PRESCRIPTION',
  file_path: null, uploading: false, upload_error: null,
  // Default ON: when a real file is present, let Gemini classify + assess quality
  auto_detect: true,
}

const DEFAULT_FORM = {
  member_id: '',
  policy_id: 'PLUM_GHI_2024',
  claim_category: 'CONSULTATION',
  // Optional advanced fields — left empty so the pipeline derives them
  treatment_date: '',
  claimed_amount: '',
  hospital_name: '',
  ytd_claims_amount: '',
  documents: [
    { ...BLANK_DOC, file_id: 'F001', file_name: 'document_1.jpg' },
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
      onUploaded({
        file_id: res.file_id, file_name: res.file_name, file_path: res.file_path,
        uploading: false, upload_error: null,
        auto_detect: true,
      })
    } catch (err) {
      onUploaded({ uploading: false, upload_error: err.message })
    }
    e.target.value = ''
  }

  return (
    <div>
      <input ref={inputRef} type="file" accept={ACCEPT} onChange={handleFile} style={{ display: 'none' }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" onClick={() => inputRef.current?.click()} disabled={doc.uploading}
          style={{
            background: isUploaded ? '#d4e5b2' : '#eae1e7',
            border: `1px solid ${isUploaded ? '#92bd33' : '#ced5dd'}`,
            color: isUploaded ? '#4a7a10' : '#570e40',
            borderRadius: 30, padding: '5px 14px', fontSize: 12, fontWeight: 600,
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
            transition: 'background-color 0.1s', opacity: doc.uploading ? 0.5 : 1,
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
            <span style={{ fontSize: 11, color: '#4a7a10', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {doc.file_name}
            </span>
            <button type="button" onClick={() => inputRef.current?.click()}
              style={{ fontSize: 11, color: '#9e708c', background: 'none', border: 'none', cursor: 'pointer', transition: 'color 0.1s' }}>
              re-upload
            </button>
          </>
        )}
      </div>

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
  const [form, setForm]             = useState(DEFAULT_FORM)
  const [showAdvanced, setAdvanced] = useState(false)

  const setField    = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const setDoc      = (i, k, v) => setForm((f) => { const d = [...f.documents]; d[i] = { ...d[i], [k]: v }; return { ...f, documents: d } })
  const setDocMulti = (i, p)    => setForm((f) => { const d = [...f.documents]; d[i] = { ...d[i], ...p }; return { ...f, documents: d } })
  const addDoc      = () => setForm((f) => ({ ...f, documents: [...f.documents, { ...BLANK_DOC, file_id: genId(), file_name: `document_${f.documents.length + 1}.jpg` }] }))
  const removeDoc   = (i) => setForm((f) => ({ ...f, documents: f.documents.filter((_, idx) => idx !== i) }))

  const uploadedCount = form.documents.filter((d) => !!d.file_path).length
  const memberIdValid = form.member_id.trim().length > 0
  const allUploaded   = form.documents.length > 0 && uploadedCount === form.documents.length
  const canSubmit     = memberIdValid && allUploaded && !isSubmitting

  function handleSubmit(e) {
    e.preventDefault()
    if (!canSubmit) return
    const docs = form.documents.map((d) => {
      const doc = { file_id: d.file_id, file_name: d.file_name, file_path: d.file_path }
      if (!d.auto_detect) doc.actual_type = d.actual_type
      return doc
    })

    // Build the payload — leave optional fields out entirely when blank so the
    // pipeline knows to derive them from extracted documents.
    const payload = {
      member_id: form.member_id.trim(),
      policy_id: form.policy_id,
      claim_category: form.claim_category,
      documents: docs,
    }
    if (form.treatment_date) payload.treatment_date = form.treatment_date
    if (form.claimed_amount && parseFloat(form.claimed_amount) > 0) {
      payload.claimed_amount = parseFloat(form.claimed_amount)
    }
    if (form.hospital_name) payload.hospital_name = form.hospital_name
    if (form.ytd_claims_amount && parseFloat(form.ytd_claims_amount) > 0) {
      payload.ytd_claims_amount = parseFloat(form.ytd_claims_amount)
    }
    onSubmit(payload)
  }

  const inputStyle = {
    color: '#2d2d2d', background: '#ffffff', border: '1px solid #ced5dd',
    borderRadius: 6, padding: '8px 12px', fontSize: 14, lineHeight: '1.42857',
    width: '100%', height: 38, fontFamily: 'Inter, Arial, sans-serif',
    transition: 'border-color 0.1s',
  }
  const labelStyle   = { fontWeight: 700, marginBottom: 5, display: 'block', fontSize: 12, color: '#570e40' }
  const sectionBg    = { background: '#fff8f1', border: '1px solid #ced5dd', borderRadius: 10, padding: 10 }
  const docRowBg     = { background: '#fffbf7', border: '1px solid #ced5dd', borderRadius: 10, padding: 10, position: 'relative' }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14, fontFamily: 'Inter, Arial, sans-serif' }}>

      {/* Employee ID — required, freeform */}
      <div>
        <label style={labelStyle}>
          Employee ID <span style={{ color: '#ff4052' }}>*</span>
        </label>
        <input
          type="text"
          placeholder="e.g. EMP001"
          value={form.member_id}
          onChange={(e) => setField('member_id', e.target.value.toUpperCase())}
          autoFocus
          required
          style={{ ...inputStyle, fontFamily: 'monospace', letterSpacing: '0.06em' }}
        />
        {!memberIdValid && (
          <p style={{ fontSize: 11, color: '#9e708c', marginTop: 4, fontStyle: 'italic' }}>
            Enter your employee ID to begin.
          </p>
        )}
      </div>

      {/* Claim Type */}
      <div>
        <label style={labelStyle}>Claim Type</label>
        <select value={form.claim_category} onChange={(e) => setField('claim_category', e.target.value)} style={inputStyle}>
          {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
        </select>
      </div>

      {/* Documents */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <label style={{ ...labelStyle, margin: 0 }}>
            Documents ({form.documents.length}) <span style={{ color: '#ff4052' }}>*</span>
          </label>
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
              {form.documents.length > 1 && (
                <button type="button" onClick={() => removeDoc(i)}
                  style={{ position: 'absolute', top: 8, right: 8, background: 'none', border: 'none',
                    cursor: 'pointer', color: '#a0a5ab', fontSize: 12, transition: 'color 0.1s',
                    fontFamily: 'Inter, Arial, sans-serif' }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = '#ff4052' }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = '#a0a5ab' }}>✕
                </button>
              )}

              <FileUploadCell doc={doc} onUploaded={(patch) => setDocMulti(i, patch)} />

              {doc.file_path && !doc.auto_detect && (
                <div style={{ marginTop: 8 }}>
                  <label style={labelStyle}>Document Type (manual override)</label>
                  <select value={doc.actual_type}
                    onChange={(e) => setDoc(i, 'actual_type', e.target.value)}
                    style={{ ...inputStyle, fontSize: 12 }}>
                    {DOC_TYPES.map((t) => <option key={t}>{t}</option>)}
                  </select>
                </div>
              )}
            </div>
          ))}
        </div>
        <p style={{ fontSize: 11, color: '#9e708c', marginTop: 6, fontStyle: 'italic' }}>
          Gemini will detect each document's type automatically.
        </p>
      </div>

      {/* Advanced toggle — power users only */}
      <button type="button" onClick={() => setAdvanced((v) => !v)}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9e708c', fontSize: 12,
          display: 'flex', alignItems: 'center', gap: 4, fontFamily: 'Inter, Arial, sans-serif',
          transition: 'color 0.1s', padding: 0, textAlign: 'left' }}>
        <span style={{ fontFamily: 'monospace' }}>{showAdvanced ? '▾' : '▸'}</span> Advanced overrides
      </button>

      {showAdvanced && (
        <div style={sectionBg}>
          <p style={{ fontSize: 11, color: '#9e708c', margin: '0 0 8px', fontStyle: 'italic' }}>
            All fields below are optional — pipeline extracts them from documents when blank.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={labelStyle}>Treatment Date</label>
              <input type="date" value={form.treatment_date}
                onChange={(e) => setField('treatment_date', e.target.value)} style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Claimed Amount (₹)</label>
              <input type="number" min="0" placeholder="auto"
                value={form.claimed_amount}
                onChange={(e) => setField('claimed_amount', e.target.value)} style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Hospital Name</label>
              <input type="text" placeholder="auto"
                value={form.hospital_name}
                onChange={(e) => setField('hospital_name', e.target.value)} style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>YTD Claims (₹)</label>
              <input type="number" min="0" placeholder="0"
                value={form.ytd_claims_amount}
                onChange={(e) => setField('ytd_claims_amount', e.target.value)} style={inputStyle} />
            </div>
          </div>
        </div>
      )}

      {/* Submit CTA */}
      <button type="submit" disabled={!canSubmit}
        title={
          !memberIdValid ? 'Enter an employee ID' :
          !allUploaded ? `Upload ${form.documents.length - uploadedCount} more document(s)` : ''
        }
        className="btn-cta"
        style={{
          background: isSubmitting ? '#340926' : !canSubmit ? '#9e708c' : '#ff4052',
          color: isSubmitting ? '#9e708c' : '#fff',
          border: isSubmitting ? '1px solid #460932' : 'none',
          borderRadius: 30, padding: '10px 24px', fontSize: 14, fontWeight: 700,
          cursor: !canSubmit ? 'not-allowed' : 'pointer', width: '100%',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          boxShadow: isSubmitting ? 'none' : 'rgba(0,0,0,0.1) 2px 4px 20px 5px',
          transition: 'background-color 0.1s', fontFamily: 'Inter, Arial, sans-serif',
          opacity: !canSubmit && !isSubmitting ? 0.85 : 1,
        }}
        onMouseEnter={(e) => { if (canSubmit) e.currentTarget.style.backgroundColor = '#e23744' }}
        onMouseLeave={(e) => { if (canSubmit) e.currentTarget.style.backgroundColor = '#ff4052' }}>
        {isSubmitting ? (
          <><svg style={{ animation: '0.8s linear infinite spin', width: 16, height: 16 }} viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" strokeOpacity="0.25"/>
            <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z"/>
          </svg>Processing…</>
        ) : !memberIdValid
          ? 'Enter Employee ID'
          : !allUploaded
            ? `Upload ${form.documents.length - uploadedCount} more to submit`
            : 'Submit Claim'}
      </button>

    </form>
  )
}
