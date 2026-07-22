function formatTime(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('ru-RU')
}

const TYPE_LABELS = { stolen: 'Угон', wanted: 'Штрафник' }

function AlertBadge({ type }) {
  const label = TYPE_LABELS[type] || type
  const styles = {
    'Угон':     { bg: 'danger',  icon: 'bi-exclamation-octagon-fill' },
    'Штрафник': { bg: 'warning', icon: 'bi-exclamation-triangle-fill' },
  }
  const style = styles[label] || { bg: 'secondary', icon: 'bi-info-circle' }
  return (
    <span className={`badge bg-${style.bg}`}>
      <i className={`bi ${style.icon} me-1`}></i>
      {label}
    </span>
  )
}

export default function AlertsTable({ rows }) {
  if (!rows.length) {
    return (
      <div className="text-center text-muted py-4">
        <i className="bi bi-inbox fs-4 d-block mb-1"></i>
        Нет данных
      </div>
    )
  }

  return (
    <div className="table-responsive">
      <table className="table table-sm table-hover mb-0">
        <thead className="table-light sticky-top">
          <tr>
            <th style={{ width: '180px' }}>Время</th>
            <th style={{ width: '100px' }}>Тип</th>
            <th style={{ width: '100px' }}>Номер</th>
            <th style={{ width: '150px' }}>Водитель</th>
            <th style={{ width: '120px' }}>Камера</th>
            <th style={{ width: '150px' }}>Локация</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(a => (
            <tr key={a.id}>
              <td className="text-nowrap small">{formatTime(a.created_at)}</td>
              <td><AlertBadge type={a.alert_type} /></td>
              <td>
                <span className="plate-badge">{a.plate_number || '—'}</span>
              </td>
              <td className="small">{a.driver_name || '—'}</td>
              <td className="text-muted small">{a.camera_name || '—'}</td>
              <td className="text-muted small">{a.camera_location || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
