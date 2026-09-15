from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    # Garante que o diretório do arquivo SQLite exista.
    db_path = settings.DATABASE_URL.split("///")[-1]
    if db_path and db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Cria as tabelas caso ainda não existam.

    Para um ambiente com múltiplas versões evolutivas do schema,
    recomenda-se migrar para Alembic; aqui usamos create_all pois o
    projeto foi definido para rodar sobre SQLite em um único container.
    """
    from app import models  # noqa: F401 garante que os modelos sejam registrados

    Base.metadata.create_all(bind=engine)
