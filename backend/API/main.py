import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from repositories.user_repository import UserRepository
from service.detection_service import DetectionService
from brocker.consumer_kafka import PlateConsumer

logging.basicConfig(level=logging.INFO)

app = FastAPI()

user_repo = UserRepository()
detection_service = DetectionService()
consumer: PlateConsumer = None


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
            # держим соединение живым, ждём disconnect от клиента
            await websocket.receive_text()
    except WebSocketDisconnect:
        detection_service.unregister_ws(websocket)


# ------------------------------------------------------------------
# REST
# ------------------------------------------------------------------

@app.get("/hello")
async def get_hello():
    return {"message": "Мда, привет!"}


@app.get("/users")
async def get_users():
    users = user_repo.get_all_users()
    return {"users": users}