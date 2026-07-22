import { useEffect, useState } from 'react'
import DetectionsTable from './DetectionsTable'
import DetectionsPagination from './DetectionsPagination'
import './Detections.css'

const API = '/api'
const ROWS_PER_PAGE = 20

const SOURCE_FILTERS = [
  { value: 'all',    label: 'Все',    icon: 'bi-collection' },
  { value: 'camera', label: 'Камеры', icon: 'bi-camera-video' },
  { value: 'video',  label: 'Видео',  icon: 'bi-film' },
]

export default function Detections() {
  const [detections, setDetections] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [currentPage, setCurrentPage] = useState(1)

  useEffect(() => {
    setLoading(true)
    fetch(`${API}/detections?limit=500`)
      .then(r => r.json())
      .then(data => {
        setDetections(data.detections || [])
        setCurrentPage(1)
      })
      .catch(() => setDetections([]))
      .finally(() => setLoading(false))
  }, [])

  const filtered = detections.filter(d => {
    if (sourceFilter !== 'all' && d.source_type !== sourceFilter) return false
    if (!searchQuery.trim()) return true
    const q = searchQuery.toLowerCase()
    return (
      d.plate_number?.toLowerCase().includes(q) ||
      d.camera_name?.toLowerCase().includes(q)
    )
  })

  const totalPages = Math.ceil(filtered.length / ROWS_PER_PAGE)
  const startIdx = (currentPage - 1) * ROWS_PER_PAGE
  const paginatedData = filtered.slice(startIdx, startIdx + ROWS_PER_PAGE)

  const handleSearch = (e) => {
    setSearchQuery(e.target.value)
    setCurrentPage(1)
  }

  const handleSourceFilter = (value) => {
    setSourceFilter(value)
    setCurrentPage(1)
  }

  const handlePageChange = (page) => {
    setCurrentPage(Math.max(1, Math.min(page, totalPages)))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div>
      <h4 className="mb-3">Детекции</h4>

      {/* Фильтр по источнику */}
      <div className="btn-group mb-3" role="group">
        {SOURCE_FILTERS.map(f => (
          <button
            key={f.value}
            type="button"
            className={`btn btn-sm ${sourceFilter === f.value ? 'btn-primary' : 'btn-outline-secondary'}`}
            onClick={() => handleSourceFilter(f.value)}
          >
            <i className={`bi ${f.icon} me-1`} />
            {f.label}
          </button>
        ))}
      </div>

      {/* Поиск */}
      <div className="search-filters mb-3">
        <div className="input-group">
          <span className="input-group-text bg-light">
            <i className="bi bi-search"></i>
          </span>
          <input
            type="text"
            className="form-control"
            placeholder="Поиск по номеру или камере..."
            value={searchQuery}
            onChange={handleSearch}
          />
          {searchQuery && (
            <button
              className="btn btn-outline-secondary"
              type="button"
              onClick={() => { setSearchQuery(''); setCurrentPage(1) }}
            >
              <i className="bi bi-x-circle"></i>
            </button>
          )}
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
          {searchQuery || sourceFilter !== 'all'
            ? 'Детекции не найдены по выбранным фильтрам.'
            : 'Детекции отсутствуют.'}
        </div>
      ) : (
        <>
          <div className="card shadow-sm mb-3">
            <div className="card-header bg-light text-muted small d-flex justify-content-between align-items-center">
              <span>
                Показано <strong>{paginatedData.length}</strong> из <strong>{filtered.length}</strong> детекций
              </span>
              <div className="d-flex gap-2">
                {sourceFilter !== 'all' && (
                  <span className="badge bg-secondary">
                    {SOURCE_FILTERS.find(f => f.value === sourceFilter)?.label}
                  </span>
                )}
                {searchQuery && (
                  <span className="badge bg-primary">Поиск: {searchQuery}</span>
                )}
              </div>
            </div>
            <div className="card-body p-0">
              <DetectionsTable rows={paginatedData} />
            </div>
          </div>

          {totalPages > 1 && (
            <DetectionsPagination
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
