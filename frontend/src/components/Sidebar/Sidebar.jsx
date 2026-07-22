import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import './Sidebar.css'

const NAV_ITEMS = [
  { to: '/cameras',         icon: 'bi-camera-video',          label: 'Камеры' },
  { to: '/detections',      icon: 'bi-search',                label: 'Детекции' },
  { to: '/alerts',          icon: 'bi-bell',                  label: 'Алерты' },
  { to: '/stolen-vehicles', icon: 'bi-shield-exclamation',    label: 'Угнанные ТС' },
  { to: '/unknown-plates',  icon: 'bi-question-circle',       label: 'Неизв. номера' },
  { to: '/video-upload',    icon: 'bi-cloud-upload',          label: 'Загрузка видео' },
  { to: '/archive',         icon: 'bi-archive',               label: 'Архив записей' },
  { to: '/users',           icon: 'bi-people',                label: 'Пользователи', adminOnly: true },
]

const ROLE_LABELS = { admin: 'Администратор', operator: 'Оператор' }

export default function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const visibleItems = NAV_ITEMS.filter(item => !item.adminOnly || user?.role === 'admin')

  return (
    <aside className="sidebar d-flex flex-column">
      <div className="sidebar-brand">
        <i className="bi bi-camera2 me-2"></i>
        <span>SmartCamera</span>
      </div>

      <nav className="sidebar-nav flex-grow-1">
        <ul className="list-unstyled mb-0">
          {visibleItems.map(({ to, icon, label }) => (
            <li key={to}>
              <NavLink
                to={to}
                className={({ isActive }) =>
                  `sidebar-link${isActive ? ' active' : ''}`
                }
              >
                <i className={`bi ${icon}`}></i>
                <span>{label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-user">
          <i className="bi bi-person-circle sidebar-user-icon"></i>
          <div className="sidebar-user-info">
            <span className="sidebar-user-name">{user?.username}</span>
            <span className="sidebar-user-role">{ROLE_LABELS[user?.role] ?? user?.role}</span>
          </div>
        </div>
        <button className="sidebar-logout" onClick={handleLogout} title="Выйти">
          <i className="bi bi-box-arrow-right"></i>
        </button>
      </div>
    </aside>
  )
}
