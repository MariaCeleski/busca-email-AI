/**
 * Layout component — navigation bar and common page wrapper.
 */

import { NavLink, Outlet } from 'react-router-dom'

export function Layout() {
  return (
    <div className="app-layout">
      <nav className="navbar">
        <div className="nav-brand">
          <span className="nav-logo">📧</span>
          AI Email Agent
        </div>
        <div className="nav-links">
          <NavLink to="/" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'} end>
            Dashboard
          </NavLink>
          <NavLink to="/review" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Manual Review
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Settings
          </NavLink>
        </div>
      </nav>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
