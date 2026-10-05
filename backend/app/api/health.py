from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import check_database_connection


router = APIRouter()


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "fusionhcm-360-api",
    }


@router.get("/health/database")
def database_health_check():
    try:
        check_database_connection()

        return {
            "status": "ok",
            "database": "connected",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        )