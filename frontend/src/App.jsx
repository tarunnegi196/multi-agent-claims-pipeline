import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import SubmitPage  from './pages/SubmitPage'
import HistoryPage from './pages/HistoryPage'
import EvalPage    from './pages/EvalPage'

/* ── Navbar ──────────────────────────────────────────────────────── */
function useApiHealth() {
  const [status, setStatus] = useState('checking') // 'checking' | 'ok' | 'down'

  useEffect(() => {
    let cancelled = false
    async function check() {
      try {
        const res = await fetch('/health', { signal: AbortSignal.timeout(3000) })
        if (!cancelled) setStatus(res.ok ? 'ok' : 'down')
      } catch {
        if (!cancelled) setStatus('down')
      }
    }
    check()
    const id = setInterval(check, 15000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  return status
}

function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false)
  const apiStatus = useApiHealth()

  const navLinkStyle = ({ isActive }) => ({
    fontSize: '1.25rem',
    fontWeight: 500,
    color: isActive ? '#ff4052' : '#570e40',
    textDecoration: 'none',
    padding: '6px 14px',
    borderRadius: 30,
    background: isActive ? 'rgba(255,64,82,0.08)' : 'transparent',
    transition: 'color 0.2s ease, background 0.2s ease, transform 0.18s ease, box-shadow 0.18s ease',
    whiteSpace: 'nowrap',
  })

  return (
    <header style={{
      background: '#fffaf2',
      borderBottom: '1px solid #ced5dd',
      position: 'sticky',
      top: 0,
      zIndex: 100,
    }}>
      <div style={{
        maxWidth: 1200,
        margin: '0 auto',
        padding: '0 20px',
        height: 56,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 24,
      }}>
        {/* Logo — href="/" stays on site, no external links */}
        <a href="/" className="plum-nav-logo-area" style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          textDecoration: 'none',
          flexShrink: 0,
          transition: 'opacity 25ms cubic-bezier(0.455, 0.03, 0.515, 0.955)',
        }}
          onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.85' }}
          onMouseLeave={(e) => { e.currentTarget.style.opacity = '1' }}
        >
          <img src="/plum_logo.png" alt="Plum" height="32"
            style={{ height: 32, width: 'auto', display: 'block' }} />
          <span style={{
            fontSize: 11,
            color: '#9e708c',
            borderLeft: '1px solid #ced5dd',
            paddingLeft: 10,
            marginLeft: 2,
            fontWeight: 500,
          }}>
            Claims Engine
          </span>
        </a>

        {/* Desktop nav */}
        <nav className="plum-nav-menu" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {[
            { to: '/',        label: 'New Claim',    end: true  },
            { to: '/history', label: 'History',      end: false },
            { to: '/eval',    label: 'Eval Report',  end: false },
          ].map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} style={navLinkStyle}
              onMouseEnter={(e) => {
                if (!e.currentTarget.style.background.includes('0.08')) e.currentTarget.style.background = 'rgba(87,14,64,0.06)'
                e.currentTarget.style.transform = 'translateY(-2px)'
                e.currentTarget.style.boxShadow = '0 4px 12px rgba(87,14,64,0.18)'
              }}
              onMouseLeave={(e) => {
                if (!e.currentTarget.style.background.includes('0.08')) e.currentTarget.style.background = 'transparent'
                e.currentTarget.style.transform = 'translateY(0)'
                e.currentTarget.style.boxShadow = 'none'
              }}>
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Right side: status + disclaimer ────────────────────────── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 24, marginLeft: 'auto' }}>
          <span style={{
            display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 500,
            color: apiStatus === 'ok' ? '#92bd33' : apiStatus === 'down' ? '#ff4052' : '#9e708c',
          }}>
            {apiStatus === 'down' ? (
              <span style={{ fontSize: 13, lineHeight: 1 }}>✕</span>
            ) : (
              <span style={{
                width: 7, height: 7, borderRadius: '50%', display: 'inline-block',
                background: apiStatus === 'ok' ? '#92bd33' : '#9e708c',
                animation: apiStatus === 'ok'
                  ? 'api-glow 2s ease-in-out infinite'
                  : 'pulse 1s ease-in-out infinite',
              }} />
            )}
            {apiStatus === 'ok' ? 'API ready' : apiStatus === 'down' ? 'Backend offline' : 'Connecting…'}
          </span>
          <span style={{ fontSize: 10, color: '#9e708c', borderLeft: '1px solid #ced5dd', paddingLeft: 24, fontStyle: 'italic' }}>
            Demo project · Not affiliated with Plum Benefits Insurance Brokers Pvt Ltd
          </span>
        </div>

        {/* Hamburger — visible ≤991px via CSS */}
        <button
          className="plum-nav-hamburger"
          onClick={() => setMenuOpen((v) => !v)}
          style={{
            display: 'none',
            fontSize: 24,
            padding: 18,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: '#570e40',
            lineHeight: 1,
          }}
        >
          {menuOpen ? '✕' : '☰'}
        </button>
      </div>

      {/* Mobile menu dropdown */}
      {menuOpen && (
        <div style={{
          background: '#fffaf2',
          borderTop: '1px solid #ced5dd',
          padding: '12px 20px',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}>
          {[
            { to: '/',        label: 'New Claim',    end: true  },
            { to: '/history', label: 'History',      end: false },
            { to: '/eval',    label: 'Eval Report',  end: false },
          ].map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} onClick={() => setMenuOpen(false)}
              style={navLinkStyle}>
              {label}
            </NavLink>
          ))}
        </div>
      )}
    </header>
  )
}

/* ── Root app ────────────────────────────────────────────────────── */
export default function App() {
  return (
    <BrowserRouter>
      <div style={{ minHeight: '100vh', background: '#11040d', color: '#fff', display: 'flex', flexDirection: 'column', fontFamily: 'Inter, Arial, sans-serif' }}>
        <Navbar />
        <div style={{ flex: 1 }}>
          <Routes>
            <Route path="/"           element={<SubmitPage />} />
            <Route path="/claims/:id" element={<SubmitPage />} />
            <Route path="/history"    element={<HistoryPage />} />
            <Route path="/eval"       element={<EvalPage />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
