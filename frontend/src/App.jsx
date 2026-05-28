import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import SubmitPage from './pages/SubmitPage'
import HistoryPage from './pages/HistoryPage'
import EvalPage from './pages/EvalPage'

/* Plum wordmark + shield icon */
function PlumLogo() {
  return (
    <div className="flex items-center gap-2.5">
      {/* Shield icon */}
      <svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden>
        <rect width="30" height="30" rx="8" fill="#7C5CFC" />
        <path
          d="M15 4.5C15 4.5 8 7.2 8 13.5C8 19.2 11.5 23.2 15 25.5C18.5 23.2 22 19.2 22 13.5C22 7.2 15 4.5 15 4.5Z"
          fill="white"
          fillOpacity="0.95"
        />
        <path
          d="M15 9.5C15 9.5 11 11.3 11 14.8C11 17.9 13 20.2 15 21.5C17 20.2 19 17.9 19 14.8C19 11.3 15 9.5 15 9.5Z"
          fill="#7C5CFC"
        />
      </svg>

      {/* Wordmark */}
      <div className="flex items-baseline gap-1.5">
        <span className="text-white font-bold text-lg tracking-tight leading-none">plum</span>
        <span
          className="text-xs font-medium px-1.5 py-0.5 rounded"
          style={{ background: 'rgba(124,92,252,0.25)', color: '#B8A9FF', border: '1px solid rgba(124,92,252,0.4)' }}
        >
          Claims Engine
        </span>
      </div>
    </div>
  )
}

function BackendStatus() {
  return (
    <div className="flex items-center gap-1.5 text-xs" style={{ color: '#8B87B5' }}>
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
      API connected
    </div>
  )
}

function Header() {
  const base = 'px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all duration-150'
  const linkClass = ({ isActive }) =>
    isActive
      ? `${base} text-white`
      : `${base} hover:text-plum-300`

  const activeStyle = { background: 'rgba(124,92,252,0.2)', color: '#B8A9FF', border: '1px solid rgba(124,92,252,0.35)' }
  const inactiveStyle = { color: '#8B87B5', border: '1px solid transparent' }

  return (
    <header
      style={{ background: 'linear-gradient(180deg, #110E28 0%, #0C0A1C 100%)', borderBottom: '1px solid #2A2550' }}
      className="sticky top-0 z-50"
    >
      <div className="max-w-screen-2xl mx-auto px-5 h-14 flex items-center gap-6">
        <PlumLogo />

        <nav className="flex gap-1">
          {[
            { to: '/', label: 'Submit Claim', end: true },
            { to: '/history', label: 'History', end: false },
            { to: '/eval', label: 'Eval Report', end: false },
          ].map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end}>
              {({ isActive }) => (
                <span
                  className={`${base} cursor-pointer`}
                  style={isActive ? activeStyle : inactiveStyle}
                >
                  {label}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-4">
          <BackendStatus />
          <a
            href="https://www.plumhq.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs transition-colors"
            style={{ color: '#3D3668' }}
          >
            plumhq.com ↗
          </a>
        </div>
      </div>
    </header>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen" style={{ background: '#0C0A1C', color: '#F2F0FF' }}>
        <Header />
        <Routes>
          <Route path="/"            element={<SubmitPage />} />
          <Route path="/claims/:id"  element={<SubmitPage />} />
          <Route path="/history"     element={<HistoryPage />} />
          <Route path="/eval"        element={<EvalPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
