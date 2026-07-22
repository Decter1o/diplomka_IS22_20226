import os
import uuid
import threading
import queue
import time
import httpx
import sys
import cv2
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
import recorder as recorder_mod
from fastapi.middleware.cors import CORSMiddleware
from core.core import process_camera, get_live_processor, stop_camera as _stop_camera
from core.file_processor import VideoFileProcessor

# Хранилище активных задач: job_id → статус
_jobs: dict = {}
_jobs_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting AI service...", flush=True)
    camera_dictionary = dict()
    try:
        print("📡 Fetching camera data from mediamtx...", flush=True)
        async with httpx.AsyncClient() as client:
            response = await client.get("http://mediamtx:8080/v3/config/paths/list")
            response.raise_for_status()
            data = response.json()
            print(f"✅ Found {len(data.get('items', []))} items", flush=True)
            for item in data.get('items', []):
                name = item.get('name')
                if name is not None:
                    camera_dictionary[name] = f"rtsp://mediamtx:8554/{name}"
                    print(f"  📹 Camera: {name}", flush=True)

            print(f"🎬 Processing {len(camera_dictionary)} cameras...", flush=True)
            for name, url in camera_dictionary.items():
                print(f"  ▶️  Starting process_camera for {name}", flush=True)
                process_camera(name, url)
                print(f"  ✅ process_camera for {name} started", flush=True)

    except Exception as e:
        print(f"❌ Error fetching camera data: {e}", flush=True)
        import traceback
        traceback.print_exc(file=sys.stdout)

    print("✅ Startup complete", flush=True)
    yield
    print("🛑 Shutting down AI service...", flush=True)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _process_video_file(job_id: str, file_path: str, source_name: str):
    """Запускает VideoFileProcessor на видеофайле в отдельном потоке."""
    try:
        with _jobs_lock:
            _jobs[job_id]['status'] = 'processing'

        processor = VideoFileProcessor(video_source=file_path, name=source_name, job_id=job_id)
        with _jobs_lock:
            _jobs[job_id]['processor'] = processor
        processor.start_processing()

        if processor.processing_thread:
            processor.processing_thread.join()

        # Ждём пока все OCR-воркеры обработают оставшиеся элементы очереди
        print(f"[JOB][WAIT] Ожидаем завершения OCR-очереди job={job_id}", flush=True)
        processor.crop_queue.join()
        print(f"[JOB][OK] OCR-очередь пуста, закрываем job={job_id}", flush=True)

        processor.stop_processing()

        with _jobs_lock:
            _jobs[job_id]['status'] = 'done'

    except Exception as e:
        with _jobs_lock:
            _jobs[job_id]['status'] = 'error'
            _jobs[job_id]['error'] = str(e)
        print(f"❌ Video processing error for job {job_id}: {e}", flush=True)
    finally:
        try:
            os.remove(file_path)
        except Exception:
            pass


@app.post("/upload-video")
async def upload_video(file: UploadFile = File(...)):
    """Принимает видеофайл и запускает на нём распознавание номеров.

    Результаты появляются в детекциях и алертах через Kafka → API Service.

    Returns:
        job_id: идентификатор задачи для проверки статуса
    """
    allowed_ext = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.dav'}
    _, ext = os.path.splitext(file.filename or '')
    if ext.lower() not in allowed_ext:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Allowed: {', '.join(allowed_ext)}"
        )

    job_id = str(uuid.uuid4())
    tmp_dir = "/tmp/video_uploads"
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{job_id}{ext}")

    try:
        content = await file.read()
        with open(tmp_path, 'wb') as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    source_name = f"upload_{job_id[:8]}"
    with _jobs_lock:
        _jobs[job_id] = {
            'status': 'queued',
            'filename': file.filename,
            'source_name': source_name,
            'processor': None,
        }

    thread = threading.Thread(
        target=_process_video_file,
        args=(job_id, tmp_path, source_name),
        daemon=True
    )
    thread.start()

    print(f"📹 Video upload job started: {job_id} ({file.filename})", flush=True)

    return {
        "job_id": job_id,
        "filename": file.filename,
        "status": "queued",
        "source_name": source_name,
        "message": "Video is being processed. Results will appear in detections and alerts."
    }


