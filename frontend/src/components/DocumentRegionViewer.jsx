/**
 * DocumentRegionViewer
 *
 * On-demand modal that shows an uploaded medical document with colour-coded
 * bounding boxes overlaid on each extracted field region.
 *
 * Completely separate from the claim pipeline — rendered only when the user
 * clicks "View regions" on an uploaded document card.
 *
 * Props:
 *   fileId   {string}  UUID returned by POST /api/files
 *   docType  {string}  DocumentType hint (PRESCRIPTION, HOSPITAL_BILL, etc.)
 *   fileName {string}  Display name for the header
 *   onClose  {fn}      Called when the user dismisses the modal
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { getDocumentRegions, getFileUrl } from '../api'

// One colour per category — matches the sidebar group headers
const CAT_COLOR = {
  patient:    '#4a90e2',
  doctor:     '#27ae60',
  clinical:   '#a855f7',
  financial:  '#f97316',
  identifier: '#0d9488',
  lab:        '#2563eb',
  date:       '#6b7280',
}
const CAT_ORDER = ['patient', 'doctor', 'clinical', 'financial', 'identifier', 'lab', 'date']

function colorFor(category) {
  return CAT_COLOR[category] || '#9e708c'
}

/* ── Loading / error states ─────────────────────────────────────── */
function StatusPane({ loading, error, count }) {
  if (loading) return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', height: 220, gap: 12, color: '#9e708c' }}>
      <svg style={{ animation: '0.9s linear infinite spin', width: 32, height: 32 }}
        viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="#340926" strokeWidth="3"/>
        <path d="M4 12a8 8 0 018-8" stroke="#7b4067" strokeWidth="3" strokeLinecap="round"/>
      </svg>
      <span style={{ fontSize: 13 }}>Calling Gemini to detect regions…</span>
      <span style={{ fontSize: 11, color: '#5a2e4a' }}>This is a separate call — not the pipeline</span>
    </div>
  )
  if (error) return (
    <div style={{ padding: 24, color: '#ff4052', fontSize: 13, lineHeight: '20px' }}>
      <strong>Could not detect regions.</strong><br />
      {error}<br />
      <span style={{ color: '#9e708c', fontSize: 11 }}>
        Check that a Gemini API key is configured and the file still exists.
      </span>
    </div>
  )
  if (count === 0) return (
    <div style={{ padding: 24, color: '#9e708c', fontSize: 13 }}>
      Gemini returned no regions for this document.<br />
      <span style={{ fontSize: 11 }}>
        The document may be too small, blurry, or the model could not locate fields.
      </span>
    </div>
  )
  return null
}

