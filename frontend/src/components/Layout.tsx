import { NavLink, useNavigate } from 'react-router-dom'
import { clearAuth, getDisplayName, getUserId } from '../api'

export default function Layout({ children }: { children: React.ReactNode }) {
  const nav = useNavigate()

  function logout() {
    clearAuth()
    nav('/login')
  }

  const navItems = [
    { to: '/feed', label: 'Home', icon: '🏠' },
    { to: '/chats', label: 'Chats', icon: '💬' },
    { to: '/upload', label: 'Upload', icon: '📷' },
  ]

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1 className="logo">Social</h1>
        <div className="me">
          <div className="me-name">{getDisplayName() ?? '—'}</div>
          <div className="me-id">user #{getUserId()}</div>
        </div>
        <nav>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `nav-item${isActive ? ' active' : ''}`
              }
              end={item.to === '/feed'}
            >
              <span className="icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <button className="logout" onClick={logout}>
          Log out
        </button>
      </aside>
      <main className="content">{children}</main>
    </div>
  )
}