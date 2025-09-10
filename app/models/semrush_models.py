# app/models/semrush_models.py
from sqlalchemy import Column, Integer, String, Boolean
from app.db.database import Base_primary as Base

class CredentialSemrush(Base):
    """
    Almacena las credenciales de las cuentas de Semrush.
    """
    __tablename__ = 'credentials_semrush'

    id = Column(Integer, primary_key=True, index=True)
    id_campaigns = Column(Integer, nullable=True)
    email = Column(String(255), unique=True, index=True)
    password = Column(String(255))
    active = Column(Boolean, default=True, nullable=False)
    proxy = Column(String(255))
    port = Column(String(10))
    note = Column(String(255), nullable=True)
    type = Column(Integer, default=1)

    def __repr__(self):
        return f"<CredentialSemrush(email='{self.email}')>"
    
class Campaign(Base):
    """
    Modelo para la tabla de campañas.
    """
    __tablename__ = 'campaigns'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    web = Column(String(255))
    # ... se pueden añadir las otras columnas si se necesitan en el futuro
    
    def __repr__(self):
        return f"<Campaign(id='{self.id}', web='{self.web}')>"