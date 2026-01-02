"""
API Router configuration.
"""
from fastapi import APIRouter
from app.application.api import auth, chat, documents, departments

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(departments.router, prefix="/departments", tags=["departments"])
