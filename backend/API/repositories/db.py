import os
from dotenv import load_dotenv
import psycopg

class DB:
    def __init__(self):
        load_dotenv()

    def get_connection(self):
        try:
            conn = psycopg.connect(
                host=os.getenv("HOST", "db"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                dbname=os.getenv("DB_NAME"),
                port=int(os.getenv("DB_PORTS"))
            )
            return conn
        except Exception as e:
            print(f"Error connecting to the database: {e}")
            return None


    