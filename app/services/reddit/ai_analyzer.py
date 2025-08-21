import os, base64, json
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()                 # Lee OPENAI_API_KEY del entorno/.env
_client = OpenAI()            # Usa automáticamente OPENAI_API_KEY

# === JSON Schema para Structured Outputs ===
_ANALYSIS_SCHEMA = {
    "name": "RedditPostAnalysis",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "maxLength": 400},
            "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
            "topics": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            "spam_risk": {"type": "number", "minimum": 0, "maximum": 1},
            "is_promotional": {"type": "boolean"},
            "toxicity": {"type": "number", "minimum": 0, "maximum": 1},
            "suggested_action": {"type": "string", "enum": ["upvote", "skip", "comment", "save"]},
            "reasons": {"type": "array", "items": {"type": "string"}, "maxItems": 6}
        },
        # 👇 Con strict=True, TODAS las claves deben ir en required
        "required": [
            "summary",
            "sentiment",
            "topics",
            "spam_risk",
            "is_promotional",
            "toxicity",
            "suggested_action",
            "reasons"
        ],
        "additionalProperties": False
    },
    "strict": True  # mantiene salidas 100% conformes al schema
}

@dataclass
class PostContext:
    url: Optional[str] = None
    subreddit: Optional[str] = None
    title_hint: Optional[str] = None

def _to_data_url_png(png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    return f"data:image/png;base64,{b64}"

def analyze_publication(
    *,
    image_bytes: Optional[bytes] = None,
    text: Optional[str] = None,
    context: Optional[PostContext] = None,
    model: str = "gpt-4o-mini"
) -> Dict[str, Any]:
    """
    Analiza una publicación de Reddit (texto e/o imagen).
    Devuelve JSON validado por schema: summary, sentiment, topics, spam_risk,
    is_promotional, toxicity, suggested_action, reasons.
    Implementado con Chat Completions + response_format (Structured Outputs).
    """
    # 1) Construir el contenido del mensaje del usuario
    lines = [
        "Analiza esta publicación de Reddit y responde SOLO con JSON.",
        "Evalúa: resumen corto, sentimiento, hasta 8 temas, riesgo de spam (0-1), si es promocional, toxicidad (0-1) y acción sugerida (upvote/skip/comment/save) con razones."
    ]
    if context:
        if context.url:        lines.append(f"URL: {context.url}")
        if context.subreddit:  lines.append(f"Subreddit: {context.subreddit}")
        if context.title_hint: lines.append(f"Título (hint): {context.title_hint}")
    if text:
        lines.append(f"Texto capturado:\n{text}")

    user_content: List[Dict[str, Any]] = [{"type": "text", "text": "\n".join(lines)}]

    # 2) Adjuntar screenshot como data URL si viene
    if image_bytes:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": _to_data_url_png(image_bytes)}
        })

    # 3) Llamada a Chat Completions con Structured Outputs (JSON Schema)
    completion = _client.chat.completions.create(
        model=model,  # p. ej. "gpt-4o-mini"
        messages=[
            {"role": "system", "content": "Eres un analista y devuelves SOLO JSON válido."},
            {"role": "user", "content": user_content},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": _ANALYSIS_SCHEMA
        },
        temperature=0
    )

    # 4) Parsear el JSON devuelto
    content = completion.choices[0].message.content or ""
    try:
        return json.loads(content)
    except Exception as e:
        return {"error": f"json_parse_failed: {e}", "raw": content}