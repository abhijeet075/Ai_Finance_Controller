from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.uploads import router as uploads_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="AI Finance Controller",
    version="0.18.0",
    description="Evidence-based reconciliation and cash forecasting API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(uploads_router, prefix="/upload", tags=["uploads"])
app.include_router(api_router, prefix="/api")
