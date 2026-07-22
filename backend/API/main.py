import asyncio
import logging
import io
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
import pandas as pd
import httpx

from repositories.user_repository import UserRepository
from repositories.alert_repository import AlertRepository
from repositories.detection_reposytory import DetectionRepository
from repositories.unknow_plate_repository import UnknownPlateRepository
from repositories.stolen_vehicle_repository import StolenVehicleRepository
from repositories.camera_repository import CameraRepository
from repositories.recording_repository import RecordingRepository
from models.alert_model import AlertType
from models.camera_create_model import CameraCreate
from models.user_model import UserRole
from service.detection_service import DetectionService
from service.camera_service import CameraService
from brocker.consumer_kafka import PlateConsumer
from auth.security import verify_password, create_access_token
from auth.dependencies import get_current_user, require_admin

logging.basicConfig(level=logging.INFO)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Репозитории
# ------------------------------------------------------------------

user_repo = UserRepository()
alert_repo = AlertRepository()
detection_repo = DetectionRepository()
unknown_plate_repo = UnknownPlateRepository()
stolen_vehicle_repo = StolenVehicleRepository()
camera_repo = CameraRepository()
recording_repo = RecordingRepository()

detection_service = DetectionService()
camera_service = CameraService()
consumer: PlateConsumer = None


# ------------------------------------------------------------------
# Жизненный цикл
# ------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    global consumer
    # Хэшируем открытые пароли, оставшиеся от предыдущих версий
    user_repo.migrate_plaintext_passwords()

    loop = asyncio.get_event_loop()
    consumer = PlateConsumer(detection_service=detection_service, loop=loop)
    consumer.start()

    await camera_service.sync_cameras_to_mediamtx()


@app.on_event("shutdown")
async def shutdown():
    if consumer:
        consumer.stop()


# ------------------------------------------------------------------
# Аутентификация
# ------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "operator"


