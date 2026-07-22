import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import './VideoUpload.css'

const API = '/api'

const STATUS_LABEL = {
  queued:     { text: 'В очереди',      cls: 'secondary', icon: 'bi-clock' },
  processing: { text: 'Обрабатывается', cls: 'primary',   icon: 'bi-arrow-repeat spin' },
  done:       { text: 'Завершено',      cls: 'success',   icon: 'bi-check-circle-fill' },
  error:      { text: 'Ошибка',         cls: 'danger',    icon: 'bi-x-circle-fill' },
}

function formatTime(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('ru-RU')
}

function PhotoModal({ url, onClose }) {
  return createPortal(
    <div className="vu-photo-overlay" onClick={onClose}>
      <div className="vu-photo-box" onClick={e => e.stopPropagation()}>
        <button className="vu-photo-close" onClick={onClose}>✕</button>
        <img src={url} alt="full" />
      </div>
    </div>,
    document.body
  )
}

export default function VideoUpload() {
  const [jobs, setJobs] = useState([])
  const [activeJob, setActiveJob] = useState(null)
  const [detections, setDetections] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState(null)
  const [photoUrl, setPhotoUrl] = useState(null)
  const [videoPreview, setVideoPreview] = useState(null)
  const [videoFileName, setVideoFileName] = useState('')
  const fileInputRef = useRef(null)
  const videoRef = useRef(null)
  const videoBlobRef = useRef(null)
  const pollRef = useRef(null)
  const detPollRef = useRef(null)

  useEffect(() => {
    return () => {
      if (videoBlobRef.current) URL.revokeObjectURL(videoBlobRef.current)
    }
  }, [])

  // ------------------------------------------------------------------
  // Загрузка списка задач при старте
  // ------------------------------------------------------------------
  useEffect(() => {
    loadJobs()
  }, [])

  // ------------------------------------------------------------------
  // Поллинг статуса активной задачи + детекций
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!activeJob) return
    if (activeJob.status === 'done' || activeJob.status === 'error') return

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API}/video-upload/${activeJob.job_id}`)
        if (!res.ok) return
        const updated = await res.json()
        setActiveJob(updated)
        setJobs(prev => prev.map(j => j.job_id === updated.job_id ? updated : j))
      } catch {}
    }, 2000)

    return () => clearInterval(pollRef.current)
  }, [activeJob?.job_id, activeJob?.status])

  useEffect(() => {
    if (!activeJob?.job_id) return

    const fetchDetections = async () => {
      try {
        const res = await fetch(
          `${API}/detections?job_id=${activeJob.job_id}&limit=200`
        )
        if (!res.ok) return
        const data = await res.json()
        setDetections(data.detections || [])
      } catch {}
    }

    fetchDetections()

    if (activeJob.status === 'processing' || activeJob.status === 'queued') {
      detPollRef.current = setInterval(fetchDetections, 2000)
    } else if (activeJob.status === 'done') {
      // После завершения ещё несколько секунд подбираем отставшие детекции из Kafka
      let ticks = 0
      detPollRef.current = setInterval(() => {
        fetchDetections()
        ticks++
        if (ticks >= 5) clearInterval(detPollRef.current)
      }, 2000)
    }

    return () => clearInterval(detPollRef.current)
  }, [activeJob?.job_id, activeJob?.status])

  const loadJobs = async () => {
    try {
      const res = await fetch(`${API}/video-upload`)
      if (!res.ok) return
      const data = await res.json()
      const jobList = data.jobs || []
      setJobs(jobList)
      if (jobList.length > 0 && !activeJob) {
        setActiveJob(jobList[0])
      }
    } catch {}
  }

  // ------------------------------------------------------------------
  // Загрузка файла
  // ------------------------------------------------------------------
  const handleFile = async (file) => {
    if (!file) return
    setError(null)

    const allowedExt = ['mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm', 'dav']
    const ext = file.name.split('.').pop().toLowerCase()
    if (!allowedExt.includes(ext)) {
      setError(`Неподдерживаемый формат. Разрешены: ${allowedExt.join(', ')}`)
      return
    }
    if (file.size > 500 * 1024 * 1024) {
      setError('Файл слишком большой. Максимум 500 МБ.')
      return
    }

    // Превью в плеере (для .dav браузер не сможет воспроизвести — покажем заглушку)
    if (videoBlobRef.current) URL.revokeObjectURL(videoBlobRef.current)
    if (ext !== 'dav') {
      const blobUrl = URL.createObjectURL(file)
      videoBlobRef.current = blobUrl
      setVideoPreview(blobUrl)
    } else {
      videoBlobRef.current = null
      setVideoPreview(null)
    }
    setVideoFileName(file.name)

    setUploading(true)
    setUploadProgress(0)
    setDetections([])

    try {
      const formData = new FormData()
      formData.append('file', file)

      const result = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('POST', `${API}/video-upload`)
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            setUploadProgress(Math.round((e.loaded / e.total) * 100))
          }
        }
        xhr.onload = () => {
          if (xhr.status === 200) resolve(JSON.parse(xhr.responseText))
          else {
            try { reject(new Error(JSON.parse(xhr.responseText).detail)) }
            catch { reject(new Error(`Ошибка ${xhr.status}`)) }
          }
        }
        xhr.onerror = () => reject(new Error('Ошибка сети'))
        xhr.send(formData)
      })

      setActiveJob(result)
      setJobs(prev => [result, ...prev])

    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
      setUploadProgress(0)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleInputChange = (e) => handleFile(e.target.files?.[0])
  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    handleFile(e.dataTransfer.files?.[0])
  }

  const isActive = activeJob?.status === 'processing' || activeJob?.status === 'queued'

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h4 className="mb-0">Загрузка видео</h4>
        {isActive && (
          <span className="badge bg-primary fs-6">
            <span className="spinner-border spinner-border-sm me-2" />
            Обрабатывается...
          </span>
        )}
      </div>

      <p className="text-muted mb-4">
        Загрузите видеофайл — система автоматически найдёт номерные знаки.
        Результаты появятся прямо на этой странице, а также в разделах
        <strong> Детекции</strong> и <strong>Алерты</strong>.
      </p>

      {/* Зона загрузки */}
      <div
        className={`vu-zone${dragOver ? ' drag-over' : ''}${uploading ? ' uploading' : ''}`}
        onClick={() => !uploading && fileInputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".mp4,.avi,.mov,.mkv,.wmv,.flv,.webm,.dav"
          onChange={handleInputChange}
          style={{ display: 'none' }}
        />

        {uploading ? (
          <div className="vu-progress-wrap">
            <div className="spinner-border text-primary mb-3" />
            <p className="mb-2 fw-semibold">Загрузка файла...</p>
            <div className="progress" style={{ width: 300, maxWidth: '90%' }}>
              <div
                className="progress-bar progress-bar-striped progress-bar-animated"
                style={{ width: `${uploadProgress}%` }}
              >
                {uploadProgress}%
              </div>
            </div>
          </div>
        ) : (
          <>
            <i className="bi bi-cloud-upload vu-icon" />
            <p className="mb-1 fw-semibold">Перетащите видео или нажмите для выбора</p>
            <p className="text-muted small mb-0">
              MP4, AVI, MOV, MKV, WMV, FLV, WEBM, DAV — до 500 МБ
            </p>
          </>
        )}
      </div>

      {error && (
        <div className="alert alert-danger mt-3 d-flex align-items-center gap-2">
          <i className="bi bi-exclamation-circle-fill" />
          {error}
        </div>
      )}

      {/* MJPEG-стрим аннотированных кадров при обработке */}
      {activeJob?.status === 'processing' && (
        <div className="vu-player-wrap mt-3">
          <div className="vu-player-header">
            <i className="bi bi-broadcast me-2 text-danger" />
            <span className="text-truncate" title={activeJob.filename}>
              {activeJob.filename} — live
            </span>
          </div>
          <img
            key={activeJob.job_id}
            src={`/api/video-upload/${activeJob.job_id}/stream`}
            alt="live stream"
            className="vu-player"
            style={{ display: 'block', background: '#000' }}
          />
        </div>
      )}

      {/* Заглушка пока задача в очереди */}
      {activeJob?.status === 'queued' && (
        <div className="vu-player-wrap mt-3 d-flex align-items-center justify-content-center"
             style={{ minHeight: 160, background: '#111' }}>
          <div className="text-center text-white">
            <div className="spinner-border text-primary mb-2" />
            <p className="mb-0 small">Ожидание начала обработки...</p>
          </div>
        </div>
      )}

      {/* Видеоплеер / заглушка для .dav — показываем только когда нет активного стрима */}
      {videoFileName && !isActive && (
        <div className="vu-player-wrap mt-3">
          <div className="vu-player-header">
            <i className="bi bi-play-circle me-2 text-primary" />
            <span className="text-truncate" title={videoFileName}>{videoFileName}</span>
          </div>
          {videoPreview ? (
            <video
              ref={videoRef}
              src={videoPreview}
              controls
              autoPlay
              muted
              className="vu-player"
              preload="auto"
            />
          ) : (
            <div className="vu-player-unsupported">
              <i className="bi bi-camera-video-off fs-2 mb-2" />
              <p className="mb-1">Предпросмотр недоступен для формата <strong>.dav</strong></p>
              <p className="small text-muted mb-0">Файл отправлен на сервер и будет обработан</p>
            </div>
          )}
        </div>
      )}

      {/* Статус активной задачи */}
      {activeJob && (
        <div className={`vu-job-status mt-3 border-${STATUS_LABEL[activeJob.status]?.cls || 'secondary'}`}>
          <div className="d-flex align-items-center gap-3 flex-wrap">
            <div className="flex-grow-1">
              <div className="d-flex align-items-center gap-2 mb-1">
                <i className="bi bi-file-earmark-play text-muted" />
                <strong>{activeJob.filename || 'Видео'}</strong>
                <span className={`badge bg-${STATUS_LABEL[activeJob.status]?.cls}`}>
                  {isActive && <span className="spinner-border spinner-border-sm me-1" />}
                  <i className={`bi ${STATUS_LABEL[activeJob.status]?.icon} me-1`} />
                  {STATUS_LABEL[activeJob.status]?.text}
                </span>
              </div>
              <div className="text-muted small">
                Источник: <code>{activeJob.source_name}</code>
                {activeJob.error && (
                  <span className="text-danger ms-2">{activeJob.error}</span>
                )}
              </div>
            </div>

            {detections.length > 0 && (
              <div className="text-end">
                <span className="badge bg-success fs-6">
                  <i className="bi bi-search me-1" />
                  {detections.length} номеров
                </span>
              </div>
            )}
          </div>

          {isActive && (
            <div className="progress mt-2" style={{ height: 4 }}>
              <div className="progress-bar progress-bar-striped progress-bar-animated w-100" />
            </div>
          )}
        </div>
      )}

      {/* Таблица детекций */}
      {activeJob && (
        <div className="mt-4">
          <div className="d-flex align-items-center gap-2 mb-3">
            <h6 className="mb-0">Найденные номера</h6>
            {isActive && (
              <span className="text-muted small">
                <span className="spinner-border spinner-border-sm me-1" />
                обновляется...
              </span>
            )}
            {detections.length > 0 && (
              <span className="badge bg-secondary ms-auto">{detections.length}</span>
            )}
          </div>

          {detections.length === 0 ? (
            <div className="vu-empty">
              {isActive ? (
                <>
                  <span className="spinner-border text-primary mb-2" />
                  <p className="text-muted">Идёт обработка видео, номера появятся здесь...</p>
                </>
              ) : (
                <>
                  <i className="bi bi-search fs-2 text-muted d-block mb-2" />
                  <p className="text-muted">
                    {activeJob.status === 'done'
                      ? 'Номера не найдены'
                      : 'Загрузите видео чтобы начать распознавание'}
                  </p>
                </>
              )}
            </div>
          ) : (
            <div className="card shadow-sm">
              <div className="table-responsive">
                <table className="table table-hover table-sm mb-0">
                  <thead className="table-dark">
                    <tr>
                      <th>#</th>
                      <th>Номер</th>
                      <th>Время</th>
                      <th>Фото номера</th>
                      <th>Полный кадр</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detections.map((d, i) => (
                      <tr key={d.detection_id}>
                        <td className="text-muted small">{i + 1}</td>
                        <td>
                          {d.plate_number ? (
                            <span className="vu-plate">{d.plate_number}</span>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                        <td className="text-nowrap small text-muted">
                          {formatTime(d.detection_time)}
                        </td>
                        <td>
                          {d.plates_photo_url ? (
                            <img
                              src={d.plates_photo_url}
                              alt="plate"
                              className="vu-thumb"
                              onClick={() => setPhotoUrl(d.plates_photo_url)}
                            />
                          ) : <span className="text-muted">—</span>}
                        </td>
                        <td>
                          {d.full_photo_url ? (
                            <img
                              src={d.full_photo_url}
                              alt="frame"
                              className="vu-thumb"
                              onClick={() => setPhotoUrl(d.full_photo_url)}
                            />
                          ) : <span className="text-muted">—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* История задач */}
      {jobs.length > 1 && (
        <div className="mt-4">
          <h6 className="mb-3 text-muted">История загрузок</h6>
          <div className="d-flex flex-wrap gap-2">
            {jobs.map(job => {
              const s = STATUS_LABEL[job.status] || { text: job.status, cls: 'secondary' }
              const isSelected = activeJob?.job_id === job.job_id
              return (
                <button
                  key={job.job_id}
                  className={`vu-history-btn${isSelected ? ' active' : ''}`}
                  onClick={() => {
                    setActiveJob(job)
                    setDetections([])
                  }}
                >
                  <span className={`badge bg-${s.cls} me-2`}>{s.text}</span>
                  <span className="text-truncate" style={{ maxWidth: 160 }}>
                    {job.filename || job.job_id}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Lightbox */}
      {photoUrl && <PhotoModal url={photoUrl} onClose={() => setPhotoUrl(null)} />}
    </div>
  )
}