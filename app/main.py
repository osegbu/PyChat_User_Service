from fastapi import FastAPI, Depends, HTTPException, status, Path, Body, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from app.utils.checkapikey import check_api_key
from contextlib import asynccontextmanager
import bcrypt
from app.db.init_db import db_conn, db_close
from app.db.query import execute_query, insert_query, select_query
from app.models.validations import UpdateUsername, ImageUpload, LoginRequest, CreatUser, UpdateAbout
import asyncpg
from app.utils.user_avatar import create_profile_image
from jose import jwt
import aiofiles
import os
from dotenv import load_dotenv

load_dotenv()

if not os.path.exists("./static"):
    os.makedirs("./static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_conn()
    yield
    await db_close()

app = FastAPI(lifespan=lifespan)
app.mount('/static', StaticFiles(directory='./static'), name='static')

origins = [
    'http://localhost',
    'http://localhost:8000',
    'http://localhost:3000'
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

security = HTTPBearer()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

async def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_passwords_match(password, confirm_password):
    if password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match"
        )
    return password

@app.post("/login", description="Login a user with their username and password")
async def login_endpoint(login_request: LoginRequest, api_key: str = Depends(check_api_key)):
    try:
        query = "SELECT * FROM users WHERE username=$1"
        user = await execute_query(insert_query, query, login_request.username)
        if user and verify_password(login_request.password, user['password']):
            return user
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid credentials')
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/signup", description="Create a new user with a username and password.")
async def signup_endpoint(create_user: CreatUser, api_key: str = Depends(check_api_key)):
    try:
        username = create_user.username
        first_letter = username[0].upper()
        password = await hash_password(check_passwords_match(create_user.password, create_user.confirm_password))
        image_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        create_profile_image(first_letter, output_path = os.path.join("static", image_name))

        query = "INSERT INTO users(username, password, about, profileImage) VALUES ($1, $2, $3, $4) RETURNING id, username, about, profileImage"
        user = await execute_query(insert_query, query, username, password, 'Just joined and excited!', image_name)
        return user
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Username is already taken')
    except Exception as e:
        print(str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/update_username")
async def update_username(updateusername: UpdateUsername, api_key: str = Depends(check_api_key), credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload['id'] == str(updateusername.id):
            query = "UPDATE users SET username = $1 WHERE id = $2 RETURNING id, username, about, profileImage"
            return await execute_query(insert_query, query, updateusername.username, updateusername.id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Unauthorized')
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Username is taken')
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/update_about")
async def update_about(updateabout: UpdateAbout, api_key: str = Depends(check_api_key), credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload['id'] == str(updateabout.id):
            query = "UPDATE users SET about = $1 WHERE id = $2 RETURNING id, username, about, profileImage"
            return await execute_query(insert_query, query, updateabout.about, updateabout.id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Unauthorized')
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/upload_profile_image/{id}", description="Upload profile image. Only JPEG and PNG formats are supported, with a max size of 5 MB.")
async def upload_image(previousImage: str = Body(...), file: UploadFile = File(...), id: int = Path(..., description="User ID to update profile image", gt=0), api_key: str = Depends(check_api_key), credentials: HTTPAuthorizationCredentials = Depends(security)):
    file_size = len(await file.read())
    file.file.seek(0)
    token = credentials.credentials
    try:
        if os.path.exists(os.path.join("static", previousImage)):
            os.remove(os.path.join("static", previousImage))

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload['id'] == str(id):
            image_upload = ImageUpload(filename=file.filename, content_type=file.content_type, size=file_size)
            unique_file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(file.filename)[1]}"
            file_path = os.path.join("static", unique_file_name)

            async with aiofiles.open(file_path, "wb") as f:
                content = await file.read()
                await f.write(content)

            query = "UPDATE users SET profileImage = $1 WHERE id = $2 RETURNING id, username, about, profileImage"
            return await execute_query(insert_query, query, unique_file_name, id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Unauthorized')
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/get_all_users")
async def get_users(api_key: str = Depends(check_api_key)):
    try:
        query = "SELECT id, username, about, profileImage, status FROM users ORDER BY id DESC"
        return await execute_query(select_query, query) or HTTPException(status_code=status.HTTP_204_NO_CONTENT, detail='No users found')
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/logout/{id}", description="Log out a user")
async def logout(id: int = Path(..., description="User ID to log out", gt=0), api_key: str = Depends(check_api_key)):
    query = "UPDATE users SET status = 'Offline' WHERE id = $1"
    return await execute_query(insert_query, query, id)