/* ── Sidebar: grouped field list ────────────────────────────────── */
function RegionSidebar({ regions, hoveredIdx, activeIdx, onHover, onActivate }) {
  const grouped = {}
  regions.forEach((r, i) => {
    const cat = r.category || 'identifier'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push({ ...r, _idx: i })
  })

  return (
    <div style={{ width: 252, borderLeft: '1px solid #2c0b21', overflowY: 'auto',
      flexShrink: 0, scrollbarWidth: 'thin', scrollbarColor: '#340926 #11040d', background: '#110310' }}>
      {CAT_ORDER.filter(c => grouped[c]?.length).map(cat => {
        const color = colorFor(cat)
        return (
          <div key={cat}>
            {/* Category header */}
            <div style={{
              padding: '7px 14px 5px', fontSize: 10, fontWeight: 800,
              color, textTransform: 'uppercase', letterSpacing: '0.09em',
              background: `${color}10`, borderBottom: `1px solid ${color}25`,
              position: 'sticky', top: 0, zIndex: 1,
            }}>
              {cat}
              <span style={{ marginLeft: 6, fontWeight: 400, color: `${color}99` }}>
                {grouped[cat].length}
              </span>
            </div>

            {grouped[cat].map(r => {
              const isActive = activeIdx === r._idx
              const isHover  = hoveredIdx === r._idx
              return (
                <div key={r._idx}
                  style={{
                    padding: '7px 14px',
                    borderBottom: '1px solid #1a0512',
                    cursor: 'pointer',
                    background: isActive ? `${color}22` : isHover ? `${color}10` : 'transparent',
                    transition: 'background 0.1s',
                    borderLeft: isActive ? `3px solid ${color}` : '3px solid transparent',
                  }}
                  onMouseEnter={() => onHover(r._idx)}
                  onMouseLeave={() => onHover(null)}
                  onClick={() => onActivate(r._idx)}
                >
                  <div style={{ fontSize: 10, color: '#7b5068', fontFamily: 'monospace', marginBottom: 2 }}>
                    {r.field}
                  </div>
                  <div style={{ fontSize: 12, color: isActive ? '#d8c5d1' : '#bea0b3',
                    wordBreak: 'break-word', lineHeight: '16px' }}>
                    {r.value || <span style={{ color: '#5a2e4a', fontStyle: 'italic' }}>—</span>}
                  </div>
                </div>
              )
            })}
          </div>
        )
      })}

      {/* Unknown category fallback */}
      {regions.filter(r => !CAT_ORDER.includes(r.category)).map((r, j) => {
        const color = colorFor(r.category)
        const isActive = activeIdx === r._idx
        const isHover  = hoveredIdx === r._idx
        return (
          <div key={`other-${j}`}
            style={{
              padding: '7px 14px', borderBottom: '1px solid #1a0512',
              cursor: 'pointer',
              background: isActive ? `${color}22` : isHover ? `${color}10` : 'transparent',
              transition: 'background 0.1s',
              borderLeft: isActive ? `3px solid ${color}` : '3px solid transparent',
            }}
            onMouseEnter={() => onHover(r._idx)}
            onMouseLeave={() => onHover(null)}
            onClick={() => onActivate(r._idx)}
          >
            <div style={{ fontSize: 10, color: '#7b5068', fontFamily: 'monospace', marginBottom: 2 }}>
              {r.field}
            </div>
            <div style={{ fontSize: 12, color: '#bea0b3', wordBreak: 'break-word' }}>
              {r.value || '—'}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ── Main component ─────────────────────────────────────────────── */
export default function DocumentRegionViewer({ fileId, docType = 'UNKNOWN', fileName, onClose }) {
  const [regions,    setRegions]  = useState([])
  const [loading,    setLoading]  = useState(true)
  const [error,      setError]    = useState(null)
  const [imgSize,    setImgSize]  = useState({ w: 0, h: 0 })
  const [hoveredIdx, setHovered]  = useState(null)
  const [activeIdx,  setActive]   = useState(null)
  const imgRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setRegions([])
    getDocumentRegions(fileId, docType)
      .then(data => { if (!cancelled) { setRegions(data.regions || []); setLoading(false) } })
      .catch(err  => { if (!cancelled) { setError(err.message); setLoading(false) } })
    return () => { cancelled = true }
  }, [fileId, docType])

  const handleImgLoad = useCallback(() => {
    if (imgRef.current) {
      setImgSize({ w: imgRef.current.offsetWidth, h: imgRef.current.offsetHeight })
    }
  }, [])

  // Recompute if window resizes
  useEffect(() => {
    const obs = new ResizeObserver(() => {
      if (imgRef.current) {
        setImgSize({ w: imgRef.current.offsetWidth, h: imgRef.current.offsetHeight })
      }
    })
    if (imgRef.current) obs.observe(imgRef.current)
    return () => obs.disconnect()
  }, [regions])

  // Escape to close
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  function bboxStyle(bbox) {
    if (!bbox || imgSize.w === 0 || imgSize.h === 0) return { display: 'none' }
    const [y1, x1, y2, x2] = bbox
    return {
      top:    `${(y1 / 1000) * imgSize.h}px`,
      left:   `${(x1 / 1000) * imgSize.w}px`,
      width:  `${((x2 - x1) / 1000) * imgSize.w}px`,
      height: `${((y2 - y1) / 1000) * imgSize.h}px`,
    }
  }

  const showSidebar = !loading && !error && regions.length > 0

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 200,
        background: 'rgba(5,1,4,0.92)', backdropFilter: 'blur(8px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#150410', border: '1px solid #340926', borderRadius: 16,
          width: 'min(96vw, 1140px)', maxHeight: '92vh',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          boxShadow: '0 40px 100px rgba(0,0,0,0.85), 0 0 0 1px rgba(70,9,50,0.5)',
        }}
        onClick={e => e.stopPropagation()}
      >

        {/* ── Modal header ─────────────────────────────────────── */}
        <div style={{
          padding: '12px 18px', borderBottom: '1px solid #2c0b21', flexShrink: 0,
          background: 'rgba(0,0,0,0.25)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* Icon */}
            <span style={{
              fontSize: 16, background: 'rgba(123,64,103,0.2)',
              border: '1px solid #460932', borderRadius: 8, padding: '4px 8px',
            }}>
              &#9681;
            </span>
            <div>
              <span style={{ fontWeight: 700, fontSize: 14, color: '#d8c5d1' }}>
                Extracted Regions
              </span>
              <span style={{ fontSize: 12, color: '#7b5068', marginLeft: 8 }}>
                {fileName}
              </span>
              <span style={{
                marginLeft: 8, fontSize: 10, padding: '2px 8px', borderRadius: 99,
                background: 'rgba(190,160,179,0.1)', border: '1px solid #460932',
                color: '#bea0b3', fontWeight: 700, textTransform: 'uppercase',
              }}>
                {docType}
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {!loading && !error && (
              <span style={{ fontSize: 12, color: '#7b5068' }}>
                {regions.length} region{regions.length !== 1 ? 's' : ''} detected
              </span>
            )}
            {/* Legend pills */}
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
              {CAT_ORDER.filter(c => regions.some(r => r.category === c)).map(cat => (
                <span key={cat} style={{
                  fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 99,
                  background: `${colorFor(cat)}18`, border: `1px solid ${colorFor(cat)}44`,
                  color: colorFor(cat), textTransform: 'uppercase', letterSpacing: '0.06em',
                }}>
                  {cat}
                </span>
              ))}
            </div>

            <button
              onClick={onClose}
              title="Close (Esc)"
              style={{
                background: 'rgba(255,255,255,0.04)', border: '1px solid #340926',
                borderRadius: 8, color: '#9e708c', cursor: 'pointer',
                fontSize: 15, padding: '5px 10px', lineHeight: 1,
                transition: 'color 0.12s, background 0.12s',
              }}
              onMouseEnter={e => { e.currentTarget.style.color = '#d8c5d1'; e.currentTarget.style.background = 'rgba(255,255,255,0.08)' }}
              onMouseLeave={e => { e.currentTarget.style.color = '#9e708c'; e.currentTarget.style.background = 'rgba(255,255,255,0.04)' }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* ── Body ─────────────────────────────────────────────── */}
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden', minHeight: 0 }}>

          {/* Image pane */}
          <div style={{
            flex: 1, overflow: 'auto', padding: 16, background: '#0b020a',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
            scrollbarWidth: 'thin', scrollbarColor: '#340926 #0b020a',
          }}>
            <StatusPane loading={loading} error={error} count={regions.length} />

            {!loading && !error && (
              <div style={{ position: 'relative', display: 'inline-block', lineHeight: 0 }}>
                <img
                  ref={imgRef}
                  src={getFileUrl(fileId)}
                  alt={fileName}
                  onLoad={handleImgLoad}
                  style={{
                    maxWidth: '100%', display: 'block', borderRadius: 6,
                    boxShadow: '0 4px 24px rgba(0,0,0,0.6)',
                  }}
                />

                {/* Bounding box overlays */}
                {imgSize.w > 0 && regions.map((r, i) => {
                  const color   = colorFor(r.category)
                  const isActive = activeIdx  === i
                  const isHover  = hoveredIdx === i
                  const isLit    = isActive || isHover

                  return (
                    <div
                      key={i}
                      style={{
                        position: 'absolute',
                        ...bboxStyle(r.bbox),
                        border: `2px solid ${color}`,
                        background: isLit ? `${color}30` : `${color}12`,
                        borderRadius: 3,
                        cursor: 'pointer',
                        boxSizing: 'border-box',
                        transition: 'background 0.12s, border-color 0.12s',
                        zIndex: isLit ? 10 : 1,
                      }}
                      onMouseEnter={() => setHovered(i)}
                      onMouseLeave={() => setHovered(null)}
                      onClick={() => setActive(p => p === i ? null : i)}
                    >
                      {/* Field label — shown when hovered or active */}
                      {isLit && (
                        <div style={{
                          position: 'absolute',
                          top: -22, left: -2,
                          background: color,
                          color: '#fff',
                          fontSize: 10, fontWeight: 700,
                          padding: '2px 7px', borderRadius: 4,
                          whiteSpace: 'nowrap',
                          pointerEvents: 'none',
                          boxShadow: '0 2px 6px rgba(0,0,0,0.5)',
                          zIndex: 20,
                          maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis',
                        }}>
                          {r.field}{r.value ? `: ${r.value}` : ''}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Sidebar */}
          {showSidebar && (
            <RegionSidebar
              regions={regions}
              hoveredIdx={hoveredIdx}
              activeIdx={activeIdx}
              onHover={setHovered}
              onActivate={idx => setActive(p => p === idx ? null : idx)}
            />
          )}
        </div>

        {/* ── Footer ───────────────────────────────────────────── */}
        {!loading && !error && regions.length > 0 && (
          <div style={{
            padding: '8px 18px', borderTop: '1px solid #2c0b21', flexShrink: 0,
            background: 'rgba(0,0,0,0.15)',
            display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: '#5a2e4a',
          }}>
            <span>&#9729;</span>
            <span>Bounding boxes are generated by a separate Gemini call — not part of the claims pipeline.</span>
            <span style={{ marginLeft: 'auto' }}>Click a region to pin it · Hover to preview</span>
          </div>
        )}
      </div>
    </div>
  )
}
