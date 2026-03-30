import datetime
from ..limit import limiter
from ..models.notifications_model import Notification
from ..models.users_model import Threshold, Users
from ..schemas.device_schema import (
    DeviceControlRequest,
    DeviceResponse,
    SensorLogCreate,
    SensorLogResponse
)
from .auth import db_dependency, user_dependency
from fastapi import APIRouter, HTTPException,Request
from typing import List

from ..models.devices_model import Device, SensorLogs

router = APIRouter(
    prefix='/iot',
    tags=['iot']
)

# Ánh xạ cảm biến tới thiết bị (Khớp với logic phần cứng ESP32 của bạn)
# 0: Đèn (Light), 1: Quạt (Temp), 2: Bơm (Soil)
SENSOR_TO_DEVICE_MAP = {
    'temp': 1,
    'soil': 2,
    'light': 0
}


def calculate_device_pwm(device: Device, latest_sensor: SensorLogs, db: db_dependency) -> int:
    current_hour = datetime.datetime.now().hour

    # --- BƯỚC 1: KIỂM TRA HẸN GIỜ ---
    in_time = True
    if device.start_hour != -1 and device.end_hour != -1:
        if device.start_hour < device.end_hour:
            in_time = (device.start_hour <= current_hour < device.end_hour)
        else:
            in_time = (current_hour >= device.start_hour or current_hour < device.end_hour)

    if not in_time: return 0

    # --- BƯỚC 2: CHẾ ĐỘ ---
    if device.mode == 0: return 0
    if device.mode == 2: return device.manual_pwm

    # --- BƯỚC 3: TỰ ĐỘNG (Cần truy vấn Threshold) ---
    if device.mode == 1:
        if not latest_sensor: return 0

        # Ánh xạ ngược lại: Index thiết bị -> Loại cảm biến
        mapping = {0: 'light', 1: 'temp', 2: 'soil'}
        s_type = mapping.get(device.device_index)

        # Lấy ngưỡng (mặc định lấy admin/hệ thống nếu không có user_id cụ thể ở đây)
        # Hoặc lấy ngưỡng chung (user_id == None) cho ESP32
        target_th = db.query(Threshold).filter(Threshold.sensor_type == s_type).order_by(Threshold.user_id.desc()).first()

        if not target_th: return 0

        # Dùng max_value làm ngưỡng kích hoạt (giống logic thông báo của bạn)
        if s_type == 'light':  # Đèn bật khi trời tối (dưới ngưỡng min)
            return device.manual_pwm if latest_sensor.light < target_th.min_value else 0
        if s_type == 'temp':  # Quạt bật khi trời nóng (vượt ngưỡng max)
            return device.manual_pwm if latest_sensor.temp > target_th.max_value else 0
        if s_type == 'soil':  # Bơm bật khi đất khô (dưới ngưỡng min)
            return device.manual_pwm if latest_sensor.soil < target_th.min_value else 0

    return 0

# --- 1. POST: NHẬN DỮ LIỆU TỪ ESP32 ---
@router.post("/update-sensor")
async def receive_sensor_data(req: SensorLogCreate, db: db_dependency):
    new_log = SensorLogs(**req.model_dump())
    db.add(new_log)

    all_users = db.query(Users).all()
    current_time = datetime.datetime.now()
    sensor_types = ['temp', 'soil', 'light']

    for user in all_users:
        for s_type in sensor_types:
            current_val = getattr(req, s_type, None)
            if current_val is None: continue

            # Lấy ngưỡng (ưu tiên user -> mặc định admin)
            target_th = db.query(Threshold).filter(
                Threshold.sensor_type == s_type,
                Threshold.user_id == user.id
            ).first() or db.query(Threshold).filter(
                Threshold.sensor_type == s_type,
                Threshold.user_id == None
            ).first()

            if target_th:
                is_over = current_val > target_th.max_value
                is_under = current_val < target_th.min_value

                # --- LOGIC THÔNG BÁO (GIỮ NGUYÊN) ---
                if is_over or is_under:
                    last_noti = db.query(Notification).filter(
                        Notification.user_id == user.id,
                        Notification.sensor_type == s_type
                    ).order_by(Notification.created_at.desc()).first()

                    should_save = True
                    if last_noti:
                        diff = (current_time - last_noti.created_at.replace(tzinfo=None)).total_seconds()
                        if diff < 300:  # 5 phút mới báo 1 lần
                            should_save = False

                    if should_save:
                        limit_val = target_th.max_value if is_over else target_th.min_value
                        msg = f"Cảnh báo: {s_type} là {current_val}, vượt ngưỡng {limit_val}"
                        db.add(Notification(
                            user_id=user.id,
                            sensor_type=s_type,
                            current_value=current_val,
                            threshold_value=limit_val,
                            message=msg
                        ))
    db.commit()
    return {"message": "Sensor data logged and notifications checked"}

