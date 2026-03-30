from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler

from BE.database import Base, engine
from BE.limit import limiter
from BE.routers import auth,users,admin,threshold,device,feedback
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from BE.config.env_config import settings
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"--- System Starting: {settings.env} ---")

    try:
        # Automatically create tables only in development environment
        if settings.env == "development":
            Base.metadata.create_all(bind=engine)
            logger.info("Database: Table configurations checked and updated (Dev Mode)")
        else:
            logger.info("Database: Skipping automatic table creation (Production Mode)")

    except Exception as e:
        logger.error("Database: Initialization failed", exc_info=True)

    yield
    logger.info("--- System Shutdown Safely ---")

app = FastAPI(
title=settings.app_title,
    # Ẩn Swagger/ReDoc nếu đang ở production
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json"
    ,lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount thư mục để có thể xem ảnh qua URL
app.mount("/static", StaticFiles(directory="static"), name="static")
# Cách 2: (Khuyên dùng cho Đồ án) Cho phép tất cả để tránh lỗi phiền phức khi đổi mạng
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Cho phép tất cả các nguồn
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)


@app.get("/")
def home():
    return {"status": "ok", "message": "Backend is running!"}


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(users.router)
app.include_router(threshold.router)
app.include_router(device.router)
app.include_router(feedback.router)