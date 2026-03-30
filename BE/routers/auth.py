from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette import status
from ..database import SessionLocal
from BE.models.users_model import Users, LoginHistory
from typing import Annotated
from datetime import timedelta,datetime,timezone
from passlib.context import CryptContext
from jose import jwt,JWTError
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from ..schemas.users_schema import CreateUserRequest,UserResponse
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import Request

env_path = Path(__file__).resolve().parent.parent.parent / '.env'

# Nạp file .env với đường dẫn cụ thể
load_dotenv(dotenv_path=env_path)



router=APIRouter(
    prefix='/auth',
    tags=['auth']
)



SECRET_KEY = os.getenv("SECRET_KEY")
PEPPER_AUTH = os.getenv("PEPPER_AUTH")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is required")

if not PEPPER_AUTH:
    raise RuntimeError("PEPPER_AUTH is required")
ALGORITHM='HS256'


bcrypt_context=CryptContext(schemes=['bcrypt'],deprecated='auto')
oauth2_bearer=OAuth2PasswordBearer(tokenUrl='auth/token')






class Token(BaseModel):
    access_token:str
    refresh_token:str
    token_type:str

def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str):
    return bcrypt_context.hash(password + PEPPER_AUTH)

def verify_password(plain_password: str, hashed_password: str):
    return bcrypt_context.verify(plain_password + PEPPER_AUTH, hashed_password)

def authenticate_user(username:str,password:str,db):
    user=db.query(Users).filter(Users.username == username).first()
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(username:str,user_id:int,role:str,expires_delta:timedelta):
    encode ={'sub':username,'id':user_id,'role':role}
    expires=datetime.now(timezone.utc) +expires_delta
    encode.update({'exp':expires})
    access_token=jwt.encode(encode,SECRET_KEY,algorithm=ALGORITHM)
    return access_token

async def get_current_user(token:Annotated[str,Depends(oauth2_bearer)]):
    try:
        payload=jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
        username:str=payload.get('sub')
        user_id:int =payload.get('id')
        user_role:str=payload.get('role')
        if username is None or user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail='Could not validate user.')
        return {'username':username,'id':user_id,'user_role':user_role}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Could not validate user.')

db_dependency=Annotated[Session,Depends(get_db)]
user_dependency=Annotated[dict,Depends(get_current_user)]


@router.post("/",status_code=status.HTTP_201_CREATED,response_model=UserResponse)
async def sign_up(db:db_dependency,create_user_request:CreateUserRequest):
    existing_user=db.query(Users).filter(Users.username == create_user_request.username).first()
    if existing_user:
        raise HTTPException(status_code=400,detail='Username already registered! ')
    existing_email=db.query(Users).filter(Users.email == create_user_request.email).first()
    if existing_email:
        raise HTTPException(status_code=400,detail='Email already registered! ')
    create_user_model = Users(
        username=create_user_request.username,
        email=create_user_request.email,
        hashed_password=hash_password(create_user_request.password),

        first_name=create_user_request.first_name,
        last_name=create_user_request.last_name,
        phone_number=create_user_request.phone_number,

        role=create_user_request.role,
        is_active=True
    )
    db.add(create_user_model)
    db.commit()
    db.refresh(create_user_model)
    return create_user_model

@router.post("/token",response_model=Token)
async def login_for_access_token(request: Request,
                                  form_data:Annotated[OAuth2PasswordRequestForm,Depends()],db:db_dependency):
    user=authenticate_user(form_data.username,form_data.password,db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail='Could not validate user.')

    client_ip = request.client.host
    user_agent = request.headers.get("user-agent")

    try:
        login_log = LoginHistory(
            user_id=user.id,
            ip_address=client_ip,
            device_info=user_agent
        )
        db.add(login_log)
        db.commit()
    except Exception as e:
        print(f"Lỗi khi ghi lịch sử đăng nhập: {e}")

    access_token =create_access_token(user.username,user.id,user.role,timedelta(minutes=10))
    refresh_token = create_access_token(user.username, user.id, user.role, timedelta(days=7))
    return {'access_token':access_token,'refresh_token':refresh_token,'token_type':'bearer'}

@router.post("/refresh")
async def refresh_access_token(refresh_token:str,db:db_dependency):
    try:
        payload =jwt.decode(refresh_token,SECRET_KEY,algorithms=[ALGORITHM])
        username: str = payload.get('sub')
        user_id: int = payload.get('id')
        user_role: str = payload.get('role')

        new_access_token=create_access_token(username,user_id,user_role,timedelta(minutes=10))
        return {'access_token':new_access_token,'token_type':"bearer"}
    except JWTError:
        raise HTTPException(status_code=401,detail="Refresh token is invalid or expired.")

