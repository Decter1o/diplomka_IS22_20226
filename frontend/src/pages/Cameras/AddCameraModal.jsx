import { useState } from 'react'
import { createPortal } from 'react-dom'
import './Cameras.css'

const API = '/api'

export default function AddCameraModal({ isOpen, onClose, onCameraAdded }) {
  const [formData, setFormData] = useState({
    name: '',
    location: '',
    rtsp_url: ''
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
    setError(null)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!formData.name.trim() || !formData.location.trim() || !formData.rtsp_url.trim()) {
      setError('Все поля обязательны')
      return
    }

    setLoading(true)
    try {
      const response = await fetch(`${API}/cameras`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      })

      if (!response.ok) {
        const errData = await response.json()
        throw new Error(errData.detail || 'Failed to add camera')
      }

      const newCamera = await response.json()
      setFormData({ name: '', location: '', rtsp_url: '' })
      onCameraAdded(newCamera)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  return createPortal(
    <div className="cam-modal-overlay" onClick={onClose}>
      <div className="cam-modal cam-modal-camera" onClick={e => e.stopPropagation()}>
        <div className="cam-modal-header">
          <h5 className="mb-0">Добавить камеру</h5>
          <button className="btn-close" onClick={onClose}></button>
        </div>
        <div className="cam-modal-body">
          {error && (
            <div className="alert alert-danger" role="alert">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="mb-3">
              <label htmlFor="name" className="form-label">Название камеры *</label>
              <input
                type="text"
                className="form-control"
                id="name"
                name="name"
                value={formData.name}
                onChange={handleChange}
                placeholder="Camera-01"
                disabled={loading}
              />
            </div>

            <div className="mb-3">
              <label htmlFor="location" className="form-label">Локация *</label>
              <input
                type="text"
                className="form-control"
                id="location"
                name="location"
                value={formData.location}
                onChange={handleChange}
                placeholder="ул. Толе би, метро"
                disabled={loading}
              />
            </div>

            <div className="mb-3">
              <label htmlFor="rtsp_url" className="form-label">RTSP URL *</label>
              <input
                type="text"
                className="form-control"
                id="rtsp_url"
                name="rtsp_url"
                value={formData.rtsp_url}
                onChange={handleChange}
                placeholder="rtsp://192.168.1.100:554/stream"
                disabled={loading}
              />
              <small className="text-muted">Пример: rtsp://192.168.1.100:554/stream</small>
            </div>

            <div className="d-flex gap-2 justify-content-end">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
                disabled={loading}
              >
                Отмена
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <span className="spinner-border spinner-border-sm me-2"></span>
                    Добавление...
                  </>
                ) : (
                  'Добавить'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>,
    document.body
  )
}
