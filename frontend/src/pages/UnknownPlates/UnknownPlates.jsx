import { useEffect, useState } from 'react'
import UnknownPlatesTable from './UnknownPlatesTable'
import PlateCheckModal from './PlateCheckModal'
import './UnknownPlates.css'

const API = '/api'
const ROWS_PER_PAGE = 20

const STATUS_FILTERS = {
  '': 'Все',
  'unrecognized': 'Не распознаны',
  'corrected': 'Исправлены',
  'not_in_db': 'Нет в базе'
}

const SOURCE_FILTERS = [
  { value: 'all',    label: 'Все',    icon: 'bi-collection' },
  { value: 'camera', label: 'Камеры', icon: 'bi-camera-video' },
  { value: 'video',  label: 'Видео',  icon: 'bi-film' },
]

export default function UnknownPlates() {
  const [allPlates, setAllPlates] = useState([])
  const [loading, setLoading] = useState(true)
  const [filterStatus, setFilterStatus] = useState('')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [currentPage, setCurrentPage] = useState(1)
  const [selectedPlate, setSelectedPlate] = useState(null)
  const today = new Date().toISOString().split('T')[0]
  const [dateRange, setDateRange] = useState({
    startDate: today,
    endDate: today,
  })

  useEffect(() => {
    setLoading(true)
    let _qp = new URLSearchParams()
    const url = `${API}/unknown-plates`
    _qp.set('limit', '500')
    if (filterStatus) _qp.set('status', filterStatus)
    if (dateRange.startDate) _qp.set('start_date', dateRange.startDate)
    if (dateRange.endDate) _qp.set('end_date', dateRange.endDate)

    fetch(_qp.toString() ? `${url}?${_qp.toString()}` : url)
      .then(r => r.json())
      .then(data => {
        setAllPlates(data.unknown_plates || [])
        setCurrentPage(1)
      })
      .catch(e => {
        console.error('Error loading unknown plates:', e)
        setAllPlates([])
      })
      .finally(() => setLoading(false))
  }, [filterStatus, dateRange])

  const visiblePlates = allPlates.filter(p => {
    if (sourceFilter === 'video')  return !!p.job_id
    if (sourceFilter === 'camera') return !!p.camera_id && !p.job_id
    return true
  })

  const startIdx = (currentPage - 1) * ROWS_PER_PAGE
  const paginatedPlates = visiblePlates.slice(startIdx, startIdx + ROWS_PER_PAGE)
  const totalPages = Math.ceil(visiblePlates.length / ROWS_PER_PAGE)

  const handlePlateClick = (plate) => {
    console.log('Plate clicked:', plate)
    setSelectedPlate(plate)
  }

  const handleModalClose = () => {
    setSelectedPlate(null)
  }

  const handleCorrected = () => {
    let _qp = new URLSearchParams()
    const url = `${API}/unknown-plates`
    _qp.set('limit', '500')
    if (filterStatus) _qp.set('status', filterStatus)
    if (dateRange.startDate) _qp.set('start_date', dateRange.startDate)
    if (dateRange.endDate) _qp.set('end_date', dateRange.endDate)

    fetch(_qp.toString() ? `${url}?${_qp.toString()}` : url)
      .then(r => r.json())
      .then(data => setAllPlates(data.unknown_plates || []))
      .catch(e => console.error('Error reloading:', e))

    handleModalClose()
  }

  return (
    <div className="unknown-plates-page">
      <h1>Неизвестные номера</h1>

      {/* Фильтр по источнику */}
      <div className="btn-group mb-3" role="group">
        {SOURCE_FILTERS.map(f => (
          <button
            key={f.value}
            type="button"
            className={`btn btn-sm ${sourceFilter === f.value ? 'btn-primary' : 'btn-outline-secondary'}`}
            onClick={() => { setSourceFilter(f.value); setCurrentPage(1) }}
          >
            <i className={`bi ${f.icon} me-1`} />
            {f.label}
          </button>
        ))}
      </div>

      <div className="filters">
        <div className="filter-group">
          <label>Статус:</label>
          <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
            {Object.entries(STATUS_FILTERS).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>От:</label>
          <input
            type="date"
            value={dateRange.startDate}
            onChange={e => setDateRange({ ...dateRange, startDate: e.target.value })}
          />
        </div>

        <div className="filter-group">
          <label>До:</label>
          <input
            type="date"
            value={dateRange.endDate}
            onChange={e => setDateRange({ ...dateRange, endDate: e.target.value })}
          />
        </div>

        <div className="filter-info">
          Всего: {visiblePlates.length}
        </div>
      </div>

      {loading ? (
        <div className="loading">Загрузка...</div>
      ) : paginatedPlates.length === 0 ? (
        <div className="no-data">Нет данных</div>
      ) : (
        <>
          <UnknownPlatesTable plates={paginatedPlates} onRowClick={handlePlateClick} />

          <div className="pagination">
            <button
              disabled={currentPage === 1}
              onClick={() => setCurrentPage(p => p - 1)}
            >
              ← Назад
            </button>
            <span>{currentPage} / {totalPages}</span>
            <button
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage(p => p + 1)}
            >
              Далее →
            </button>
          </div>
        </>
      )}

      {selectedPlate && (
        <PlateCheckModal
          plate={selectedPlate}
          onClose={handleModalClose}
          onCorrected={handleCorrected}
        />
      )}
    </div>
  )
}
