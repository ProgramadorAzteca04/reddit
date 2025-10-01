# app/db/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import get_settings

settings = get_settings()

# --- Conexión a la Base de Datos Principal ---
engine_primary = create_engine(settings.DATABASE_URL, echo=False)
SessionLocal_primary = sessionmaker(autocommit=False, autoflush=False, bind=engine_primary)
Base_primary = declarative_base() # Base para los modelos de la BD principal

# --- Conexión a la Base de Datos Secundaria (para los modelos de Reddit) ---
engine_secondary = create_engine(settings.SECOND_DATABASE_URL, echo=False)
SessionLocal_secondary = sessionmaker(autocommit=False, autoflush=False, bind=engine_secondary)
Base_secondary = declarative_base() # Base para los modelos de la BD secundaria

# --- Dependencia para obtener la sesión de la BD Principal ---
def get_db():
    db = SessionLocal_primary()
    try:
        yield db
    finally:
        db.close()

# --- Dependencia para obtener la sesión de la BD Secundaria ---
def get_db_secondary():
    db = SessionLocal_secondary()
    try:
        yield db
    finally:
        db.close()