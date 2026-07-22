import { useState } from 'react'
import { createPortal } from 'react-dom'
import './UnknownPlates.css'

const API = '/api'

export default function PlateCheckModal({ plate, onClose, onCorrected }) {
  console.log('PlateCheckModal rendered with plate:', plate)
  console.log('Modal component mounted, plate.id:', plate?.id)

  const [inputPlate, setInputPlate] = useState(plate.corrected_plate_number || '')
  const [checkResult, setCheckResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleCheck = async () => {
    if (!inputPlate.trim()) {
      setCheckResult({ error: 'Введите номер' })
      return
    }

    setLoading(true)
    try {
      const res = await fetch(`${API}/unknown-plates/check/${encodeURIComponent(inputPlate.toUpperCase())}`)
      const data = await res.json()
      setCheckResult(data)
    } catch (e) {
      setCheckResult({ error: 'Ошибка проверки' })
    }
    setLoading(false)
  }

  const handleSave = async () => {
    if (!inputPlate.trim()) return

    setSaving(true)
    try {
      const res = await fetch(`${API}/unknown-plates/${plate.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ corrected_plate_number: inputPlate.toUpperCase() })
      })

      if (res.ok) {
        onCorrected()
      } else {
        alert('Ошибка при сохранении')
      }
    } catch (e) {
      alert('Ошибка: ' + e.message)
    }
    setSaving(false)
  }

  console.log('Rendering modal with onClose:', typeof onClose)

  return createPortal(
    <div className="plate-modal-overlay" onClick={onClose}>
      <div className="plate-modal" onClick={e => e.stopPropagation()}>
        <div className="plate-modal-header">
          <h2>Проверка номера</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="plate-modal-content">
          <div className="photo-section">
            <div className="photos">
              {plate.plates_photo_url && (
                <div>
                  <p>Фото номера:</p>
                  <img src={plate.plates_photo_url} alt="plate" />
                </div>
              )}
              {plate.full_photo_url && (
                <div>
                  <p>Полный кадр:</p>
                  <img src={plate.full_photo_url} alt="full" />
                </div>
              )}
            </div>
          </div>

          <div className="info-section">
            <div className="info-row">
              <label>Распознанный номер:</label>
              <span>{plate.plate_number || '—'}</span>
            </div>

            <div className="info-row">
              <label>Время:</label>
              <span>{new Date(plate.timestamp).toLocaleString('ru-RU')}</span>
            </div>

            <div className="input-group">
              <label>Введите правильный номер:</label>
              <div className="input-with-btn">
                <input
                  type="text"
                  value={inputPlate}
                  onChange={e => {
                    setInputPlate(e.target.value.toUpperCase())
                    setCheckResult(null)
                  }}
                  placeholder="0123BC45"
                  maxLength="20"
                />
                <button
                  className="btn-check"
                  onClick={handleCheck}
                  disabled={loading || !inputPlate.trim()}
                >
                  {loading ? 'Проверка...' : 'Проверить'}
                </button>
              </div>
            </div>

            {checkResult && (
              <div className={`result ${checkResult.found ? 'found' : 'not-found'}`}>
                <p><strong>{checkResult.status}</strong></p>
                {checkResult.found && (
                  <>
                    <p>Владелец: <strong>{checkResult.driver_name}</strong></p>
                    <p>ИИН: {checkResult.iin}</p>
                  </>
                )}
              </div>
            )}

            <div className="modal-actions">
              <button
                className="btn btn-primary"
                onClick={handleSave}
                disabled={saving || !inputPlate.trim()}
              >
                {saving ? 'Сохранение...' : 'Сохранить и исправить'}
              </button>
              <button className="btn btn-secondary" onClick={onClose}>
                Отмена
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}
