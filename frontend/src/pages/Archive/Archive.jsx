import { useState, useEffect } from 'react'
import './Archive.css'

const API = '/api'

function formatTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('ru-RU')
}

function formatDuration(sec) {
  if (!sec) return '—'
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m} мин ${s} сек`
}

function formatBytes(bytes) {
  if (!bytes) return '—'
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
}

export default function Archive() {
  const [cameras, setCameras] = useState([])
  const [camera, setCamera] = useState('')
  const [startDate, setStartDate] = useState('')
  const [startTime, setStartTime] = useState('00:00')
  const [endDate, setEndDate] = useState('')
  const [endTime, setEndTime] = useState('23:59')
  const [recordings, setRecordings] = useState([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  useEffect(() => {
    fetch(`${API}/recordings/cameras`)
      .then(r => r.json())
      .then(d => {
        const list = d.cameras || []
        setCameras(list)
        if (list.length) setCamera(list[0])
      })
      .catch(() => {})
  }, [])

  const handleSearch = async () => {
    if (!camera) return
    setLoading(true)
    setSearched(true)
    try {
      const params = new URLSearchParams({ camera, limit: 500 })
      if (startDate) params.set('start', `${startDate}T${startTime}:00`)
      if (endDate) params.set('end', `${endDate}T${endTime}:59`)
      const r = await fetch(`${API}/recordings?${params}`)
      const d = await r.json()
      setRecordings(d.recordings || [])
    } catch {
      setRecordings([])
    } finally {
      setLoading(false)
    }
  }

  const handleDownloadRange = () => {
    if (!camera || !startDate || !endDate) return
    const start = `${startDate}T${startTime}:00`
    const end = `${endDate}T${endTime}:59`
    const params = new URLSearchParams({ camera, start, end })
    window.open(`${API}/recordings/download?${params}`, '_blank')
  }

  const canDownloadRange = camera && startDate && endDate

  return (
    <div className="archive-page">
      <h1>Архив записей</h1>

      <div className="archive-filters">
        <div className="filter-group">
          <label>Камера</label>
          <select value={camera} onChange={e => setCamera(e.target.value)}>
            {cameras.length === 0 && <option value="">Нет камер</option>}
            {cameras.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <div className="filter-group">
          <label>С</label>
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
          <input type="time" value={startTime} onChange={e => setStartTime(e.target.value)} />
        </div>

        <div className="filter-group">
          <label>По</label>
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
          <input type="time" value={endTime} onChange={e => setEndTime(e.target.value)} />
        </div>

        <button className="btn-archive-search" onClick={handleSearch} disabled={!camera}>
          <i className="bi bi-search me-1"></i>Найти
        </button>

        {canDownloadRange && (
          <button className="btn-archive-dl-range" onClick={handleDownloadRange}>
            <i className="bi bi-scissors me-1"></i>Скачать отрезок
          </button>
        )}
      </div>

      {loading && <div className="archive-status">Загрузка...</div>}

      {!loading && searched && recordings.length === 0 && (
        <div className="archive-status">Записей не найдено</div>
      )}

      {!loading && recordings.length > 0 && (
        <div className="archive-info">
          Найдено сегментов: <strong>{recordings.length}</strong>
        </div>
      )}

      {!loading && recordings.length > 0 && (
        <div className="table-container">
          <table className="archive-table">
            <thead>
              <tr>
                <th>Начало</th>
                <th>Конец</th>
                <th>Длительность</th>
                <th>Размер</th>
                <th className="text-center">Скачать</th>
              </tr>
            </thead>
            <tbody>
              {recordings.map(r => (
                <tr key={r.id}>
                  <td>{formatTime(r.started_at)}</td>
                  <td>{formatTime(r.ended_at)}</td>
                  <td>{formatDuration(r.duration_sec)}</td>
                  <td>{formatBytes(r.file_size)}</td>
                  <td className="text-center">
                    <a
                      href={r.minio_url}
                      target="_blank"
                      rel="noreferrer"
                      className="btn-archive-dl"
                      title="Скачать сегмент"
                    >
                      <i className="bi bi-download"></i>
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
