import './UnknownPlates.css'

export default function UnknownPlatesTable({ plates, onRowClick }) {
  const getStatusBadge = (status) => {
    const badges = {
      'unrecognized': { text: 'Не распознан', color: '#ff9800' },
      'corrected': { text: 'Исправлен', color: '#4caf50' },
      'not_in_db': { text: 'Нет в базе', color: '#f44336' }
    }
    const badge = badges[status] || { text: status, color: '#999' }
    return <span className="status-badge" style={{ backgroundColor: badge.color }}>{badge.text}</span>
  }

  const getSourceLabel = (plate) => {
    if (plate.job_id) return (
      <span className="source-badge source-video">
        <i className="bi bi-film" /> Видео
      </span>
    )
    if (plate.camera_id) return (
      <span className="source-badge source-camera">
        <i className="bi bi-camera-video" /> Камера
      </span>
    )
    return <span className="text-muted">—</span>
  }

  return (
    <div className="table-container">
      <table className="unknown-plates-table">
        <thead>
          <tr>
            <th>Время</th>
            <th>Распознанный номер</th>
            <th>Исправленный номер</th>
            <th>Источник</th>
            <th>Фото</th>
            <th>Статус</th>
            <th className="action-col">Действие</th>
          </tr>
        </thead>
        <tbody>
          {plates.map(plate => (
            <tr key={plate.id}>
              <td>{new Date(plate.timestamp).toLocaleString('ru-RU')}</td>
              <td className="plate-number">{plate.plate_number || '—'}</td>
              <td className="corrected-number">{plate.corrected_plate_number || '—'}</td>
              <td>{getSourceLabel(plate)}</td>
              <td>
                {plate.plates_photo_url && (
                  <img src={plate.plates_photo_url} alt="plate" className="plate-thumb" />
                )}
              </td>
              <td>{getStatusBadge(plate.status)}</td>
              <td className="action-col">
                <button
                  className="btn-action"
                  onClick={() => onRowClick(plate)}
                >
                  Проверить
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
