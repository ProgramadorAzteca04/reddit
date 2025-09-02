# app/services/reddit/comment_service.py
import time
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from app.models.reddit_models import Post
from app.db.database import get_db_secondary
from .browser_service import BrowserManager
import os

def scrape_and_store_comment_as_post(url: str):
    """
    Realiza scraping de un comentario de Reddit usando un navegador real (Selenium) 
    para manejar contenido dinámico y lo guarda como un Post.
    El contenido del comentario se guarda en el campo 'title' del post.
    No requiere inicio de sesión.
    """
    print(f"🚀 Iniciando scraping con Selenium para la URL: {url}")
    
    # --- Configuración del Navegador ---
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")
    DEBUGGING_PORT = "9224"
    
    browser_manager = BrowserManager(CHROME_PATH, USER_DATA_DIR, DEBUGGING_PORT)
    db: Session = next(get_db_secondary())
    driver = None

    try:
        # --- Abrir Navegador y Cargar Página ---
        browser_manager.open_chrome_with_debugging(url)
        print("   -> Esperando 15 segundos a que la página cargue completamente...")
        time.sleep(15)
        
        driver = browser_manager.connect_to_browser()
        if not driver:
            raise ConnectionError("No se pudo conectar Selenium al navegador.")
        
        # --- Extracción de datos del HTML renderizado ---
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'lxml')

        comment_tag = soup.find('shreddit-comment')
        if not comment_tag:
            raise ValueError("No se pudo encontrar la etiqueta del comentario principal (shreddit-comment) después de cargar con Selenium.")
            
        comment_id = comment_tag.get('thingid', '')
        if not comment_id:
             raise ValueError("El comentario no tiene un 'thingid'. No se puede procesar.")

        post_tag = soup.find('shreddit-post')
        subreddit = post_tag.get('subreddit-prefixed-name', 'Subreddit no encontrado') if post_tag else 'Subreddit no encontrado'
        
        author = comment_tag.get('author', 'Autor no encontrado')
        
        comment_body_tag = comment_tag.find("div", {"id": f"{comment_id}-post-rtjson-content"})
        comment_text = ""
        if comment_body_tag:
            for element in comment_body_tag.find_all(['p', 'a']):
                if element.name == 'a':
                    comment_text += f" [{element.get_text(strip=True)}]({element.get('href')}) "
                else:
                    comment_text += element.get_text(strip=True) + "\n"
        else:
            comment_text = "Contenido no disponible"

        print(f"   -> ✅ Datos extraídos: ID={comment_id}, Autor='{author}', Subreddit='{subreddit}'")

        # --- Creación y guardado del objeto Post ---
        existing_post = db.query(Post).filter(Post.id == comment_id).first()
        if existing_post:
            print(f"   -> ⚠️  El comentario con ID '{comment_id}' ya existe. No se guardará de nuevo.")
            return {"status": "skipped", "message": "El comentario ya existe."}

        # AJUSTE: Guardamos el contenido del comentario en el campo 'title'
        new_post = Post(
            id=comment_id,
            title=comment_text.strip(), # <-- Aquí está el cambio
            subreddit=subreddit,
            author=author,
            post_url=url,
            score=int(comment_tag.get('score', 0)),
            comments_count=0 
        )

        db.add(new_post)
        db.commit()
        db.refresh(new_post)

        print(f"   -> 💾 Comentario guardado exitosamente como post con ID: {new_post.id}")
        return {"status": "success", "message": f"Comentario {comment_id} guardado como post."}

    except Exception as e:
        print(f"   -> 🚨 ERROR inesperado durante el scraping o guardado: {e}")
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        if browser_manager:
            browser_manager.quit_driver()
        db.close()
        print("   -> ✅ Navegador cerrado. Fin del proceso de scraping.")