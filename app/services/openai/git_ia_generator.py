# app/services/openai/git_ia_generator.py
import os
import random
from openai import OpenAI
from dotenv import load_dotenv

# Carga las variables de entorno desde el archivo .env
load_dotenv()

# Inicializa el cliente de OpenAI (comparte la misma configuración que otros servicios)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
if not client.api_key:
    raise ValueError("No se encontró la API key de OpenAI. Asegúrate de que esté configurada en tu archivo .env")

def generate_north_american_name(gender: str = "any") -> str:
    """
    Llama a la IA de OpenAI para generar un nombre y apellido común de Norteamérica.

    Args:
        gender (str): El género para el nombre ('male', 'female', o 'any'). 
                      Por defecto es 'any' para un nombre aleatorio.

    Returns:
        str: Un nombre completo (ej. "John Smith").
    """
    print("   -> 🧠 Solicitando un nombre norteamericano a la IA...")

    # Validar la entrada de género para mayor seguridad
    gender_prompt = "unisex"
    if gender.lower() == "male":
        gender_prompt = "masculino"
    elif gender.lower() == "female":
        gender_prompt = "femenino"

    prompt = f"""
    Genera un único nombre completo (nombre y apellido) que sea común en Norteamérica (Estados Unidos o Canadá).
    El nombre debe ser creíble y sonar natural.
    
    Género solicitado: {gender_prompt}.

    Ejemplos de formato correcto:
    - Michael Johnson
    - Jessica Williams
    - Chris Miller

    Por favor, responde únicamente con el nombre completo, sin texto adicional, comillas o saludos.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Eres un asistente generador de datos personales realistas."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9,
            max_tokens=10,
        )
        
        name = response.choices[0].message.content.strip()
        
        # Una pequeña validación para asegurar que el formato es correcto (dos palabras)
        if len(name.split()) == 2:
            print(f"   -> ✅ Nombre generado: '{name}'")
            return name
        else:
            # Si la IA devuelve algo inesperado, usamos un nombre por defecto
            print(f"   -> ⚠️ La IA devolvió un formato inesperado: '{name}'. Usando un nombre por defecto.")
            return "Alex Taylor"

    except Exception as e:
        print(f"   -> 🚨 Error al generar el nombre con OpenAI: {e}")
        # En caso de error, devolvemos un nombre seguro por defecto
        return "Alex Taylor"

def generate_tech_bio(name: str) -> str:
    """
    Genera una biografía breve, profesional y natural para un perfil, centrada en tecnología.
    """
    print(f"   -> 🧠 Generando una biografía tecnológica para '{name}'...")
    
    # --- Elementos para aleatorizar el prompt y hacerlo más natural ---
    tech_interests = [
        "el desarrollo web full-stack", "Python y el machine learning", "la ciberseguridad",
        "el desarrollo de aplicaciones móviles", "la computación en la nube y DevOps",
        "crear experiencias de usuario intuitivas con tecnologías front-end",
        "el código abierto y las comunidades de desarrolladores", "la ciencia de datos y la visualización"
    ]
    personal_touches = [
        "En mi tiempo libre, disfruto contribuyendo a proyectos de código abierto.",
        "Siempre estoy aprendiendo y explorando nuevas tecnologías.",
        "Me encanta resolver problemas complejos con código limpio y eficiente.",
        "Apasionado por transformar ideas en soluciones de software funcionales.",
        "Busco conectar con otros desarrolladores y aprender de la comunidad."
    ]
    structures = [
        "Un desarrollador de software enfocado en {interest}. {touch}",
        "Un ingeniero de software especializado en {interest}. {touch}",
        "Entusiasta de la tecnología con experiencia en {interest}. {touch}",
        "Apasionado por {interest}. {touch}",
    ]

    # --- Seleccionar elementos aleatorios ---
    selected_interest = random.choice(tech_interests)
    selected_touch = random.choice(personal_touches)
    selected_structure = random.choice(structures)
    bio_template = selected_structure.format(interest=selected_interest, touch=selected_touch)

    # --- Construir el prompt con reglas estrictas ---
    prompt = f"""
    Eres un redactor experto en crear biografías para perfiles de tecnología como GitHub. Tu objetivo es sonar 100% humano, creíble y natural.

    La biografía es para una persona llamada {name}.
    Basándote en la siguiente plantilla, reescríbela ligeramente para que suene más personal y fluida. Puedes cambiar palabras, pero mantén la idea central.

    Plantilla: "{bio_template}"

    REGLAS ESTRICTAS PARA EVITAR SPAM Y CLICHÉS:
    1.  **NO USAR** jerga corporativa o palabras de moda como "ninja", "rockstar", "gurú", "disruptivo", "sinergia" o "evangelista".
    2.  **SER CONCISO**: Máximo dos frases.
    3.  **SONAR HUMILDE**: Evita un lenguaje arrogante o exagerado.
    4.  **SER ESPECÍFICO PERO ACCESIBLE**: Menciona una tecnología pero de forma que se entienda el interés general.

    Responde únicamente con el texto final de la biografía, sin comillas ni texto adicional.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Eres un asistente que redacta biografías profesionales, naturales y concisas para perfiles de desarrolladores."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=60,
        )
        
        bio = response.choices[0].message.content.strip()
        print(f"   -> ✅ Biografía generada: '{bio}'")
        return bio

    except Exception as e:
        print(f"   -> 🚨 Error al generar la biografía con OpenAI: {e}")
        # Biografía por defecto en caso de error
        return "Software developer passionate about open-source and building useful tools."


# --- Ejemplo de uso (puedes ejecutar este archivo directamente para probarlo) ---
if __name__ == '__main__':
    print("Probando la generación de nombres:")
    random_name = generate_north_american_name()
    print(f"Nombre aleatorio: {random_name}\n")
    
    male_name = generate_north_american_name(gender="male")
    print(f"Nombre masculino: {male_name}\n")

    female_name = generate_north_american_name(gender="female")
    print(f"Nombre femenino: {female_name}\n")

    # --- NUEVO: Probando la generación de biografía ---
    print("Probando la generación de biografías:")
    test_name = "Chris Miller"
    bio = generate_tech_bio(test_name)
    print(f"Biografía para {test_name}: {bio}\n")

    # Flujo completo
    new_name = generate_north_american_name()
    new_bio = generate_tech_bio(new_name)
    print(f"--- Perfil Completo Generado ---")
    print(f"Nombre: {new_name}")
    print(f"Biografía: {new_bio}")
    print(f"---------------------------------")

