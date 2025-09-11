import os
import random
from datetime import datetime
import re
from typing import Optional
import unicodedata
from openai import OpenAI
from dotenv import load_dotenv

# Carga las variables de entorno desde el archivo .env
load_dotenv()

# Inicializa el cliente de OpenAI con la clave de la API
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
if not client.api_key:
    raise ValueError("No se encontró la API key de OpenAI. Asegúrate de crear un archivo .env con OPENAI_API_KEY='tu-clave'")

def _generate_random_topic(client: OpenAI) -> str:
    """
    Llama a la IA para generar un único tema de debate interesante,
    evitando explícitamente temas de tecnología e IA.
    """
    print("   -> 🧠 Solicitando un nuevo tema a la IA...")
    try:
        prompt_tema = """
        Genera un único tema de debate interesante y atractivo para una publicación en un foro como Reddit.
        El tema debe ser de interés general, invitar a la opinión y ser controversial pero no ofensivo.
        
        IMPORTANTE: No generes temas sobre inteligencia artificial, machine learning, programación,
        tecnología, criptomonedas o cualquier tema técnico relacionado.
        
        Ejemplos de buenos temas:
        - ¿La piña en la pizza es un crimen o una genialidad?
        - Cuál es la película más infravalorada que has visto y por qué.
        - Pequeños hábitos diarios que pueden mejorar tu vida radicalmente.
        
        Responde únicamente con la frase del tema, sin comillas ni texto adicional.
        """
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt_tema}],
            temperature=0.8,
            max_tokens=50,
        )
        topic = response.choices[0].message.content.strip()
        print(f"   -> ✅ Tema recibido: '{topic}'")
        return topic
    except Exception as e:
        print(f"   -> 🚨 Error al generar tema: {e}")
        # En caso de error, devolvemos un tema seguro por defecto
        return "cuál es el mejor consejo financiero que has recibido"

