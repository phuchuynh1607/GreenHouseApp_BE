import os
from pydantic_settings import BaseSettings
from pathlib import Path

# Xác định đường dẫn tới file .env (ở thư mục gốc project)
# Từ EcommerceApp/core/config.py nhảy lên 2 cấp để thấy .env
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    env: str = "development"
    app_title: str = "FastAPI"

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    class Config:
        # Chỉ định file .env nằm ở thư mục gốc
        env_file = os.path.join(BASE_DIR, ".env")
        extra = "ignore" # Bỏ qua các biến thừa trong .env không có trong class này

settings = Settings()