@app.post("/auth/login")
async def login(body: LoginRequest):
    """Вход в систему. Возвращает JWT-токен."""
    user = user_repo.get_by_username(body.username)
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(
            status_code=401,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Учётная запись отключена")
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Информация о текущем авторизованном пользователе."""
    return {
        "uuid": current_user["uuid"],
        "username": current_user["username"],
        "role": current_user["role"],
    }


# ------------------------------------------------------------------
# Управление пользователями (только Admin)
# ------------------------------------------------------------------

@app.get("/users")
async def get_users(current_user: dict = Depends(require_admin)):
    """Возвращает список всех пользователей."""
    return {"users": user_repo.get_all_users()}


@app.post("/users", status_code=201)
async def create_user(body: UserCreateRequest, current_user: dict = Depends(require_admin)):
    """Создаёт нового пользователя."""
    try:
        role = UserRole(body.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Недопустимая роль: {body.role}")
    try:
        user = user_repo.create(body.username, body.password, role)
        return user
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/users/{user_id}", status_code=200)
async def delete_user(user_id: str, current_user: dict = Depends(require_admin)):
    """Удаляет пользователя по UUID."""
    if current_user["uuid"] == user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить собственную учётную запись")
    deleted = user_repo.delete(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {"detail": "Пользователь удалён"}


# ------------------------------------------------------------------
# WebSocket
# ------------------------------------------------------------------

@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    """WebSocket endpoint для получения алертов в реальном времени."""
    await websocket.accept()
    detection_service.register_ws(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        detection_service.unregister_ws(websocket)


# ------------------------------------------------------------------
# Алерты
# ------------------------------------------------------------------

@app.get("/alerts")
async def get_alerts(limit: int = 100, offset: int = 0, camera_id: Optional[UUID] = None,
                     current_user: dict = Depends(get_current_user)):
    """Возвращает список всех алертов (штрафники + угоны), свежие первыми."""
    if camera_id:
        alerts = alert_repo.get_by_camera(camera_id=camera_id, limit=limit, offset=offset)
    else:
        alerts = alert_repo.get_all(limit=limit, offset=offset)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/alerts/wanted")
async def get_wanted_alerts(limit: int = 100, offset: int = 0,
                            current_user: dict = Depends(get_current_user)):
    """Возвращает только алерты по штрафникам."""
    alerts = alert_repo.get_by_type(AlertType.wanted, limit=limit, offset=offset)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/alerts/stolen")
async def get_stolen_alerts(limit: int = 100, offset: int = 0,
                            current_user: dict = Depends(get_current_user)):
    """Возвращает только алерты по угнанным авто."""
    alerts = alert_repo.get_by_type(AlertType.stolen, limit=limit, offset=offset)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/alerts/enriched")
async def get_enriched_alerts(limit: int = 100, offset: int = 0,
                              alert_type: Optional[str] = None,
                              current_user: dict = Depends(get_current_user)):
    """Возвращает обогащённые алерты с информацией о номере, водителе и камере."""
    type_filter = None
    if alert_type:
        try:
            type_filter = AlertType(alert_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid alert_type: {alert_type}")

    alerts = alert_repo.get_enriched(limit=limit, offset=offset, alert_type=type_filter)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/alerts/export")
async def export_alerts(start_date: str, end_date: str, format: str = "csv",
                        alert_type: Optional[str] = None,
                        current_user: dict = Depends(get_current_user)):
    """Выгружает алерты за период в CSV или Excel."""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if format not in ["csv", "xlsx"]:
        raise HTTPException(status_code=400, detail="Format must be 'csv' or 'xlsx'")

    type_filter = None
    if alert_type:
        try:
            type_filter = AlertType(alert_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid alert_type: {alert_type}")

    alerts = alert_repo.get_enriched(limit=10000, offset=0,
                                     alert_type=type_filter,
                                     start_date=start, end_date=end)

    if not alerts:
        raise HTTPException(status_code=404, detail="No alerts found for this period")

    df = pd.DataFrame(alerts)
    df = df.rename(columns={
        'id': 'ID',
        'alert_type': 'Тип',
        'created_at': 'Время',
        'plate_number': 'Номер',
        'driver_name': 'Водитель',
        'camera_name': 'Камера',
        'camera_location': 'Локация'
    })
    df['Тип'] = df['Тип'].map({'wanted': 'Штрафник', 'stolen': 'Угон'})
    df['Время'] = pd.to_datetime(df['Время']).dt.strftime('%Y-%m-%d %H:%M:%S')
    df = df[['ID', 'Время', 'Тип', 'Номер', 'Водитель', 'Камера', 'Локация']]

    if format == "csv":
        output = io.StringIO()
        df.to_csv(output, index=False, encoding='utf-8')
        filename = f"alerts_{start_date}_{end_date}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl', sheet_name='Алерты')
        output.seek(0)
        filename = f"alerts_{start_date}_{end_date}.xlsx"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


# ------------------------------------------------------------------
# Детекции
# ------------------------------------------------------------------

@app.get("/detections")
async def get_detections(limit: int = 100, offset: int = 0,
                         camera_id: Optional[UUID] = None,
                         job_id: Optional[UUID] = None,
                         current_user: dict = Depends(get_current_user)):
    """Возвращает историю всех распознаваний номеров."""
    detections = detection_repo.get_all(limit=limit, offset=offset,
                                        camera_id=camera_id, job_id=job_id)
    return {"detections": detections, "count": len(detections)}


# ------------------------------------------------------------------
# Неизвестные номера
# ------------------------------------------------------------------

@app.get("/unknown-plates")
async def get_unknown_plates(
    limit: int = 100,
    offset: int = 0,
    camera_id: Optional[UUID] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Возвращает список номеров с фильтрацией по статусу и дате."""
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
        except:
            start_dt = None
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date + 'T23:59:59')
        except:
            end_dt = None

    plates = unknown_plate_repo.get_all(
        limit=limit, offset=offset, camera_id=camera_id,
        status=status, start_date=start_dt, end_date=end_dt
    )
    return {"unknown_plates": plates, "count": len(plates)}


