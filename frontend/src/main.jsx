import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap-icons/font/bootstrap-icons.css'
import './index.css'
import App from './App.jsx'

// Перехватываем fetch: автоматически добавляем Authorization для /api/*
// и при получении 401 — сбрасываем сессию и редиректим на /login
const _origFetch = window.fetch.bind(window)
window.fetch = function (url, init = {}) {
  const urlStr = typeof url === 'string' ? url : String(url)
  const isApi = urlStr.includes('/api/')
  const isAuthEndpoint = urlStr.includes('/api/auth/')

  if (isApi && !isAuthEndpoint) {
    const token = localStorage.getItem('access_token')
    if (token) {
      init = {
        ...init,
        headers: { Authorization: `Bearer ${token}`, ...init.headers },
      }
    }
  }

  return _origFetch(url, init).then(res => {
    if (res.status === 401 && !isAuthEndpoint && window.location.pathname !== '/login') {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return res
  })
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
