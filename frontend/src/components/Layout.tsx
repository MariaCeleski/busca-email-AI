/**
 * Layout component — barra de navegação e wrapper da aplicação.
 * Navegação em português com links para todas as páginas do sistema.
 */

import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export function Layout() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/auth', { replace: true })
  }

  return (
    <div className="app-layout">
      <nav className="navbar">
        <div className="navbar-inner">
          <div className="nav-brand">
            <span className="nav-logo">🤖</span>
            <span className="nav-brand-text">AI Email Agent</span>
          </div>
          <div className="nav-links">
            <NavLink to="/" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'} end>
              📊 Painel
            </NavLink>
            <NavLink to="/review" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              ⚠️ Revisão
            </NavLink>
            <NavLink to="/feedback" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              🧠 Feedback
            </NavLink>
            <NavLink to="/settings" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              ⚙️ Configurações
            </NavLink>
            <button onClick={handleLogout} className="btn btn-secondary btn-sm nav-logout">
              Sair
            </button>
          </div>
        </div>
      </nav>
      <main className="main-content">
        <Outlet />
      </main>
      <footer className="app-footer">
        <span>AI Email Agent © 2025 — Sistema Multi-Agente com LangGraph</span>
      </footer>
    </div>
  )
}