@app.get("/unknown-plates/check/{plate_number}")
async def check_plate_in_db(plate_number: str,
                             current_user: dict = Depends(get_current_user)):
    """Проверяет есть ли номер в базе и возвращает информацию о водителе."""
    from repositories.plate_repository import PlateRepository
    plate_info = PlateRepository().get_plate_with_driver(plate_number)
    if plate_info:
        return {
            "found": True,
            "status": "номер в базе",
            "driver_name": plate_info["driver_name"],
            "iin": plate_info["iin"],
            "plate_id": str(plate_info["plate_id"])
        }
    return {"found": False, "status": "номера нет в базе"}


class UnknownPlateCorrection(BaseModel):
    corrected_plate_number: str


@app.put("/unknown-plates/{unknown_plate_id}")
async def correct_unknown_plate(unknown_plate_id: UUID, body: UnknownPlateCorrection,
                                current_user: dict = Depends(get_current_user)):
    """Обновляет статус unknown_plate на 'corrected' с введённым номером."""
    success = unknown_plate_repo.update(
        unknown_plate_id=unknown_plate_id,
        corrected_plate_number=body.corrected_plate_number,
        status='corrected'
    )
    if not success:
        raise HTTPException(status_code=404, detail="Unknown plate not found")
    return {"detail": "Updated successfully"}


# ------------------------------------------------------------------
# Угнанные автомобили
# ------------------------------------------------------------------

class StolenVehicleCreate(BaseModel):
    plate_id: UUID
    description: Optional[str] = None


@app.get("/stolen-vehicles/enriched")
async def get_stolen_vehicles_enriched(current_user: dict = Depends(get_current_user)):
    """Возвращает угнанные авто с номером, водителем и ИИН."""
    vehicles = stolen_vehicle_repo.get_enriched()
    return {"stolen_vehicles": vehicles, "count": len(vehicles)}


@app.get("/stolen-vehicles")
async def get_stolen_vehicles(current_user: dict = Depends(get_current_user)):
    """Возвращает список всех угнанных автомобилей."""
    vehicles = stolen_vehicle_repo.get_all()
    return {"stolen_vehicles": vehicles, "count": len(vehicles)}


@app.post("/stolen-vehicles", status_code=201)
async def add_stolen_vehicle(body: StolenVehicleCreate,
                             current_user: dict = Depends(get_current_user)):
    """Добавляет автомобиль в список угнанных по plate_id."""
    vehicle = stolen_vehicle_repo.create(plate_id=body.plate_id, description=body.description)
    if not vehicle:
        raise HTTPException(status_code=400, detail="Не удалось добавить. Возможно, plate_id уже в списке или не существует.")
    return vehicle


@app.delete("/stolen-vehicles/{plate_id}", status_code=200)
async def remove_stolen_vehicle(plate_id: UUID,
                                current_user: dict = Depends(get_current_user)):
    """Удаляет автомобиль из списка угнанных по plate_id."""
    deleted = stolen_vehicle_repo.delete(plate_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="plate_id не найден в списке угнанных.")
    return {"detail": f"plate_id {plate_id} удалён из списка угнанных."}


# ------------------------------------------------------------------
# Камеры
# ------------------------------------------------------------------

@app.get("/cameras")
async def get_cameras(current_user: dict = Depends(get_current_user)):
    """Возвращает список всех камер."""
    cameras = camera_repo.get_all()
    return {"cameras": cameras, "count": len(cameras)}


@app.post("/cameras", status_code=201)
async def create_camera(body: CameraCreate, current_user: dict = Depends(require_admin)):
    """Создаёт новую камеру в БД и добавляет её в MediaMTX. Только для Admin."""
    try:
        camera = await camera_service.create_camera(
            name=body.name, location=body.location, rtsp_url=body.rtsp_url
        )
        return camera
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/cameras/{camera_id}", status_code=200)
async def delete_camera(camera_id: UUID, current_user: dict = Depends(require_admin)):
    """Удаляет камеру из БД и из MediaMTX. Только для Admin."""
    try:
        await camera_service.delete_camera(camera_id)
        return {"detail": "Camera deleted successfully"}
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------
# Загрузка видео для анализа
# ------------------------------------------------------------------

