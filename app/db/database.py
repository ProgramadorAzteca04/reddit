from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings

settings = get_settings()

# 🔁 Motor sincrónico
engine = create_engine(settings.DATABASE_URL, echo=True)

# 🔁 Session sincrónica
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 🔁 Dependencia para obtener la sesión
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