def generate_post_content(model: str = "gpt-4.1", temperature: float = 0.75) -> dict:
    """
    Genera contenido para Reddit de forma autónoma: primero genera un tema
    y luego crea una publicación sobre él, evitando siempre temas de IA.
    """
    # 1. FILTRO DE TEMAS Y VALIDACIÓN
    FORBIDDEN_KEYWORDS = [
        'ia', 'inteligencia artificial', 'ai', 'machine learning',
        'aprendizaje automático', 'deep learning', 'llm', 'gpt',
        'chatgpt', 'gemini', 'claude', 'modelos de lenguaje', 'redes neuronales',
        'prompt engineering', 'programación', 'software', 'código'
    ]
    
    topic = ""
    for attempt in range(3): # Intentamos 3 veces obtener un tema seguro
        generated_topic = _generate_random_topic(client)
        lower_topic = generated_topic.lower()
        
        is_safe = not any(keyword in lower_topic for keyword in FORBIDDEN_KEYWORDS)
        
        if is_safe:
            topic = generated_topic
            break
        else:
            print(f"   -> ⚠️ TEMA DESCARTADO: '{generated_topic}' contiene una palabra clave prohibida. Reintentando...")
    
    if not topic:
        print("   -> 🛑 No se pudo generar un tema seguro. Usando un tema por defecto.")
        topic = "La importancia de desconectar de la tecnología un día a la semana"

    print("\n" + "="*60)
    print(f"🤖 GENERANDO CONTENIDO PARA EL TEMA FINAL: '{topic}'")
    print("="*60)
    
    # 2. OBTENER Y FORMATEAR LA FECHA ACTUAL PARA DAR CONTEXTO
    dias = {
        "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", 
        "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
    }
    meses = {
        "January": "Enero", "February": "Febrero", "March": "Marzo", "April": "Abril", 
        "May": "Mayo", "June": "Junio", "July": "Julio", "August": "Agosto", 
        "September": "Septiembre", "October": "Octubre", "November": "Noviembre", "December": "Diciembre"
    }
    now = datetime.now()
    dia_semana = dias[now.strftime('%A')]
    mes = meses[now.strftime('%B')]
    fecha_actual_formateada = f"{dia_semana}, {now.day} de {mes} de {now.year}"
    contexto_actual = f"Para tu referencia, la fecha actual es {fecha_actual_formateada}. Basa tu redacción en el estado actual del mundo, las tendencias de internet y los eventos relevantes hasta esta fecha."
    print(f"   -> Usando contexto de fecha: {fecha_actual_formateada}")

    # 3. SELECCIÓN ALEATORIA DE ESTILO Y PROTOCOLOS
    tonos = ["informal y cercano, como si hablaras con un amigo", "profesional pero accesible, como un experto explicando algo simple"]
    tipos_de_post = [
        "informativo y útil, que enseñe algo nuevo o práctico a la comunidad",
        "debatible, planteando una pregunta o una opinión que invite a la gente a comentar y discutir"
    ]
    spontaneity_protocols = [
        "iniciar el cuerpo con una pregunta retórica que enganche directamente al lector",
        "incluir una breve anécdota personal (puede ser inventada) para que el post se sienta más real",
        "redactar el cuerpo como si estuvieras pensando en voz alta, usando frases cortas y directas",
        "finalizar el post con una pregunta directa y abierta a la comunidad para fomentar la conversación"
    ]
    post_lengths = [
        "muy corto y directo, de una o dos frases",
        "de un párrafo de tamaño medio, desarrollando un poco la idea",
        "más detallado, de unos 2 o 3 párrafos"
    ]
    tono_elegido = random.choice(tonos)
    tipo_post_elegido = random.choice(tipos_de_post)
    protocolo_elegido = random.choice(spontaneity_protocols)
    largo_elegido = random.choice(post_lengths)
    print(f"   -> Tono elegido: {tono_elegido.split(',')[0]}")
    print(f"   -> Tipo de post: {tipo_post_elegido.split(',')[0]}")
    print(f"   -> Protocolo de espontaneidad: {protocolo_elegido}")
    print(f"   -> Largo elegido: {largo_elegido.split(',')[0]}")

    # 4. INSTRUCCIÓN ALEATORIA PARA AÑADIR UN ERROR SUTIL
    instruccion_de_error = ""
    if random.random() < 0.5: # 50% de probabilidad
        donde_el_error = random.choice(["en el título", "en el cuerpo"])
        instruccion_de_error = f"""
        Para que parezca más real y humano, por favor introduce un único y sutil error de ortografía o puntuación {donde_el_error}.
        Debe ser un error común y creíble, como un error de tipeo (ej: 'prgramar' en vez de 'programar'), omitir una tilde, o una coma faltante. Solo un pequeño error.
        """
        print("   -> Se solicitará un sutil error intencional.")

    # 5. CONSTRUCCIÓN DEL PROMPT FINAL PARA LA IA
    prompt = f"""
    Eres un redactor de contenido experto en crear publicaciones para Reddit que se sienten auténticas y humanas.
    Tu objetivo es evitar sonar como una IA. Escribe de forma natural, directa y como lo haría una persona real en un foro.
    IMPORTANTE: No menciones ni hagas alusión a temas relacionados con inteligencia artificial, machine learning o modelos de lenguaje.

    Tu tarea es generar una publicación sobre el siguiente tema: "{topic}".

    Sigue estas reglas y protocolos estrictamente:
    1.  **Contexto Relevante**: {contexto_actual}
    2.  **Tipo de Contenido**: La publicación debe ser del tipo: {tipo_post_elegido}.
    3.  **Tono**: Utiliza un tono {tono_elegido}.
    4.  **Protocolo de Espontaneidad**: Para que el post suene más natural, debes {protocolo_elegido}.
    5.  **Largo del Cuerpo**: El cuerpo del post debe ser {largo_elegido}. Esta es una regla muy importante.
    6.  **Lenguaje**: Usa un lenguaje sencillo y directo. Evita a toda costa palabras complicadas o un vocabulario demasiado formal. Piensa en cómo hablas, no en cómo escribes un ensayo.
    7.  **Error Sutil**: {instruccion_de_error if instruccion_de_error else "La gramática y ortografía deben ser correctas."}
    8.  **Sin Emojis**: No utilices emojis en ninguna parte del título o del cuerpo. Es una regla estricta.
    
    Por favor, responde estrictamente en el siguiente formato, sin añadir texto adicional antes o después:

    TITULO: [Aquí va el título corto y llamativo]
    CUERPO: [Aquí va el cuerpo del post, respetando la regla de largo y todas las demás]
    """
    
    # 6. LLAMADA A LA API Y MANEJO DE ERRORES
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Eres un asistente de redacción para redes sociales que crea contenido relevante y actual que parece escrito por humanos."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=400,
        )
        
        response_text = response.choices[0].message.content.strip()
        print("   -> Respuesta recibida de la API.")

        if "CUERPO:" not in response_text or "TITULO:" not in response_text:
            raise ValueError("La respuesta de la API no tiene el formato esperado (TITULO:/CUERPO:).")
        
        title_part = response_text.split("CUERPO:")[0]
        title = title_part.replace("TITULO:", "").strip()
        body = response_text.split("CUERPO:")[1].strip()

        print("   -> ✅ Contenido generado y procesado exitosamente.")
        return {"title": title, "body": body}

    except Exception as e:
        print(f"\n🚨 ERROR FATAL al generar contenido con OpenAI: {e}")
        return {"title": "Error de Generación", "body": f"No se pudo generar el contenido: {e}"}
    
