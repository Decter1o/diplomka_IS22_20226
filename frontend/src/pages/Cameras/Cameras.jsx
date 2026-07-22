import { useEffect, useState } from 'react'
import VideoPlayer from './VideoPlayer'
import CameraDataTabs from './CameraDataTabs'
import AddCameraModal from './AddCameraModal'
import { useAuth } from '../../context/AuthContext'
import './Cameras.css'

const API = '/api'

export default function Cameras() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [cameras, setCameras] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [wsConnected, setWsConnected] = useState(false)
  const [liveEvent, setLiveEvent] = useState(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [deleting, setDeleting] = useState(null)

  const loadCameras = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API}/cameras`)
      const data = await response.json()
      setCameras(data.cameras || [])
      if (data.cameras?.length && !selectedId) {
        setSelectedId(data.cameras[0].camera_id)
      }
    } catch (err) {
      console.error('Error loading cameras:', err)
      setCameras([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCameras()
  }, [])

  const handleCameraAdded = (newCamera) => {
    setCameras(prev => [newCamera, ...prev])
    setSelectedId(newCamera.camera_id)
  }

  const handleDeleteCamera = async (cameraId) => {
    if (!confirm('Вы уверены что хотите удалить эту камеру?')) return

    setDeleting(cameraId)
    try {
      const response = await fetch(`${API}/cameras/${cameraId}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('Failed to delete camera')
      setCameras(prev => prev.filter(c => c.camera_id !== cameraId))
      if (selectedId === cameraId) {
        setSelectedId(cameras[0]?.camera_id || null)
      }
    } catch (err) {
      alert('Ошибка при удалении камеры: ' + err.message)
    } finally {
      setDeleting(null)
    }
  }

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/alerts')
    ws.onopen = () => setWsConnected(true)
    ws.onmessage = (event) => {
      try {
        setLiveEvent(JSON.parse(event.data))
      } catch (e) {
        console.error('WebSocket parse error:', e)
      }
    }
    ws.onerror = () => setWsConnected(false)
    ws.onclose = () => setWsConnected(false)
    return () => ws.close()
  }, [])

  const selected = cameras.find(c => c.camera_id === selectedId)

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h4 className="mb-0">Камеры</h4>
        {isAdmin && (
          <button
            className="btn btn-sm btn-primary"
            onClick={() => setShowAddModal(true)}
          >
            <i className="bi bi-plus-lg me-2"></i>
            Добавить камеру
          </button>
        )}
      </div>

      {!wsConnected && (
        <div className="alert alert-warning alert-sm mb-3 d-flex align-items-center gap-2">
          <i className="bi bi-exclamation-circle-fill"></i>
          <span>WebSocket отключен (live события недоступны)</span>
        </div>
      )}

      {loading && (
        <div className="text-center text-muted py-4">
          <div className="spinner-border spinner-border-sm me-2" />
          Загрузка...
        </div>
      )}

      {!loading && cameras.length === 0 && (
        <div className="alert alert-warning">Камеры не найдены.</div>
      )}

      {!loading && cameras.length > 0 && (
        <>
          <div className="camera-tabs mb-3">
            {cameras.map(cam => (
              <div key={cam.camera_id} className="camera-tab-wrapper">
                <button
                  onClick={() => setSelectedId(cam.camera_id)}
                  className={`camera-tab-btn${cam.camera_id === selectedId ? ' active' : ''}`}
                >
                  <i className={`bi ${cam.status ? 'bi-camera-video-fill' : 'bi-camera-video-off'} me-2`}></i>
                  <span>{cam.name}</span>
                  <small className="camera-tab-location">{cam.location}</small>
                </button>
                {isAdmin && (
                  <button
                    onClick={() => handleDeleteCamera(cam.camera_id)}
                    className="btn-delete-camera"
                    disabled={deleting === cam.camera_id}
                    title="Удалить камеру"
                  >
                    {deleting === cam.camera_id
                      ? <span className="spinner-border spinner-border-sm"></span>
                      : <i className="bi bi-x-lg"></i>}
                  </button>
                )}
              </div>
            ))}
          </div>

          {selected && (
            <div className="camera-content">
              <div className="camera-player-col">
                <div className="card shadow-sm h-100">
                  <div className="card-header d-flex align-items-center gap-2">
                    <i className="bi bi-camera-video-fill text-primary"></i>
                    <strong>{selected.name}</strong>
                    <span className="text-muted small ms-1">— {selected.location}</span>
                    <span className={`badge ms-auto ${selected.status ? 'bg-success' : 'bg-secondary'}`}>
                      {selected.status ? 'Активна' : 'Отключена'}
                    </span>
                  </div>
                  <div className="card-body p-0">
                    <VideoPlayer cameraName={selected.name} />
                  </div>
                </div>
              </div>
              <div className="camera-data-col">
                <CameraDataTabs
                  cameraId={selected.camera_id}
                  liveEvent={liveEvent}
                  wsConnected={wsConnected}
                />
              </div>
            </div>
          )}
        </>
      )}

      {isAdmin && (
        <AddCameraModal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          onCameraAdded={handleCameraAdded}
        />
      )}
    </div>
  )
}
