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


def calculate_device_pwm(device: Device, latest_sensor: SensorLogs, db: db_dependency) -> int:
    current_hour = datetime.datetime.now().hour

    # MODE 0: OFF
    if device.mode == 0:
        return 0

    # Tách logic kiểm tra thời gian ra để dùng chung
    # Trường hợp đặc biệt: -1 và -1 là chạy suốt 24/24
    if device.start_hour == -1 and device.end_hour == -1:
        in_time = True
    # Trường hợp một trong hai là -1 nhưng không phải cả hai (0 -1, -1 5, ...) -> Không hợp lệ
    elif device.start_hour == -1 or device.end_hour == -1:
        in_time = False
    else:
        if device.start_hour < device.end_hour:
            in_time = device.start_hour <= current_hour < device.end_hour
        else:
            in_time = current_hour >= device.start_hour or current_hour < device.end_hour

    # MODE 2: MANUAL
    if device.mode == 2:
        # Nếu trong khung giờ (hoặc 24/24): bật theo manual_pwm. Ngoài giờ: tắt.
        return device.manual_pwm if in_time else 0

    # MODE 1: AUTO
    if device.mode == 1:
        # Nếu ngoài khung giờ hoạt động -> tắt ngay
        if not in_time:
            return 0

        # Trong khung giờ -> mới bắt đầu kiểm tra cảm biến
        if not latest_sensor:
            return 0

        mapping = {0: 'light', 1: 'temp', 2: 'soil'}
        s_type = mapping.get(device.device_index)


        target_th = db.query(Threshold).filter(
            Threshold.sensor_type == s_type
        ).order_by(Threshold.id.desc()).first()

        if not target_th:
            return 0

        should_run = False
        if s_type == 'light' and latest_sensor.light < target_th.min_value:
            should_run = True
        elif s_type == 'temp' and latest_sensor.temp > target_th.max_value:
            should_run = True
        elif s_type == 'soil' and latest_sensor.soil < target_th.min_value:
            should_run = True

        return device.manual_pwm if should_run else 0

    return 0

DELTA = {
    "temp": 0.5,   # Lệch 0.5 độ C thì ghi
    "humi": 1.0,   # Lệch 1% độ ẩm thì ghi
    "light": 2.0,  # Lệch 2% ánh sáng thì ghi
    "soil": 1.0    # Lệch 1% độ ẩm đất thì ghi
}
# --- 1. POST: NHẬN DỮ LIỆU TỪ ESP32 ---
@router.post("/update-sensor")
@limiter.limit("240/minute")
async def receive_sensor_data(req: SensorLogCreate, db: db_dependency,request: Request):
    current_time = datetime.datetime.now()
    last_log = db.query(SensorLogs).order_by(SensorLogs.timestamp.desc()).first()
    should_save_log = False
    if not last_log:
        should_save_log = True
    else:
        time_diff = (current_time - last_log.timestamp.replace(tzinfo=None)).total_seconds()
        if time_diff >= 300:
            should_save_log = True
        else:
            diff_temp = abs((req.temp or 0) - (last_log.temp or 0))
            diff_humi = abs((req.humi or 0) - (last_log.humi or 0))
            diff_light = abs((req.light or 0) - (last_log.light or 0))
            diff_soil = abs((req.soil or 0) - (last_log.soil or 0))
            if (diff_temp > DELTA["temp"] or
                    diff_humi > DELTA["humi"] or
                    diff_light > DELTA["light"] or
                    diff_soil > DELTA["soil"]):
                should_save_log = True

    if should_save_log:
        new_log = SensorLogs(**req.model_dump())
        db.add(new_log)

    all_users = db.query(Users).all()
    sensor_types = ['temp', 'soil', 'light']

    for user in all_users:
        for s_type in sensor_types:
            current_val = getattr(req, s_type, None)
            if current_val is None: continue
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
@limiter.limit("240/minute")
async def get_latest_sensor(db: db_dependency, user: user_dependency,request: Request):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    latest = db.query(SensorLogs).order_by(SensorLogs.timestamp.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail="No data found")
    return latest


# --- 3. GET: LẤY DANH SÁCH THIẾT BỊ (Bơm, Quạt, Đèn) ---
@router.get("/devices", response_model=List[DeviceResponse])
@limiter.limit("240/minute")
async def get_all_devices(db: db_dependency, user: user_dependency,request: Request):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')
    return db.query(Device).order_by(Device.device_index).all()


