import httpx
from fastapi import FastAPI

app = FastAPI()

app.on_event("startup")
async def startup_event():
    try:
        async with httpx.AsyncClient() as client:
            camera_dictionary = dict()
            response = await client.get("http://mediamtx:8080/v3/path/list")
            data = response.json()
            for item in data['items']:
                name = item.get['name']
                
                camera_dictionary[name] = ""



    except:
        print("Error fetching camera data from mediamtx")