AI_SERVICE_URL = "http://ai-service:8000"


@app.post("/video-upload")
async def upload_video_for_analysis(file: UploadFile = File(...),
                                    current_user: dict = Depends(get_current_user)):
    """Принимает видеофайл, проксирует в AI Service для распознавания."""
    try:
        content = await file.read()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{AI_SERVICE_URL}/upload-video",
                files={"file": (file.filename, content, file.content_type or "video/mp4")},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI Service timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/video-upload/{job_id}")
async def get_video_job_status(job_id: str, current_user: dict = Depends(get_current_user)):
    """Возвращает статус задачи обработки видео."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{AI_SERVICE_URL}/upload-video/{job_id}")
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Job not found")
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/video-upload")
async def list_video_jobs(current_user: dict = Depends(get_current_user)):
    """Возвращает список всех задач обработки видео."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{AI_SERVICE_URL}/upload-video")
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/camera/{name}/stream")
async def stream_camera(name: str, current_user: dict = Depends(get_current_user)):
    """Проксирует MJPEG-стрим аннотированных кадров от AI Service."""
    async def generate():
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                async with client.stream("GET", f"{AI_SERVICE_URL}/camera/{name}/stream") as response:
                    if response.status_code != 200:
                        return
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        yield chunk
            except Exception:
                return

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


# ------------------------------------------------------------------
# Записи видеопотока
# ------------------------------------------------------------------

class RecordingCreate(BaseModel):
    camera_path: str
    minio_object: str
    minio_url: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_sec: Optional[int] = None
    file_size: Optional[int] = None


@app.post("/internal/recordings", status_code=201, include_in_schema=False)
async def register_recording(body: RecordingCreate):
    """Вызывается AI-сервисом после загрузки сегмента в MinIO (без авторизации)."""
    started = datetime.fromisoformat(body.started_at) if body.started_at else None
    ended = datetime.fromisoformat(body.ended_at) if body.ended_at else None
    rec = recording_repo.create(
        camera_path=body.camera_path, minio_object=body.minio_object,
        minio_url=body.minio_url, started_at=started, ended_at=ended,
        duration_sec=body.duration_sec, file_size=body.file_size,
    )
    if not rec:
        raise HTTPException(status_code=500, detail="Failed to register recording")
    return rec


@app.get("/recordings/cameras")
async def get_recording_cameras(current_user: dict = Depends(get_current_user)):
    """Возвращает список камер, для которых есть записи."""
    return {"cameras": recording_repo.get_cameras()}


@app.get("/recordings")
async def get_recordings(
    camera: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """Возвращает список сегментов записей."""
    if start and end and camera:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        recordings = recording_repo.get_for_range(camera, start_dt, end_dt)
    else:
        recordings = recording_repo.get_all(camera=camera, limit=limit, offset=offset)
    return {"recordings": recordings, "count": len(recordings)}


@app.get("/recordings/download")
async def download_recording_range(camera: str, start: str, end: str,
                                   current_user: dict = Depends(get_current_user)):
    """Скачивает произвольный отрезок записи через AI-сервис."""
    async def generate():
        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                async with client.stream(
                    "GET", f"{AI_SERVICE_URL}/recording-download",
                    params={"camera": camera, "start": start, "end": end},
                ) as response:
                    if response.status_code != 200:
                        return
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                        yield chunk
            except Exception:
                return

    safe_cam = camera.replace("/", "_")
    fname = f"recording_{safe_cam}_{start[:10]}.mp4"
    return StreamingResponse(
        generate(),
        media_type="video/mp4",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@app.get("/video-upload/{job_id}/stream")
async def stream_video_job(job_id: str, current_user: dict = Depends(get_current_user)):
    """Проксирует MJPEG-стрим аннотированных кадров от AI Service."""
    async def generate():
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                async with client.stream("GET", f"{AI_SERVICE_URL}/upload-video/{job_id}/stream") as response:
                    if response.status_code != 200:
                        return
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        yield chunk
            except Exception:
                return

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")
