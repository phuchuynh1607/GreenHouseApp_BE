from fastapi import APIRouter, HTTPException
from starlette import status
from typing import List

from ..models.users_model import Threshold
from .auth import user_dependency, db_dependency
from ..schemas.threshold_schema import ThresholdCreate, ThresholdResponse

router = APIRouter(
    prefix='/thresholds',
    tags=['thresholds']
)


# --- 1. GET: LẤY NGƯỠNG ĐANG ÁP DỤNG (ƯU TIÊN USER) ---
@router.get("/active", response_model=List[ThresholdResponse])
async def get_active_thresholds(db: db_dependency, user: user_dependency):
    """
    Logic: Lấy toàn bộ sensor_type. Với mỗi loại, ưu tiên lấy của User,
    nếu User chưa cài thì lấy mặc định của Admin.
    """
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')
    sensor_types = ['light', 'temp', 'soil']
    active_list = []

    for s_type in sensor_types:
        # Tìm của User trước
        target = db.query(Threshold).filter(
            Threshold.sensor_type == s_type,
            Threshold.user_id == user.get('id')
        ).first()

        # Nếu không có, tìm của Admin (user_id is None)
        if not target:
            target = db.query(Threshold).filter(
                Threshold.sensor_type == s_type,
                Threshold.user_id == None
            ).first()

        if target:
            active_list.append(target)

    return active_list


# --- 2. POST/PUT: DÀNH CHO ADMIN (Hệ thống) ---
@router.post("/admin", status_code=status.HTTP_201_CREATED)
async def set_admin_default_threshold(
        req: ThresholdCreate, db: db_dependency, user: user_dependency
):
    if user.get('user_role') != 'admin':
        raise HTTPException(status_code=403, detail="You do not have permission to access this.")

    # Kiểm tra đã có ngưỡng default cho sensor này chưa
    existing = db.query(Threshold).filter(
        Threshold.sensor_type == req.sensor_type,
        Threshold.user_id == None
    ).first()

    if existing:
        existing.min_value = req.min_value
        existing.max_value = req.max_value
        db.commit()
        return {"message": "Updated admin default threshold"}

    new_th = Threshold(**req.model_dump(), user_id=None)
    db.add(new_th)
    db.commit()
    return {"message": "Created admin default threshold"}

#GET dành cho admin để chỉnh sửa ngưỡng mặc định (hệ thống)
@router.get("/admin/defaults", response_model=List[ThresholdResponse])
async def get_admin_thresholds(db: db_dependency, user: user_dependency):
    if user.get('user_role') != 'admin':
        raise HTTPException(status_code=403, detail="Forbidden")


    return db.query(Threshold).filter(Threshold.user_id == None).all()

# --- 3. POST/PUT: DÀNH CHO USER (Cá nhân) ---
@router.post("/user", status_code=status.HTTP_201_CREATED)
async def set_user_custom_threshold(
        req: ThresholdCreate, db: db_dependency, user: user_dependency
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')
    # Tìm xem user này đã từng custom sensor này chưa
    existing = db.query(Threshold).filter(
        Threshold.sensor_type == req.sensor_type,
        Threshold.user_id == user.get('id')
    ).first()

    if existing:
        existing.min_value = req.min_value
        existing.max_value = req.max_value
        db.commit()
        return {"message": "Updated your custom threshold"}

    new_th = Threshold(**req.model_dump(), user_id=user.get('id'))
    db.add(new_th)
    db.commit()
    return {"message": "Created your custom threshold"}


# --- 4. DELETE: USER MUỐN QUAY LẠI DÙNG MẶC ĐỊNH CỦA ADMIN ---
@router.delete("/user/{sensor_type}")
async def reset_to_default(sensor_type: str, db: db_dependency, user: user_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    target = db.query(Threshold).filter(
        Threshold.sensor_type == sensor_type,
        Threshold.user_id == user.get('id')
    ).first()

    if not target:
        raise HTTPException(status_code=404, detail="There's no custom threshold to delete!")

    db.delete(target)
    db.commit()
    return {"message": "Custom Threshold Deleted! Back to Default Threshold"}