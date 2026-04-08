import httpx
import threading
from fastapi import FastAPI

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
                else:
                    print("Camera name is missing in the response item.")

            threads = [threading.Tread(target = , args=(name, url)) for name, url in camera_dictionary.items()]


    except:
        print("Error fetching camera data from mediamtx")