from fastapi import HTTPException, status
import asyncpg
from dotenv import load_dotenv, dotenv_values
import os

load_dotenv()


db_user = os.getenv("DB_USER")
db_pwd = os.getenv("DB_PWD")
db_name = os.getenv("DB_NAME")
db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")

if not all([db_user, db_pwd, db_name, db_host, db_port]):
    raise Exception("Database credentials are not fully set in environment variables.")

class Database:
    def __init__(self, min_size=1, max_size=10) -> None:
        self.min_size = min_size
        self.max_size = max_size
        self.dsn = f"postgresql://{db_user}:{db_pwd}@{db_host}:{db_port}/{db_name}"
        self.pool = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(dsn=self.dsn)
        else:
            print('Pool is already connected.')

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self.pool = None
    
    async def acquire_connection(self):
        return await self.pool.acquire()

    async def release_connection(self, connection):
        await self.pool.release(connection)
                
database = Database()

async def db_conn():
    try:
        await database.connect()
        print('Pool connected...')
        return {'Response': 'Connected'}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unknown error: {e}"
        )

async def db_close():
    await database.disconnect()
    print('Connection pool closed...')
    return {'Response': 'Disconnected'}
