export default function VideoPlayer({ cameraName }) {
  return (
    <div className="video-wrapper">
      <img
        key={cameraName}
        src={`/api/camera/${encodeURIComponent(cameraName)}/stream`}
        className="camera-video"
        alt={cameraName}
      />
      <div className="video-placeholder">
        <i className="bi bi-camera-video-off"></i>
        <span>Поток недоступен</span>
      </div>
    </div>
  )
}
