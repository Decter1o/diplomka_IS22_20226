import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import './StolenVehicles.css'

const API = '/api'

export default function AddStolenModal({ onClose, onAdded }) {
  const [tab, setTab] = useState('manual')

  // Вкладка "Ввести номер"
  const [plateInput, setPlateInput] = useState('')
  const [searchResult, setSearchResult] = useState(null)
  const [searching, setSearching] = useState(false)

  // Вкладка "Из детекций"
  const [detections, setDetections] = useState([])
  const [loadingDetections, setLoadingDetections] = useState(false)
  const [selectedPlate, setSelectedPlate] = useState(null)

  const [description, setDescription] = useState('')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (tab !== 'detections') return
    setLoadingDetections(true)
    fetch(`${API}/detections?limit=200`)
      .then(r => r.json())
      .then(data => {
        const seen = new Set()
        const unique = []
        for (const d of (data.detections || [])) {
          if (d.plate_number && !seen.has(d.plate_number)) {
            seen.add(d.plate_number)
            unique.push(d.plate_number)
          }
        }
        setDetections(unique)
      })
      .catch(() => setDetections([]))
      .finally(() => setLoadingDetections(false))
  }, [tab])

  const handleSearch = async () => {
    const num = plateInput.trim().toUpperCase()
    if (!num) return
    setSearching(true)
    setSearchResult(null)
    setError(null)
    try {
      const r = await fetch(`${API}/unknown-plates/check/${encodeURIComponent(num)}`)
      setSearchResult(await r.json())
    } catch {
      setError('Ошибка поиска')
    } finally {
      setSearching(false)
    }
  }

  const handleSelectDetection = async (plateNumber) => {
    setSelectedPlate({ plate_number: plateNumber })
    setError(null)
    try {
      const r = await fetch(`${API}/unknown-plates/check/${encodeURIComponent(plateNumber)}`)
      const data = await r.json()
      setSelectedPlate(data.found
        ? { plate_number: plateNumber, plate_id: data.plate_id, driver_name: data.driver_name, iin: data.iin }
        : { plate_number: plateNumber, notInDb: true }
      )
    } catch {
      // оставляем базовый объект
    }
  }

  const handleAdd = async () => {
    setError(null)
    const plateId = tab === 'manual' ? searchResult?.plate_id : selectedPlate?.plate_id
    if (!plateId) {
      setError('Номер не найден в базе данных')
      return
    }
    setAdding(true)
    try {
      const r = await fetch(`${API}/stolen-vehicles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plate_id: plateId, description: description || null }),
      })
      if (!r.ok) {
        const err = await r.json()
        throw new Error(err.detail || 'Ошибка добавления')
      }
      onAdded()
    } catch (e) {
      setError(e.message)
    } finally {
      setAdding(false)
    }
  }

  const canAdd = tab === 'manual' ? !!searchResult?.found : !!selectedPlate?.plate_id

  return createPortal(
    <div className="sv-overlay" onClick={onClose}>
      <div className="sv-modal" onClick={e => e.stopPropagation()}>
        <div className="sv-modal-header">
          <h5 className="mb-0">Добавить угнанное ТС</h5>
          <button className="btn-close" onClick={onClose}></button>
        </div>

        <div className="sv-modal-body">
          <ul className="nav nav-tabs mb-3">
            <li className="nav-item">
              <button
                className={`nav-link ${tab === 'manual' ? 'active' : ''}`}
                onClick={() => { setTab('manual'); setError(null) }}
              >
                <i className="bi bi-keyboard me-1"></i>Ввести номер
              </button>
            </li>
            <li className="nav-item">
              <button
                className={`nav-link ${tab === 'detections' ? 'active' : ''}`}
                onClick={() => { setTab('detections'); setError(null) }}
              >
                <i className="bi bi-clock-history me-1"></i>Из детекций
              </button>
            </li>
          </ul>

          {error && <div className="alert alert-danger py-2 small">{error}</div>}

          {tab === 'manual' && (
            <div className="mb-3">
              <div className="input-group">
                <input
                  type="text"
                  className="form-control font-monospace text-uppercase"
                  placeholder="123ABC45"
                  value={plateInput}
                  onChange={e => { setPlateInput(e.target.value.toUpperCase()); setSearchResult(null) }}
                  onKeyDown={e => e.key === 'Enter' && handleSearch()}
                />
                <button className="btn btn-outline-secondary" onClick={handleSearch} disabled={searching}>
                  {searching
                    ? <span className="spinner-border spinner-border-sm"></span>
                    : <i className="bi bi-search"></i>}
                </button>
              </div>

              {searchResult && (
                <div className={`alert py-2 mt-2 small ${searchResult.found ? 'alert-success' : 'alert-warning'}`}>
                  {searchResult.found ? (
                    <>
                      <div><strong>{plateInput}</strong> найден в базе</div>
                      <div>Водитель: {searchResult.driver_name || '—'}</div>
                      <div>ИИН: {searchResult.iin || '—'}</div>
                    </>
                  ) : (
                    'Номер не найден в базе данных'
                  )}
                </div>
              )}
            </div>
          )}

          {tab === 'detections' && (
            <div className="sv-detections-list mb-3">
              {loadingDetections ? (
                <div className="text-center py-3">
                  <span className="spinner-border spinner-border-sm"></span>
                </div>
              ) : detections.length === 0 ? (
                <div className="text-muted text-center py-3 small">Нет детекций</div>
              ) : (
                detections.map(pn => (
                  <button
                    key={pn}
                    className={`sv-det-item ${selectedPlate?.plate_number === pn ? 'selected' : ''}`}
                    onClick={() => handleSelectDetection(pn)}
                  >
                    <span className="font-monospace fw-bold">{pn}</span>
                    {selectedPlate?.plate_number === pn && (
                      <span className="small ms-2 text-muted">
                        {selectedPlate.driver_name || (selectedPlate.notInDb ? 'нет в базе' : '...')}
                      </span>
                    )}
                  </button>
                ))
              )}
            </div>
          )}

          <div className="mb-3">
            <label className="form-label small">Описание (необязательно)</label>
            <input
              type="text"
              className="form-control form-control-sm"
              placeholder="Марка, цвет, обстоятельства угона..."
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
          </div>

          <div className="d-flex gap-2 justify-content-end">
            <button className="btn btn-secondary btn-sm" onClick={onClose} disabled={adding}>
              Отмена
            </button>
            <button className="btn btn-danger btn-sm" onClick={handleAdd} disabled={adding || !canAdd}>
              {adding
                ? <><span className="spinner-border spinner-border-sm me-1"></span>Добавление...</>
                : <><i className="bi bi-plus-lg me-1"></i>Добавить</>}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}
