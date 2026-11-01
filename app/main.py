from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.acquisition.api import router as acquisition_router
from app.normalization.api import router as normalization_router


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(router)
app.include_router(acquisition_router, prefix='/poc')
app.include_router(normalization_router, prefix='/poc')
app.include_router(acquisition_router, prefix='/api/week-1')
app.include_router(normalization_router, prefix='/api/week-2')
