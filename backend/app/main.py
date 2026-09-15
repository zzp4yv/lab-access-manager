from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models import Admin
from app.routers import admins, auth, dashboard, users
from app.security import hash_password
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")

settings = get_settings()


def bootstrap_admin() -> None:
    """Cria o primeiro administrador a partir de variáveis de ambiente,
    caso nenhum exista ainda. Evita ficar sem acesso ao sistema em um
    deploy limpo (ver BOOTSTRAP_ADMIN_* em .env.example)."""
    if not settings.BOOTSTRAP_ADMIN_EMAIL or not settings.BOOTSTRAP_ADMIN_PASSWORD:
        return

    db = SessionLocal()
    try:
        existing = db.query(Admin).count()
        if existing > 0:
            return
        admin = Admin(
            full_name=settings.BOOTSTRAP_ADMIN_NAME,
            email=settings.BOOTSTRAP_ADMIN_EMAIL.lower(),
            hashed_password=hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD),
        )
        db.add(admin)
        db.commit()
        logger.info("Administrador inicial criado: %s", admin.email)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    bootstrap_admin()
    start_scheduler()
    logger.info("Aplicação iniciada em modo de provisionamento: %s", settings.PROVISIONING_MODE)
    yield
    stop_scheduler()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admins.router)
app.include_router(dashboard.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "environment": settings.ENVIRONMENT, "provisioning_mode": settings.PROVISIONING_MODE}


# Serve o frontend estático (HTML/CSS/JS puro, sem etapa de build) a
# partir do mesmo container/processo do backend, simplificando o
# docker-compose para um único serviço.
if os.path.isdir(settings.FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=settings.FRONTEND_DIR, html=True), name="frontend")
else:  # pragma: no cover - apenas em ambientes sem a pasta frontend presente
    logger.warning("Diretório de frontend não encontrado em %s; servindo apenas a API.", settings.FRONTEND_DIR)
