function formatTime(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('ru-RU')
}

function PhotoThumb({ url, alt }) {
  if (!url) return <span className="text-muted">—</span>
  return (
    <a href={url} target="_blank" rel="noreferrer" className="photo-link">
      <img src={url} alt={alt} className="plate-thumb" />
    </a>
  )
}

export default function DetectionsTable({ rows }) {
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
            <th style={{ width: '100px' }}>Номер</th>
            <th style={{ width: '140px' }}>Источник</th>
            <th style={{ width: '80px' }}>Фото номера</th>
            <th style={{ width: '80px' }}>Фото кадра</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(d => (
            <tr key={d.detection_id}>
              <td className="text-nowrap small">{formatTime(d.detection_time)}</td>
              <td>
                <span className="plate-badge">{d.plate_number || '—'}</span>
              </td>
              <td className="small">
                {d.source_type === 'video' ? (
                  <span className="text-primary">
                    <i className="bi bi-film me-1" />
                    Видео
                  </span>
                ) : (
                  <span className="text-muted">
                    <i className="bi bi-camera-video me-1" />
                    {d.camera_name || d.camera_id?.slice?.(0, 8) || '—'}
                  </span>
                )}
              </td>
              <td><PhotoThumb url={d.plates_photo_url} alt="номер" /></td>
              <td><PhotoThumb url={d.full_photo_url} alt="кадр" /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
