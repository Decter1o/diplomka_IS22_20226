import httpx
import threading
from fastapi import FastAPI
from core.core import process_camera

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    camera_dictionary = dict()
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://mediamtx:8080/v3/path/list")
            response.raise_for_status()
            data = response.json()
            for item in data['items']:
                name = item.get('name')
                if name is not None:
                    camera_dictionary[name] = f"rtsp://mediamtx:8554/{name}"
            
            # Просто вызовите process_camera напрямую без создания потоков
            for name, url in camera_dictionary.items():
                process_camera(name, url)  # Запускает daemon потоки и возвращает
                
    except:
        print("Error fetching camera data from mediamtx")