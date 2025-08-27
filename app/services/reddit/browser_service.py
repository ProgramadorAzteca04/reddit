# app/services/reddit/browser_service.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from fastapi import HTTPException
import subprocess
import os
from typing import Optional

class BrowserManager:
    """Gestiona el ciclo de vida del navegador."""
    def __init__(self, chrome_path: str, user_data_dir: str, port: str):
        self.chrome_path = chrome_path
        self.user_data_dir = user_data_dir
        self.port = port
        self.driver: Optional[webdriver.Chrome] = None

    def _launch_chrome(self, command: list):
        """Lanza una instancia de Chrome con la configuración especificada."""
        try:
            # Simplificamos a un Popen estándar. Es más confiable y predecible.
            # La maximización y el enfoque se harán explícitamente después.
            subprocess.Popen(command)
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail=f"No se encontró Chrome en: {self.chrome_path}")
        except Exception as e:
            # Captura de otros posibles errores en diferentes SO.
            print(f"⚠️ No se pudo lanzar Chrome con el método estándar: {e}")
            subprocess.Popen(command)

    def open_chrome_with_debugging(self, url: str) -> None:
        """Abre Chrome con el puerto de depuración remoto activado."""
        # Eliminamos el argumento --start-maximized para evitar conflictos.
        command = [self.chrome_path, f"--remote-debugging-port={self.port}", f"--user-data-dir={self.user_data_dir}", url]
        self._launch_chrome(command)
        print(f"🌐 Chrome (Debug) abierto en el puerto {self.port}")

    def open_chrome_incognito(self, url: str) -> None:
        """Abre una nueva ventana de Chrome en modo incógnito."""
        command = [self.chrome_path, "--incognito", "--start-maximized", url]
        self._launch_chrome(command)
        print(f"🕵️ Chrome (Incognito) abierto en: {url}")

    def connect_to_browser(self):
        """Conecta Selenium to la instancia de Chrome previamente abierta."""
        print("🔗 Conectando Selenium al navegador existente...")
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.port}")
        service = ChromeService(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        print("✅ Selenium conectado exitosamente.")
        return self.driver

    def quit_driver(self):
        """Cierra la conexión de Selenium y finaliza el navegador."""
        if self.driver:
            self.driver.quit()
            print("🚪 Conexión de Selenium cerrada.")
            self.driver = None