@router.post("/control-device")
async def control_device(req: DeviceControlRequest, db: db_dependency, user: user_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    device = db.query(Device).filter(Device.device_index == req.device_index).first()
    if not device:
        raise HTTPException(status_code=404, detail='Device not found!')

    # Cập nhật các field từ request
    if req.mode is not None:
        device.mode = req.mode
    if req.manual_pwm is not None:
        device.manual_pwm = req.manual_pwm
    if req.start_hour is not None:
        device.start_hour = req.start_hour
    if req.end_hour is not None:
        device.end_hour = req.end_hour


    if device.mode == 1:
        is_all_day = (device.start_hour == -1 and device.end_hour == -1)
        is_valid_range = (0 <= device.start_hour <= 23 and
                          0 <= device.end_hour <= 23 and
                          device.start_hour != device.end_hour)

        if not (is_all_day or is_valid_range):
            raise HTTPException(
                status_code=400,
                detail="AUTO mode requires: both hours = -1 (24/7) OR a valid 0-23h range (start != end)"
            )

    # Logic Reset Timer (giữ nguyên nếu bạn muốn xóa sạch hẹn giờ khi sang Manual)
    if req.mode == 2 and req.start_hour is None and req.end_hour is None:
        device.start_hour = -1
        device.end_hour = -1

    db.commit()
    return {"message": f"Configuration for {device.name} updated"}


# --- 5. GET: LẤY LỊCH SỬ CẢNH BÁO ---
@router.get("/notifications")
async def get_notifications(db: db_dependency, user: user_dependency):
    if user is None:
        raise HTTPException(status_code=401,detail="Authentication Failed")

    results = db.query(
        Notification,
        Users.username,Users.role
    ).join(Users, Users.id == Notification.user_id, isouter=True)

    results = results.filter(Users.role != 'admin')

    if user.get('user_role') != 'admin':
        results = results.filter(Notification.user_id == user.get('id'))

    results = results.order_by(Notification.created_at.desc()).limit(100).all()

    return [
        {
            "id": notif.id,
            "sensor_type": notif.sensor_type,
            "message": notif.message,
            "current_value": notif.current_value,
            "threshold_value": notif.threshold_value,
            "created_at": notif.created_at,
            "is_read": notif.is_read,
            "user_id": notif.user_id,
            "username": username if username else "Unknown"
        } for notif, username ,role in results
    ]


@router.put("/notifications/read-all")
async def mark_all_as_read(db: db_dependency, user: user_dependency):
    if user.get('user_role') != 'admin':
        raise HTTPException(status_code=403)

    db.query(Notification).filter(Notification.is_read == False).update({"is_read": True})
    db.commit()
    return {"message": "All notifications marked as read"}


@router.get("/esp32/status")
@limiter.limit("240/minute")
async def get_esp32_commands(db: db_dependency,request:Request):
    latest = db.query(SensorLogs).order_by(SensorLogs.timestamp.desc()).first()
    devices = db.query(Device).order_by(Device.device_index).all()

    pwm_outputs = []
    for d in devices:
        val = calculate_device_pwm(d, latest, db)
        pwm_outputs.append(val)

    return {
        "pwm": pwm_outputs,
        "modes": [d.mode for d in devices]
    }


@router.get("/sensor-history")
async def get_sensor_history(
        db: db_dependency,
        user: user_dependency,
        hours: int = 24,
        max_points: int = 50,
):
    if user is None:
        raise HTTPException(status_code=401,detail='Authentication Failed.')

    cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=hours)
    total_count = db.query(SensorLogs).filter(
        SensorLogs.timestamp >= cutoff_time
    ).count()
    if total_count == 0:
        return []
    if total_count <= max_points:
        logs = db.query(SensorLogs).filter(
            SensorLogs.timestamp >= cutoff_time
        ).order_by(SensorLogs.timestamp).all()
        return format_logs(logs)

    # Nếu nhiều dữ liệu, lấy mẫu
    step = total_count / max_points

    logs = []
    for i in range(max_points):
        offset = int(i * step)
        log = db.query(SensorLogs).filter(
            SensorLogs.timestamp >= cutoff_time
        ).order_by(SensorLogs.timestamp).offset(offset).first()
        if log:
            logs.append(log)

    return format_logs(logs)


def format_logs(logs):
    return [
        {
            "timestamp": log.timestamp.strftime("%H:%M %d/%m"),
            "temp": log.temp,
            "humi": log.humi,
            "light": log.light,
            "soil": log.soil
        }
        for log in logs
    ]