import { useEffect, useState } from 'react'
import AddStolenModal from './AddStolenModal'
import './StolenVehicles.css'

const API = '/api'

export default function StolenVehicles() {
  const [vehicles, setVehicles] = useState([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(null)
  const [showAddModal, setShowAddModal] = useState(false)

  const load = () => {
    setLoading(true)
    fetch(`${API}/stolen-vehicles/enriched`)
      .then(r => r.json())
      .then(data => setVehicles(data.stolen_vehicles || []))
      .catch(() => setVehicles([]))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleDelete = async (plateId) => {
    if (!window.confirm('Удалить из списка угнанных?')) return
    setDeleting(plateId)
    try {
      await fetch(`${API}/stolen-vehicles/${plateId}`, { method: 'DELETE' })
      load()
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-4">
        <h4 className="mb-0">
          <i className="bi bi-car-front-fill me-2 text-danger"></i>
          Угнанные транспортные средства
        </h4>
        <button className="btn btn-danger btn-sm" onClick={() => setShowAddModal(true)}>
          <i className="bi bi-plus-lg me-1"></i>Добавить
        </button>
      </div>

      {loading ? (
        <div className="text-center py-5">
          <span className="spinner-border text-danger"></span>
        </div>
      ) : vehicles.length === 0 ? (
        <div className="card shadow-sm">
          <div className="card-body text-muted text-center py-5">
            <i className="bi bi-car-front fs-1 d-block mb-2 opacity-25"></i>
            Список угнанных ТС пуст
          </div>
        </div>
      ) : (
        <div className="card shadow-sm">
          <div className="card-header d-flex align-items-center gap-2">
            <span className="badge bg-danger">{vehicles.length}</span>
            <span className="small text-muted">транспортных средств в розыске</span>
          </div>
          <div className="card-body p-0">
            <table className="table table-hover mb-0">
              <thead className="table-light">
                <tr>
                  <th>Номер</th>
                  <th>Дата добавления</th>
                  <th>Водитель</th>
                  <th>ИИН</th>
                  <th>Описание</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {vehicles.map(v => (
                  <tr key={v.plate_id}>
                    <td>
                      <span className="badge bg-danger fs-6 font-monospace">{v.plate_number}</span>
                    </td>
                    <td className="text-nowrap">
                      {v.reported_at
                        ? new Date(v.reported_at).toLocaleDateString('ru-RU', {
                            day: '2-digit', month: '2-digit', year: 'numeric'
                          })
                        : '—'}
                    </td>
                    <td>{v.driver_name || <span className="text-muted">—</span>}</td>
                    <td className="font-monospace">{v.iin || <span className="text-muted">—</span>}</td>
                    <td className="sv-description">{v.description || <span className="text-muted">—</span>}</td>
                    <td>
                      <button
                        className="btn btn-outline-danger btn-sm"
                        onClick={() => handleDelete(v.plate_id)}
                        disabled={deleting === v.plate_id}
                        title="Удалить из списка"
                      >
                        {deleting === v.plate_id
                          ? <span className="spinner-border spinner-border-sm"></span>
                          : <i className="bi bi-trash"></i>}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showAddModal && (
        <AddStolenModal
          onClose={() => setShowAddModal(false)}
          onAdded={() => { setShowAddModal(false); load() }}
        />
      )}
    </div>
  )
}
