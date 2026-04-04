import httpx
from fastapi import FastAPI
from repositories.user_repository import UserRepository

app = FastAPI()
user_repo = UserRepository()

@app.get("/hello")
async def get_hello():
    return {"message": "Мда, привет!"}
@app.get("/users")
async def get_users():
    users = user_repo.get_all_users()
    return {"users": users}
