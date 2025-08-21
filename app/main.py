# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.openapi.docs import get_swagger_ui_html

from app.core.config import get_settings
from app.api.v1.endpoints import reddit

settings = get_settings()

# Crear app sin docs por defecto (los proveemos custom más abajo)
app = FastAPI(
    title="My FastAPI App",
    debug=settings.DEBUG,
    version="1.0.0",
    docs_url=None,     # 👈 desactiva docs por defecto
    redoc_url=None,    # (opcional) desactiva ReDoc
)

# Rutas de tu API
app.include_router(
    reddit.router,
    prefix="/reddit",
    tags=["Reddit Automation"]
)

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Bienvenido a la API de Reddit Clone"}

# =========================
#  Swagger UI: Dark Mode
# =========================
# CSS: importa el CSS oficial y aplica overrides solo en modo oscuro.
DARK_CSS = """
@import url('https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui.css');

@media (prefers-color-scheme: dark) {
  :root {
    --primary: #7aa2f7;
    --bg: #0f172a;
    --panel: #111827;
    --text: #e5e7eb;
    --muted: #9ca3af;
    --border: #1f2937;
    --code-bg: #0b1020;
    --link: #93c5fd;
  }

  html, body {
    background-color: var(--bg) !important;
    color: var(--text) !important;
  }

  .swagger-ui .topbar,
  .swagger-ui .scheme-container,
  .swagger-ui .info,
  .swagger-ui .opblock,
  .swagger-ui .opblock .opblock-section-header,
  .swagger-ui .model,
  .swagger-ui .response-col_description__inner,
  .swagger-ui .modal-ux {
    background: var(--panel) !important;
    color: var(--text) !important;
    border-color: var(--border) !important;
  }

  .swagger-ui .opblock-tag,
  .swagger-ui .info .title,
  .swagger-ui .info .base-url,
  .swagger-ui .info .version-stamp {
    color: var(--text) !important;
  }

  .swagger-ui .markdown code,
  .swagger-ui .highlight-code pre {
    background: var(--code-bg) !important;
    color: var(--text) !important;
  }

  .swagger-ui .btn, .swagger-ui .btn.authorize {
    background: var(--primary) !important;
    color: #071018 !important;
    border-color: transparent !important;
  }

  .swagger-ui a, .swagger-ui .info a, .swagger-ui .opblock a {
    color: var(--link) !important;
  }

  /* bordes por método */
  .swagger-ui .opblock.opblock-get     { border-color: #3b82f6 !important; }
  .swagger-ui .opblock.opblock-post    { border-color: #10b981 !important; }
  .swagger-ui .opblock.opblock-put     { border-color: #f59e0b !important; }
  .swagger-ui .opblock.opblock-delete  { border-color: #ef4444 !important; }

  /* inputs */
  .swagger-ui input[type=text],
  .swagger-ui textarea,
  .swagger-ui select {
    background: var(--bg) !important;
    color: var(--text) !important;
    border-color: var(--border) !important;
  }
}

"""

@app.get("/swagger-ui-dark.css", include_in_schema=False)
def swagger_ui_dark_css():
    return Response(content=DARK_CSS, media_type="text/css")

@app.get("/docs", include_in_schema=False)
def custom_swagger_ui():
    """Swagger UI con modo oscuro (auto por prefers-color-scheme)."""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} — Docs",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui-bundle.js",
        swagger_css_url="/swagger-ui-dark.css",  # 👈 aplicamos nuestro CSS
    )
