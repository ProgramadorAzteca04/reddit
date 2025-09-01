from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Table,
    Boolean,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableList

from app.db.database import Base_secondary as Base

# Base para los modelos declarativos de SQLAlchemy
Base = declarative_base()

# --- TABLA DE ASOCIACIÓN PARA INTERACCIONES ---
# Esta tabla no es un modelo, sino una estructura auxiliar que conecta
# a los usuarios (credentials) con las publicaciones (posts).
interaction_association_table = Table(
    'interactions',
    Base.metadata,
    Column('credential_id', Integer, ForeignKey('credentials.id'), primary_key=True),
    Column('post_id', String, ForeignKey('posts.id'), primary_key=True),
    Column('interaction_type', String, default='view'), # Ej: 'view', 'upvote', 'comment'
    Column('interacted_at', DateTime(timezone=True), server_default=func.now())
)

# --- TABLA DE CREDENCIALES ---
class Credential(Base):
    """
    Almacena las credenciales de las cuentas de Reddit que utiliza el bot.
    """
    __tablename__ = 'credentials'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=False) # En producción, esto debería estar encriptado.
    email = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    maduracion = Column(Boolean, server_default='false', nullable=False)
    interacted_posts = relationship(
        "Post",
        secondary=interaction_association_table,
        back_populates="interacting_users"
    )
    def __repr__(self):
        return f"<Credential(username='{self.username}')>"
class Post(Base):
    """
    Almacena la información extraída de una publicación de Reddit.
    """
    __tablename__ = 'posts'

    # Usamos el ID de Reddit como clave primaria para evitar duplicados.
    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    subreddit = Column(String, index=True)
    author = Column(String, index=True)
    score = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    post_url = Column(String, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    interacted_by_credential_ids = Column(MutableList.as_mutable(JSONB), server_default='[]')

    # Relación: Una publicación puede tener interacciones de muchos usuarios.
    interacting_users = relationship(
        "Credential",
        secondary=interaction_association_table,
        back_populates="interacted_posts"
    )

    def __repr__(self):
        return f"<Post(id='{self.id}', title='{self.title[:30]}...')>"
