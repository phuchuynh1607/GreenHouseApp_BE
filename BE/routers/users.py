import aiofiles
from fastapi import APIRouter,HTTPException,File,UploadFile
import uuid
import os
from BE.models.users_model import Users, LoginHistory
from starlette import status
from .auth import user_dependency,db_dependency, verify_password,hash_password
from ..schemas.users_schema import UserVerification,UserUpdateRequest,UserResponse
from ..schemas.login_history_schema import LoginHistoryResponse
from typing import List
router = APIRouter(prefix='/users',tags=['users'])

IMAGEDIR = "static/images/"
os.makedirs(IMAGEDIR, exist_ok=True)

@router.post("/upload/", status_code=status.HTTP_201_CREATED)
async def create_upload_file(
    user: user_dependency,
    file: UploadFile = File(...)
):

    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # Kiểm tra định dạng file để đảm bảo an toàn
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Tạo tên file duy nhất bằng UUID để tránh trùng lặp
    ext = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{ext}"
    file_path = os.path.join(IMAGEDIR, unique_filename)

    # Ghi file bất đồng bộ bằng aiofiles để không chặn main thread
    try:
        async with aiofiles.open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                await f.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save file: {str(e)}")

    # Trả về URL để Frontend lưu vào database
    return {"url": file_path.replace("\\", "/")}



@router.get("/",status_code=status.HTTP_200_OK,response_model=UserResponse)
async def get_user_information(user:user_dependency,db:db_dependency):
    if user is None:
        raise HTTPException(status_code=401,detail='Authentication Failed')
    return db.query(Users).filter(Users.id == user.get('id')).first()

@router.put("/password",status_code=status.HTTP_204_NO_CONTENT)
async def change_password(user:user_dependency,db:db_dependency,user_verification:UserVerification):
    if user is None:
        raise HTTPException(status_code=401,detail='Authentication Failed')
    user_model =db.query(Users).filter(Users.id == user.get('id')).first()

    if not verify_password(user_verification.password, user_model.hashed_password):
        raise HTTPException(status_code=401,detail='Error on password change')
    user_model.hashed_password = hash_password(user_verification.new_password)
    db.add(user_model)
    db.commit()


@router.put("/change_information", status_code=status.HTTP_200_OK, response_model=UserResponse)
async def change_user_information(
        user: user_dependency,
        db: db_dependency,
        user_request: UserUpdateRequest
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')
    user_model = db.query(Users).filter(Users.id == user.get('id')).first()
    if user_model.user_image and user_model.user_image != user_request.user_image:
        if os.path.exists(user_model.user_image):
            try:
                os.remove(user_model.user_image)
            except Exception as e:
                print(f"Error deleting file: {e}")
    user_model.first_name = user_request.first_name
    user_model.last_name = user_request.last_name
    user_model.phone_number = user_request.phone_number
    user_model.gender = user_request.gender
    user_model.user_image = user_request.user_image

    db.add(user_model)
    db.commit()
    db.refresh(user_model)
    return user_model


@router.get("/login-history", response_model=List[LoginHistoryResponse])
async def get_my_login_history(
        user: user_dependency,
        db: db_dependency
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # Lấy danh sách lịch sử, sắp xếp cái mới nhất lên đầu
    history = db.query(LoginHistory) \
        .filter(LoginHistory.user_id == user.get('id')) \
        .order_by(LoginHistory.login_time.desc()) \
        .limit(20) \
        .all()

    return history