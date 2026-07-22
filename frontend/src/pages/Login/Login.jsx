import { useState } from 'react'
import { useNavigate, Navigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import './Login.css'

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (user) return <Navigate to="/cameras" replace />

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      navigate('/cameras', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <i className="bi bi-camera2 login-logo"></i>
          <h4 className="login-title">SmartCamera</h4>
          <p className="login-subtitle">Система видеонаблюдения</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          {error && (
            <div className="alert alert-danger d-flex align-items-center gap-2 py-2">
              <i className="bi bi-exclamation-circle-fill"></i>
              <span>{error}</span>
            </div>
          )}

          <div className="mb-3">
            <label htmlFor="username" className="form-label">Логин</label>
            <div className="input-group">
              <span className="input-group-text">
                <i className="bi bi-person"></i>
              </span>
              <input
                id="username"
                type="text"
                className="form-control"
                placeholder="Введите логин"
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoFocus
                required
                disabled={loading}
              />
            </div>
          </div>

          <div className="mb-4">
            <label htmlFor="password" className="form-label">Пароль</label>
            <div className="input-group">
              <span className="input-group-text">
                <i className="bi bi-lock"></i>
              </span>
              <input
                id="password"
                type="password"
                className="form-control"
                placeholder="Введите пароль"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                disabled={loading}
              />
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary w-100"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner-border spinner-border-sm me-2"></span>
                Вход...
              </>
            ) : (
              <>
                <i className="bi bi-box-arrow-in-right me-2"></i>
                Войти
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
