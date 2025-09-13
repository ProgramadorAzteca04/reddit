from app.db.database import Base_secondary as Base
from sqlalchemy import Column, DateTime, Integer, String, func


class Credential(Base):
    """
    Almacena las credenciales de las cuentas de Reddit que utiliza el bot.
    """
    __tablename__ = 'credentials_git'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=False) # En producción, esto debería estar encriptado.
    email = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    proxy = Column(String(255))
    port = Column(String(10))
    def __repr__(self):
        return f"<Credential(username='{self.username}')>"