# --- 2. GET: LẤY DỮ LIỆU MỚI NHẤT (Cho màn hình Dashboard trên App) ---
@router.get("/latest-data", response_model=SensorLogResponse)
@limiter.limit("30/minute")
async def get_latest_sensor(db: db_dependency, user: user_dependency,request: Request):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    latest = db.query(SensorLogs).order_by(SensorLogs.timestamp.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail="No data found")
    return latest


# --- 3. GET: LẤY DANH SÁCH THIẾT BỊ (Bơm, Quạt, Đèn) ---
@router.get("/devices", response_model=List[DeviceResponse])
@limiter.limit("30/minute")
async def get_all_devices(db: db_dependency, user: user_dependency,request: Request):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')
    return db.query(Device).order_by(Device.device_index).all()


@router.post("/control-device")
async def control_device(req: DeviceControlRequest, db: db_dependency, user: user_dependency):
    if user is None:
        raise HTTPException(status_code=401)

    device = db.query(Device).filter(Device.device_index == req.device_index).first()
    if not device:
        raise HTTPException(status_code=404)

    # Cập nhật cấu hình (Partial Update)
    if req.mode is not None: device.mode = req.mode
    if req.manual_pwm is not None: device.manual_pwm = req.manual_pwm
    if req.start_hour is not None: device.start_hour = req.start_hour
    if req.end_hour is not None: device.end_hour = req.end_hour

    db.commit()
    # Trả về thông báo thành công, ESP32 sẽ tự cập nhật ở chu kỳ fetch sau (1-3s)
    return {"message": f"Configuration for {device.name} updated"}


# --- 5. GET: LẤY LỊCH SỬ CẢNH BÁO ---
@router.get("/notifications")
async def get_notifications(db: db_dependency, user: user_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    return db.query(Notification) \
        .filter(Notification.user_id == user.get('id')) \
        .order_by(Notification.created_at.desc()) \
        .limit(50) \
        .all()


@router.get("/esp32/status")
async def get_esp32_commands(db: db_dependency):
    latest = db.query(SensorLogs).order_by(SensorLogs.timestamp.desc()).first()
    devices = db.query(Device).order_by(Device.device_index).all()

    for device in devices:
        # Truyền db vào để hàm helper có thể query bảng Threshold
        device.current_value = calculate_device_pwm(device, latest, db)

    db.commit()
    return {
        "pwm": [d.current_value for d in devices],
        "modes": [d.mode for d in devices]
    }


@router.get("/sensor-history")
async def get_sensor_history(
        db: db_dependency,
        user: user_dependency,
        hours: int = 24,
):
    if user is None:
        raise HTTPException(status_code=401)

    cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=hours)

    # Lấy dữ liệu và giới hạn số lượng điểm (ví dụ: tối đa 100 điểm cho biểu đồ đẹp)
    logs = db.query(SensorLogs).filter(
        SensorLogs.timestamp >= cutoff_time
    ).order_by(SensorLogs.timestamp.desc()).limit(100).all()

    # Đảo ngược lại để đúng thứ tự thời gian từ cũ đến mới
    logs.reverse()

    return [
        {
            "timestamp": log.timestamp.strftime("%H:%M %d/%m"),  # Format lại cho FE dễ hiện
            "temp": log.temp,
            "humi": log.humi,
            "light": log.light,
            "soil": log.soil
        }
        for log in logs
    ]