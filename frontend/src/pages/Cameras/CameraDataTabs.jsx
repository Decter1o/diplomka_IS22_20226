import { useEffect, useState } from 'react'

const API = '/api'

const ALERT_TYPE_LABEL = {
  stolen: { label: 'Угон', cls: 'danger' },
  wanted: { label: 'Штрафник', cls: 'warning' },
}

function formatTime(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('ru-RU')
}

function PhotoThumb({ url, alt }) {
  if (!url) return <span className="text-muted">—</span>
  return (
    <a href={url} target="_blank" rel="noreferrer">
      <img src={url} alt={alt} className="plate-thumb" />
    </a>
  )
}

export default function CameraDataTabs({ cameraId, liveEvent, wsConnected }) {
  const [tab, setTab] = useState('detections')
  const [detections, setDetections] = useState([])
  const [alerts, setAlerts] = useState([])
  const [unknown, setUnknown] = useState([])
  const [loading, setLoading] = useState(false)

  // Загрузка данных при смене камеры
  useEffect(() => {
    if (!cameraId) return
    setLoading(true)

    Promise.all([
      fetch(`${API}/detections?camera_id=${cameraId}&limit=50`).then(r => r.json()),
      fetch(`${API}/alerts?camera_id=${cameraId}&limit=50`).then(r => r.json()),
      fetch(`${API}/unknown-plates?camera_id=${cameraId}&limit=50`).then(r => r.json()),
    ])
      .then(([det, alr, unk]) => {
        setDetections(det.detections || [])
        setAlerts(alr.alerts || [])
        setUnknown(unk.unknown_plates || [])
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [cameraId])

  // Слушание live событий
  useEffect(() => {
    if (!liveEvent || !wsConnected) return

    // Проверяем, относится ли событие к текущей камере
    const isSameCamera = liveEvent.camera === cameraId ||
                         (liveEvent.camera_name && liveEvent.camera_name === cameraId)

    if (!isSameCamera && liveEvent.camera) {
      return
    }

    if (liveEvent.event === 'alert') {
      // Новый алерт — добавляем в начало списка
      setAlerts(prev => {
        const newAlert = {
          id: liveEvent.alert_id,
          alert_type: liveEvent.alert_type,
          detection_id: liveEvent.detection_id,
          created_at: liveEvent.created_at,
          driver_id: liveEvent.driver_id || null,
          plate_id: liveEvent.plate_id || null,
        }
        return [newAlert, ...prev].slice(0, 50)
      })
    } else if (liveEvent.event === 'unknown_plate') {
      // Неизвестный номер — добавляем в начало списка
      setUnknown(prev => {
        const newUnknown = {
          id: `${Date.now()}`,
          plate_number: liveEvent.plate_number,
          timestamp: liveEvent.timestamp,
          camera_id: cameraId,
          plates_photo_url: liveEvent.plates_photo_url,
          full_photo_url: liveEvent.full_photo_url,
        }
        return [newUnknown, ...prev].slice(0, 50)
      })
    }
  }, [liveEvent, cameraId, wsConnected])

  return (
    <div className="card shadow-sm h-100">
      <div className="card-header p-0">
        <ul className="nav nav-tabs card-header-tabs ms-0">
          {[
            { key: 'detections', icon: 'bi-search', label: 'Детекции', count: detections.length },
            { key: 'alerts',     icon: 'bi-bell',   label: 'Алерты',   count: alerts.length },
            { key: 'unknown',    icon: 'bi-question-circle', label: 'Неизвестные', count: unknown.length },
          ].map(t => (
            <li className="nav-item" key={t.key}>
              <button
                className={`nav-link${tab === t.key ? ' active' : ''}`}
                onClick={() => setTab(t.key)}
              >
                <i className={`bi ${t.icon} me-1`}></i>
                {t.label}
                <span className={`badge ms-2 ${tab === t.key ? 'bg-primary' : 'bg-secondary'}`}>
                  {t.count}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="card-body p-0 overflow-auto" style={{ maxHeight: '420px' }}>
        {loading ? (
          <div className="text-center text-muted py-4">
            <div className="spinner-border spinner-border-sm me-2" />
            Загрузка...
          </div>
        ) : (
          <>
            {tab === 'detections' && (
              <DetectionsTable rows={detections} />
            )}
            {tab === 'alerts' && (
              <AlertsTable rows={alerts} />
            )}
            {tab === 'unknown' && (
              <UnknownTable rows={unknown} />
            )}
          </>
        )}
      </div>
    </div>
  )
}

function DetectionsTable({ rows }) {
  if (!rows.length) return <Empty text="Детекций нет" />
  return (
    <table className="table table-sm table-hover mb-0">
      <thead className="table-light sticky-top">
        <tr>
          <th>Время</th>
          <th>Номер</th>
          <th>Фото номера</th>
          <th>Фото кадра</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(d => (
          <tr key={d.detection_id}>
            <td className="text-nowrap small">{formatTime(d.detection_time)}</td>
            <td><span className="plate-badge">{d.plate_number || '—'}</span></td>
            <td><PhotoThumb url={d.plates_photo_url} alt="номер" /></td>
            <td><PhotoThumb url={d.full_photo_url} alt="кадр" /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function AlertsTable({ rows }) {
  if (!rows.length) return <Empty text="Алертов нет" />
  return (
    <table className="table table-sm table-hover mb-0">
      <thead className="table-light sticky-top">
        <tr>
          <th>Время</th>
          <th>Тип</th>
          <th>Detection ID</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(a => {
          const t = ALERT_TYPE_LABEL[a.alert_type] || { label: a.alert_type, cls: 'secondary' }
          return (
            <tr key={a.id}>
              <td className="text-nowrap small">{formatTime(a.created_at)}</td>
              <td><span className={`badge bg-${t.cls}`}>{t.label}</span></td>
              <td className="small text-muted font-monospace">{a.detection_id?.slice(0, 8)}…</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function UnknownTable({ rows }) {
  if (!rows.length) return <Empty text="Неизвестных номеров нет" />
  return (
    <table className="table table-sm table-hover mb-0">
      <thead className="table-light sticky-top">
        <tr>
          <th>Время</th>
          <th>Номер</th>
          <th>Фото номера</th>
          <th>Фото кадра</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(u => (
          <tr key={u.id}>
            <td className="text-nowrap small">{formatTime(u.timestamp)}</td>
            <td><span className="plate-badge">{u.plate_number}</span></td>
            <td><PhotoThumb url={u.plates_photo_url} alt="номер" /></td>
            <td><PhotoThumb url={u.full_photo_url} alt="кадр" /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Empty({ text }) {
  return (
    <div className="text-center text-muted py-4">
      <i className="bi bi-inbox fs-4 d-block mb-1"></i>
      {text}
    </div>
  )
}