def select_best_post_title(titles: list[str]) -> str | None:
    """
    Usa OpenAI para analizar una lista de títulos de Reddit y seleccionar el más interesante,
    evitando explícitamente temas íntimos o sexuales.
    """
    if not titles:
        return None

    print(f"\n🧠 Enviando {len(titles)} títulos a OpenAI para su evaluación...")

    formatted_titles = "\n".join(f"{i+1}. {title}" for i, title in enumerate(titles))

    # --- PROMPT MEJORADO CON REGLAS ESTRICTAS ---
    prompt = f"""
    A continuación se presenta una lista de títulos de publicaciones de un feed de Reddit.
    Tu tarea es actuar como un curador de contenido y seleccionar el título que consideres más interesante y de interés general.

    **REGLAS ESTRICTAS DE FILTRADO:**
    1.  **NO SELECCIONAR** títulos que contengan temas sexuales, eróticos, románticos o íntimos.
    2.  **EVITAR** preguntas sobre relaciones de pareja, experiencias personales de citas o temas similares.
    3.  **PRIORIZAR** temas neutrales, curiosidades, debates divertidos o noticias de interés general.

    Lista de Títulos:
    {formatted_titles}

    Por favor, responde únicamente con el texto exacto del título que has seleccionado y que cumple con todas las reglas, sin números, comillas ni ninguna otra palabra adicional.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Eres un asistente experto en análisis y filtrado de contenido de redes sociales, con un fuerte enfoque en la seguridad de la marca y la decencia."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=100,
        )
        
        selected_title = response.choices[0].message.content.strip()
        print(f"   -> ✅ OpenAI ha seleccionado el título: '{selected_title}'")
        return selected_title

    except Exception as e:
        print(f"   -> 🚨 Error al comunicarse con OpenAI para seleccionar un título: {e}")
        return titles[0] if titles else None
    
def generate_comment_for_post(post_title: str) -> str:
    """
    Genera un comentario relevante y de aspecto humano para un post de Reddit.
    """
    print(f"\n🧠 Generando un comentario para el post: '{post_title}'...")

    tonos = ["de acuerdo y aportando algo más", "ligeramente en desacuerdo pero de forma respetuosa", "haciendo una pregunta relacionada", "compartiendo una experiencia personal breve"]
    estilos = ["directo y corto", "un poco más elaborado, con una o dos frases", "informal, usando jerga de internet"]
    
    tono_elegido = random.choice(tonos)
    estilo_elegido = random.choice(estilos)

    prompt = f"""
    Eres un comentarista de foros experto en participar en conversaciones de forma auténtica.
    Tu objetivo es escribir un comentario que parezca escrito por una persona real, no por una IA.

    El título de la publicación es: "{post_title}"

    Tu tarea es generar un único comentario que sea relevante para este título.
    Sigue estas reglas:
    1.  **Tono y Estilo**: El comentario debe ser {tono_elegido} y tener un estilo {estilo_elegido}.
    2.  **Naturalidad**: Usa un lenguaje casual. Puedes usar alguna falta de ortografía menor o error de tipeo intencional si crees que lo hace más humano (ej. "q" en vez de "que", omitir una tilde).
    3.  **Brevedad**: El comentario debe ser corto, como máximo dos frases.
    4.  **No Emojis**: No uses emojis.
    5.  **Sin IA**: No menciones nada sobre ser una IA, ni temas de tecnología o programación.

    Responde únicamente con el texto del comentario, sin comillas ni texto adicional.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Eres un asistente que genera comentarios para redes sociales que parecen escritos por humanos."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=80,
        )
        comment = response.choices[0].message.content.strip()
        print(f"   -> ✅ Comentario generado: '{comment}'")
        return comment
    except Exception as e:
        print(f"   -> 🚨 Error al generar comentario: {e}")
        return "Estoy totalmente de acuerdo con esto."
    
