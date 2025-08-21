# 🤖 Reddit Bot con FastAPI + PostgreSQL

Un bot de Reddit potente y escalable construido con **FastAPI** para la API, **SQLAlchemy** para el ORM, y **PostgreSQL** como base de datos. Este proyecto utiliza la autenticación OAuth2 de Reddit para interactuar de forma segura con su API, permitiendo guardar y gestionar posts de Reddit.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.95%2B-green?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-10%2B-blue?style=for-the-badge&logo=postgresql)](https://www.postgresql.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0%2B-red?style=for-the-badge&logo=sqlalchemy)](https://www.sqlalchemy.org/)

---

## 🚀 Características

-   **API Rápida y Moderna:** Construido sobre FastAPI, garantizando alto rendimiento y documentación automática (`/docs`).
-   **Base de Datos Robusta:** Utiliza PostgreSQL para un almacenamiento de datos persistente y fiable.
-   **Autenticación Segura:** Implementa el flujo de autenticación OAuth2 de Reddit.
-   **Arquitectura Escalable:** Estructura de proyecto modular que separa la lógica de negocio, el acceso a datos y la API.
-   **Migraciones de Base de Datos:** Integrado con Alembic para gestionar y versionar el esquema de la base de datos.

---

## 📦 Requisitos Previos

-   **Python 3.10+**
-   **PostgreSQL 10+**
-   Una **cuenta de Reddit** con una aplicación configurada (de tipo `script`).
-   **Git** (opcional, para clonar el repositorio).

---

## ⚙️ Guía de Instalación y Puesta en Marcha

### 1. Clonar el Repositorio

```bash
git clone [https://github.com/tu-usuario/reddit-bot.git](https://github.com/tu-usuario/reddit-bot.git)
cd reddit-bot
```

### 2. Crear y Activar un Entorno Virtual

Es una buena práctica trabajar en un entorno virtual para aislar las dependencias del proyecto.

-   **Windows:**
    ```bash
    python -m venv env
    .\env\Scripts\activate
    ```
    *Si encuentras un error de ejecución de scripts, ejecuta este comando en PowerShell como administrador:*
    ```powershell
    Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
    ```

-   **macOS / Linux:**
    ```bash
    python3 -m venv env
    source env/bin/activate
    ```

### 3. Instalar Dependencias

Instala todas las librerías necesarias definidas en `requirements.txt`.

```bash
pip install -r requirements.txt
```

### 4. Configurar las Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto, copiando el ejemplo `.env.example`.

```bash
cp .env.example .env
```

Ahora, edita el archivo `.env` con tus propias credenciales y configuración:

```ini
# Configuración de la Base de Datos
DATABASE_URL="postgresql://user:password@host:port/database_name"

# Credenciales de la API de Reddit
REDDIT_CLIENT_ID="TU_CLIENT_ID_DE_REDDIT"
REDDIT_CLIENT_SECRET="TU_CLIENT_SECRET"
REDDIT_USER_AGENT="MiApp/0.1 by u/tu_usuario"

# Configuración de la App
SECRET_KEY="UNA_LLAVE_SECRETA_MUY_SEGURA_AQUI"
```

### 5. Aplicar Migraciones de la Base de Datos

Para crear las tablas en tu base de datos PostgreSQL, usa Alembic.

```bash
alembic upgrade head
```

### 6. Iniciar la Aplicación

Con todo configurado, inicia el servidor de desarrollo Uvicorn.

```bash
uvicorn app.main:app --reload
```

¡Listo! ✨ La API estará disponible en `http://127.0.0.1:8000`. Puedes acceder a la documentación interactiva en `http://127.0.0.1:8000/docs`.

---

## 📁 Estructura del Proyecto

El proyecto sigue una arquitectura modular para mantener el código organizado y escalable.

```
.
├── app/                  # 📦 Carpeta principal de la aplicación FastAPI.
│   ├── api/              # 🌐 Contiene los endpoints de la API.
│   │   └── v1/
│   │       └── endpoints/
│   ├── core/             # ⚙️ Configuración central de la aplicación.
│   ├── db/               # 💾 Módulos de base de datos.
│   ├── models/           # 🏛️ Define los modelos de datos de SQLAlchemy.
│   ├── schemas/          # 📝 Define los esquemas de validación de datos con Pydantic.
│   ├── services/         # 🧠 Lógica de negocio de la aplicación.
│   └── main.py           # 🚀 Punto de entrada que inicia la aplicación FastAPI.
├── .env                  # Archivo de variables de entorno (ignorado por Git).
├── .env.example          # Archivo de ejemplo para las variables de entorno.
└── requirements.txt      # Lista de dependencias de Python.
```