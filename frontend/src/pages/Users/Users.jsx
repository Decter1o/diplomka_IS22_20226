import { useEffect, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import './Users.css'

const API = '/api'

const ROLE_LABELS = { admin: 'Администратор', operator: 'Оператор' }
const ROLES = ['admin', 'operator']

const EMPTY_FORM = { username: '', password: '', role: 'operator' }

export default function Users() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  const load = () => {
    setLoading(true)
    fetch(`${API}/users`)
      .then(r => r.json())
      .then(data => setUsers(data.users || []))
      .catch(() => setUsers([]))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleDelete = async (userId, username) => {
    if (!window.confirm(`Удалить пользователя «${username}»?`)) return
    setDeleting(userId)
    try {
      const res = await fetch(`${API}/users/${userId}`, { method: 'DELETE' })
      if (!res.ok) {
        const err = await res.json()
        alert(err.detail || 'Ошибка при удалении')
        return
      }
      load()
    } finally {
      setDeleting(null)
    }
  }

  const handleFormChange = (e) => {
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }))
    setFormError('')
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!form.username.trim() || !form.password.trim()) {
      setFormError('Логин и пароль обязательны')
      return
    }
    setSaving(true)
    setFormError('')
    try {
      const res = await fetch(`${API}/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!res.ok) {
        const err = await res.json()
        setFormError(err.detail || 'Ошибка при создании')
        return
      }
      setForm(EMPTY_FORM)
      setShowForm(false)
      load()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4 className="mb-0">
          <i className="bi bi-people-fill me-2 text-primary"></i>
          Пользователи
        </h4>
        <button
          className="btn btn-sm btn-primary"
          onClick={() => { setShowForm(v => !v); setFormError('') }}
        >
          <i className={`bi ${showForm ? 'bi-x-lg' : 'bi-plus-lg'} me-1`}></i>
          {showForm ? 'Закрыть' : 'Добавить пользователя'}
        </button>
      </div>

      {/* Форма создания */}
      {showForm && (
        <div className="card shadow-sm mb-4">
          <div className="card-header bg-light fw-semibold">
            <i className="bi bi-person-plus me-2"></i>
            Новый пользователь
          </div>
          <div className="card-body">
            <form onSubmit={handleCreate} className="row g-3 align-items-end">
              {formError && (
                <div className="col-12">
                  <div className="alert alert-danger py-2 mb-0">{formError}</div>
                </div>
              )}
              <div className="col-md-4">
                <label className="form-label">Логин</label>
                <input
                  type="text"
                  className="form-control"
                  name="username"
                  value={form.username}
                  onChange={handleFormChange}
                  placeholder="login"
                  disabled={saving}
                  autoFocus
                />
              </div>
              <div className="col-md-4">
                <label className="form-label">Пароль</label>
                <input
                  type="password"
                  className="form-control"
                  name="password"
                  value={form.password}
                  onChange={handleFormChange}
                  placeholder="••••••••"
                  disabled={saving}
                />
              </div>
              <div className="col-md-2">
                <label className="form-label">Роль</label>
                <select
                  className="form-select"
                  name="role"
                  value={form.role}
                  onChange={handleFormChange}
                  disabled={saving}
                >
                  {ROLES.map(r => (
                    <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                  ))}
                </select>
              </div>
              <div className="col-md-2">
                <button type="submit" className="btn btn-primary w-100" disabled={saving}>
                  {saving
                    ? <span className="spinner-border spinner-border-sm"></span>
                    : <><i className="bi bi-check-lg me-1"></i>Создать</>
                  }
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Таблица пользователей */}
      <div className="card shadow-sm">
        <div className="card-header d-flex align-items-center gap-2">
          <span className="badge bg-primary">{users.length}</span>
          <span className="small text-muted">пользователей в системе</span>
        </div>
        <div className="card-body p-0">
          {loading ? (
            <div className="text-center py-5">
              <span className="spinner-border text-primary"></span>
            </div>
          ) : users.length === 0 ? (
            <div className="text-center text-muted py-5">Нет пользователей</div>
          ) : (
            <table className="table table-hover mb-0">
              <thead className="table-light">
                <tr>
                  <th>Логин</th>
                  <th>Роль</th>
                  <th>Статус</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.uuid} className={u.uuid === currentUser?.uuid ? 'table-active' : ''}>
                    <td>
                      <i className="bi bi-person me-2 text-muted"></i>
                      <strong>{u.username}</strong>
                      {u.uuid === currentUser?.uuid && (
                        <span className="badge bg-secondary ms-2">вы</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge ${u.role === 'admin' ? 'bg-danger' : 'bg-info text-dark'}`}>
                        {ROLE_LABELS[u.role] ?? u.role}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${u.is_active ? 'bg-success' : 'bg-secondary'}`}>
                        {u.is_active ? 'Активен' : 'Отключён'}
                      </span>
                    </td>
                    <td className="text-end">
                      <button
                        className="btn btn-outline-danger btn-sm"
                        onClick={() => handleDelete(u.uuid, u.username)}
                        disabled={deleting === u.uuid || u.uuid === currentUser?.uuid}
                        title={u.uuid === currentUser?.uuid ? 'Нельзя удалить себя' : 'Удалить'}
                      >
                        {deleting === u.uuid
                          ? <span className="spinner-border spinner-border-sm"></span>
                          : <i className="bi bi-trash"></i>}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
