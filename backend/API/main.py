import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Optional

from repositories.user_repository import UserRepository
from repositories.alert_repository import AlertRepository
from repositories.detection_reposytory import DetectionRepository
from repositories.unknow_plate_repository import UnknownPlateRepository
from repositories.stolen_vehicle_repository import StolenVehicleRepository
from repositories.camera_repository import CameraRepository
from models.alert_model import AlertType
from service.detection_service import DetectionService
from brocker.consumer_kafka import PlateConsumer

logging.basicConfig(level=logging.INFO)

app = FastAPI()

# ------------------------------------------------------------------
# Репозитории
# ------------------------------------------------------------------

user_repo = UserRepository()
alert_repo = AlertRepository()
detection_repo = DetectionRepository()
unknown_plate_repo = UnknownPlateRepository()
stolen_vehicle_repo = StolenVehicleRepository()
camera_repo = CameraRepository()

detection_service = DetectionService()
consumer: PlateConsumer = None


# ------------------------------------------------------------------
# Жизненный цикл
# ------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    global consumer
    loop = asyncio.get_event_loop()
    consumer = PlateConsumer(detection_service=detection_service, loop=loop)
    consumer.start()


@app.on_event("shutdown")
async def shutdown():
    if consumer:
        consumer.stop()


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
async def get_alerts(limit: int = 100, offset: int = 0):
    """Возвращает список всех алертов (штрафники + угоны), свежие первыми."""
    alerts = alert_repo.get_all(limit=limit, offset=offset)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/alerts/wanted")
async def get_wanted_alerts(limit: int = 100, offset: int = 0):
    """Возвращает только алерты по штрафникам."""
    alerts = alert_repo.get_by_type(AlertType.wanted, limit=limit, offset=offset)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/alerts/stolen")
async def get_stolen_alerts(limit: int = 100, offset: int = 0):
    """Возвращает только алерты по угнанным авто."""
    alerts = alert_repo.get_by_type(AlertType.stolen, limit=limit, offset=offset)
    return {"alerts": alerts, "count": len(alerts)}


# ------------------------------------------------------------------
# Детекции
# ------------------------------------------------------------------

@app.get("/detections")
async def get_detections(limit: int = 100, offset: int = 0):
    """Возвращает историю всех распознаваний номеров."""
    detections = detection_repo.get_all(limit=limit, offset=offset)
    return {"detections": detections, "count": len(detections)}


# ------------------------------------------------------------------
# Неизвестные номера
# ------------------------------------------------------------------

@app.get("/unknown-plates")
async def get_unknown_plates(limit: int = 100, offset: int = 0):
    """Возвращает список номеров, которые не нашлись в базе."""
    plates = unknown_plate_repo.get_all(limit=limit, offset=offset)
    return {"unknown_plates": plates, "count": len(plates)}


# ------------------------------------------------------------------
# Угнанные автомобили
# ------------------------------------------------------------------

class StolenVehicleCreate(BaseModel):
    plate_number: str
    description: Optional[str] = None


@app.get("/stolen-vehicles")
async def get_stolen_vehicles():
    """Возвращает список всех угнанных автомобилей."""
    vehicles = stolen_vehicle_repo.get_all()
    return {"stolen_vehicles": vehicles, "count": len(vehicles)}


@app.post("/stolen-vehicles", status_code=201)
async def add_stolen_vehicle(body: StolenVehicleCreate):
    """Добавляет автомобиль в список угнанных."""
    vehicle = stolen_vehicle_repo.create(
        plate_number=body.plate_number,
        description=body.description,
    )
    if not vehicle:
        raise HTTPException(status_code=400, detail="Не удалось добавить. Возможно, номер уже в списке.")
    return vehicle


@app.delete("/stolen-vehicles/{plate_number}", status_code=200)
async def remove_stolen_vehicle(plate_number: str):
    """Удаляет автомобиль из списка угнанных (например, если нашли)."""
    deleted = stolen_vehicle_repo.delete(plate_number)
    if not deleted:
        raise HTTPException(status_code=404, detail="Номер не найден в списке угнанных.")
    return {"detail": f"Номер {plate_number} удалён из списка угнанных."}


# ------------------------------------------------------------------
# Камеры
# ------------------------------------------------------------------

@app.get("/cameras")
async def get_cameras():
    """Возвращает список всех камер."""
    cameras = camera_repo.get_all()
    return {"cameras": cameras, "count": len(cameras)}


# ------------------------------------------------------------------
# Пользователи
# ------------------------------------------------------------------

@app.get("/users")
async def get_users():
    users = user_repo.get_all_users()
    return {"users": users}


@app.get("/hello")
async def get_hello():
    return {"message": "Мда, привет!"}