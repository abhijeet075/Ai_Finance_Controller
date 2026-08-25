from fastapi import APIRouter

from app.api import exceptions, forecast, health, reconciliation, transactions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
api_router.include_router(reconciliation.router, prefix="/reconciliation", tags=["reconciliation"])
api_router.include_router(exceptions.router, prefix="/exceptions", tags=["exceptions"])
api_router.include_router(forecast.router, prefix="/forecast", tags=["forecast"])