_USERNAME_ALLOWED = re.compile(r"[^a-z0-9-]")  # todo lo que NO sea permitido
_MULTIDASH = re.compile(r"-{2,}")

_ADJETIVOS = [
    "agil", "bravo", "creativo", "discreto", "epico", "firme", "gentil",
    "humilde", "ingenioso", "jovial", "leal", "noble", "optimista", "prudente",
    "querido", "sereno", "tenaz", "valiente", "vivo", "zen"
]
_SUSTANTIVOS = [
    "avion", "bosque", "cafe", "cactus", "cometa", "delfin", "granito",
    "halcon", "isla", "lince", "marea", "naranja", "panda", "quimera",
    "rio", "sol", "trigal", "ulises", "viento", "zorro"
]

def _strip_accents(s: str) -> str:
    """Convierte 'canción-Ñ' -> 'cancion-n' usando NFKD y eliminando marcas."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

def _sanitize_username(raw: str) -> str:
    """
    Aplica reglas:
    - solo [a-z0-9-]
    - guiones múltiples -> uno
    - sin guion al inicio/fin
    """
    s = raw.lower()
    s = _strip_accents(s)
    s = _USERNAME_ALLOWED.sub("-", s)     # reemplaza caracteres no permitidos por '-'
    s = _MULTIDASH.sub("-", s)            # colapsa --- -> -
    s = s.strip("-")                      # quita guiones en extremos
    return s

def is_valid_username(u: str) -> bool:
    """Validador estricto de la regla pedida."""
    return bool(u) and u == _sanitize_username(u)

def generate_human_username(seed: Optional[int] = None, max_len: int = 20, with_number_prob: float = 0.4) -> str:
    """
    Genera un username humano tipo 'agil-zorro' o 'agil-zorro-27' cumpliendo:
    - solo alfanumérico y '-'
    - no empieza/termina con '-'
    - longitud máxima configurable (default 20)

    Args:
        seed: fija la semilla aleatoria para reproducibilidad (opcional)
        max_len: longitud máxima del username final
        with_number_prob: probabilidad de añadir sufijo numérico

    Returns:
        str: username válido
    """
    rnd = random.Random(seed)

    for _ in range(30):  # hasta 30 intentos por si recortes dejan guion al final
        adj = rnd.choice(_ADJETIVOS)
        noun = rnd.choice(_SUSTANTIVOS)
        base = f"{adj}-{noun}"

        # 40% de las veces, añade un número corto para variedad humana
        if rnd.random() < with_number_prob:
            num = str(rnd.randint(2, 999))  # evita '1' para que no parezca placeholder
            candidate = f"{base}-{num}"
        else:
            candidate = base

        candidate = _sanitize_username(candidate)

        # aplicar límite de longitud sin romper reglas
        if len(candidate) > max_len:
            candidate = candidate[:max_len]
            candidate = candidate.strip("-")           # puede cortar en '-'
            candidate = _MULTIDASH.sub("-", candidate) # por si acaso

        # última garantía de validez
        if is_valid_username(candidate):
            return candidate

    # Fallback ultra seguro si todos los intentos fallaran
    safe = _sanitize_username("usuario-"+str(random.randint(10, 999)))
    if len(safe) > max_len:
        safe = safe[:max_len].strip("-")
    return safe