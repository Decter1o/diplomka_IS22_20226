import { useEffect, useState } from 'react'
import AlertsTable from './AlertsTable'
import AlertsPagination from './AlertsPagination'
import './Alerts.css'

const API = '/api'
const ROWS_PER_PAGE = 20

const ALERT_TYPES = {
  '': 'Все',
  'wanted': 'Штрафники',
  'stolen': 'Угоны',
}

export default function Alerts() {
  const [allAlerts, setAllAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterType, setFilterType] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [wsConnected, setWsConnected] = useState(false)
  const [liveEvent, setLiveEvent] = useState(null)
  const [exportLoading, setExportLoading] = useState(false)
  const [dateRange, setDateRange] = useState({
    startDate: new Date().toISOString().split('T')[0],
    endDate: new Date().toISOString().split('T')[0],
  })

  // Загрузка обогащённых алертов
  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams({ limit: '500' })
    if (filterType) params.set('alert_type', filterType)
    const url = `${API}/alerts/enriched?${params.toString()}`

    fetch(url)
      .then(r => r.json())
      .then(data => {
        setAllAlerts(data.alerts || [])
        setCurrentPage(1)
      })
      .catch(() => setAllAlerts([]))
      .finally(() => setLoading(false))
  }, [filterType])

  // WebSocket для live событий
  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.host}/api/ws/alerts`)

    ws.onopen = () => setWsConnected(true)
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setLiveEvent(data)
      } catch (e) {
        console.error('WebSocket parse error:', e)
      }
    }
    ws.onerror = () => setWsConnected(false)
    ws.onclose = () => setWsConnected(false)

    return () => ws.close()
  }, [])

  // Слушание live событий — добавляем новые алерты в начало
  useEffect(() => {
    if (!liveEvent || !wsConnected) return

    if (liveEvent.event === 'alert') {
      // Проверяем фильтр типа
      if (filterType && liveEvent.alert_type !== filterType) {
        return
      }

      // Добавляем в начало (потом его обогатим при следующей загрузке)
      setAllAlerts(prev => [
        {
          id: liveEvent.alert_id,
          alert_type: liveEvent.alert_type === 'stolen' ? 'Угон' : 'Штрафник',
          created_at: liveEvent.created_at,
          plate_number: liveEvent.plate_number,
          driver_name: 'N/A',
          camera_name: liveEvent.camera,
          camera_location: '',
        },
        ...prev,
      ].slice(0, 500))
    }
  }, [liveEvent, wsConnected, filterType])

  // Фильтрация по поисковой строке
  const filtered = allAlerts.filter(a => {
    if (!searchQuery.trim()) return true
    const query = searchQuery.toLowerCase()
    return (
      a.plate_number?.toLowerCase().includes(query) ||
      a.driver_name?.toLowerCase().includes(query) ||
      a.camera_name?.toLowerCase().includes(query)
    )
  })

  // Пагинация
  const totalPages = Math.ceil(filtered.length / ROWS_PER_PAGE)
  const startIdx = (currentPage - 1) * ROWS_PER_PAGE
  const endIdx = startIdx + ROWS_PER_PAGE
  const paginatedData = filtered.slice(startIdx, endIdx)

  const handleSearch = (e) => {
    setSearchQuery(e.target.value)
    setCurrentPage(1)
  }

  const handlePageChange = (page) => {
    setCurrentPage(Math.max(1, Math.min(page, totalPages)))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleExport = async (format) => {
    setExportLoading(true)
    try {
      const params = new URLSearchParams({
        start_date: dateRange.startDate,
        end_date: dateRange.endDate,
        format: format,
      })
      if (filterType) params.set('alert_type', filterType)
      const url = `${API}/alerts/export?${params.toString()}`

      const response = await fetch(url)
      if (!response.ok) {
        const error = await response.json()
        alert(`Ошибка: ${error.detail}`)
        return
      }

      const blob = await response.blob()
      const downloadUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = `alerts_${dateRange.startDate}_${dateRange.endDate}.${format}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(downloadUrl)
    } catch (error) {
      console.error('Export error:', error)
      alert('Ошибка при выгрузке')
    } finally {
      setExportLoading(false)
    }
  }

  return (
    <div>
      <h4 className="mb-3">Алерты</h4>

      {!wsConnected && (
        <div className="alert alert-warning alert-sm mb-3 d-flex align-items-center gap-2">
          <i className="bi bi-exclamation-circle-fill"></i>
          <span>WebSocket отключен (live события недоступны)</span>
        </div>
      )}

      {/* Фильтры и поиск */}
      <div className="filters-section mb-3">
        <div className="row g-2 mb-3">
          <div className="col-md-4">
            <input
              type="text"
              className="form-control"
              placeholder="Поиск по номеру, водителю, камере..."
              value={searchQuery}
              onChange={handleSearch}
            />
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={filterType}
              onChange={(e) => {
                setFilterType(e.target.value)
                setCurrentPage(1)
              }}
            >
              {Object.entries(ALERT_TYPES).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Выгрузка */}
        <div className="export-section p-3 bg-light rounded mb-3">
          <div className="row align-items-end g-2">
            <div className="col-md-3">
              <label className="form-label mb-1 small">От</label>
              <input
                type="date"
                className="form-control form-control-sm"
                value={dateRange.startDate}
                onChange={(e) => setDateRange({ ...dateRange, startDate: e.target.value })}
              />
            </div>
            <div className="col-md-3">
              <label className="form-label mb-1 small">До</label>
              <input
                type="date"
                className="form-control form-control-sm"
                value={dateRange.endDate}
                onChange={(e) => setDateRange({ ...dateRange, endDate: e.target.value })}
              />
            </div>
            <div className="col-md-6">
              <button
                className="btn btn-sm btn-outline-primary me-2"
                onClick={() => handleExport('csv')}
                disabled={exportLoading}
              >
                <i className="bi bi-download me-1"></i>
                CSV
              </button>
              <button
                className="btn btn-sm btn-outline-success"
                onClick={() => handleExport('xlsx')}
                disabled={exportLoading}
              >
                <i className="bi bi-download me-1"></i>
                Excel
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Таблица */}
      {loading ? (
        <div className="text-center text-muted py-5">
          <div className="spinner-border spinner-border-sm me-2" />
          Загрузка...
        </div>
      ) : filtered.length === 0 ? (
        <div className="alert alert-info">
          {searchQuery ? 'Алерты не найдены по вашему поиску.' : 'Алерты отсутствуют.'}
        </div>
      ) : (
        <>
          {/* Результаты */}
          <div className="card shadow-sm mb-3">
            <div className="card-header bg-light text-muted small d-flex justify-content-between align-items-center">
              <span>
                Показано <strong>{paginatedData.length}</strong> из <strong>{filtered.length}</strong> алертов
              </span>
              {searchQuery && (
                <span className="badge bg-primary">Поиск: {searchQuery}</span>
              )}
            </div>
            <div className="card-body p-0">
              <AlertsTable rows={paginatedData} />
            </div>
          </div>

          {/* Пагинация */}
          {totalPages > 1 && (
            <AlertsPagination
              currentPage={currentPage}
              totalPages={totalPages}
              onPageChange={handlePageChange}
            />
          )}
        </>
      )}
    </div>
  )
}