@app.get("/upload-video/{job_id}")
async def get_job_status(job_id: str):
    """Возвращает статус задачи обработки видео."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"job_id": job_id, **{k: v for k, v in job.items() if k != 'processor'}}


@app.get("/upload-video")
async def list_jobs():
    """Возвращает список всех задач обработки видео."""
    with _jobs_lock:
        jobs = [
            {"job_id": k, **{kk: vv for kk, vv in v.items() if kk != 'processor'}}
            for k, v in _jobs.items()
        ]
    return {"jobs": jobs, "count": len(jobs)}


@app.get("/upload-video/{job_id}/stream")
async def stream_job_frames(job_id: str):
    """MJPEG-стрим аннотированных кадров для активной задачи."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    processor = job.get('processor')
    if not processor:
        raise HTTPException(status_code=404, detail="Stream not available yet")

    frame_queue = processor.frame_queue
    target_fps = min(getattr(processor, 'fps', 15) or 15, 15)
    frame_interval = 1.0 / target_fps

    def generate():
        last_frame_time = 0.0
        timeout_ticks = 0
        while True:
            try:
                frame = frame_queue.get(timeout=3)
                timeout_ticks = 0
            except queue.Empty:
                with _jobs_lock:
                    status = _jobs.get(job_id, {}).get('status', 'done')
                if status not in ('processing', 'queued'):
                    break
                timeout_ticks += 1
                if timeout_ticks > 10:
                    break
                continue

            now = time.time()
            elapsed = now - last_frame_time
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)
            last_frame_time = time.time()

            ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ok:
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                buf.tobytes() +
                b"\r\n"
            )

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/camera/{name}/stream")
async def stream_camera_frames(name: str):
    """MJPEG-стрим аннотированных кадров для живой камеры."""
    processor = get_live_processor(name)
    if not processor:
        raise HTTPException(status_code=404, detail="Camera not found or not started")

    frame_queue = processor.frame_queue

    def generate():
        timeout_ticks = 0
        while True:
            try:
                frame = frame_queue.get(timeout=3)
                timeout_ticks = 0
            except queue.Empty:
                timeout_ticks += 1
                if timeout_ticks > 20:
                    break
                continue

            ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ok:
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                buf.tobytes() +
                b"\r\n"
            )

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/camera/{name}/start")
async def start_camera(name: str):
    """Запускает обработку RTSP-потока для камеры. Вызывается из API-сервиса при создании камеры."""
    if get_live_processor(name):
        return {"ok": True, "message": "Already running"}
    process_camera(name, f"rtsp://mediamtx:8554/{name}")
    return {"ok": True, "message": f"Started processing for {name}"}


@app.delete("/camera/{name}/stop")
async def stop_camera(name: str):
    """Останавливает обработку потока камеры. Вызывается из API-сервиса при удалении камеры."""
    _stop_camera(name)
    return {"ok": True, "message": f"Stopped processing for {name}"}


@app.get("/recording-webhook")
async def recording_webhook(
    background_tasks: BackgroundTasks,
    path: str = Query(...),
    segment: str = Query(...),
    duration: str = Query("300"),
):
    """Called by MediaMTX runOnRecordSegmentComplete. Uploads segment to MinIO."""
    return await recorder_mod.handle_webhook(path, segment, duration, background_tasks)


@app.get("/recording-download")
async def recording_download(
    camera: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
):
    """Concatenates recording segments with FFmpeg and streams the result."""
    return await recorder_mod.handle_download(camera, start, end)


if __name__ == "__main__":
    import uvicorn
    print("🌐 Starting uvicorn server on 0.0.0.0:8000", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8000)