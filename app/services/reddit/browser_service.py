# app/services/reddit/browser_service.py
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import os
from typing import Optional, Dict

class BrowserManager:
    """Gestiona el ciclo de vida del navegador usando selenium-wire para un manejo de proxy robusto."""
    
    def __init__(self, chrome_path: str, user_data_dir: str, port: str, proxy: Optional[Dict[str, str]] = None, user_agent: Optional[str] = None):
        self.chrome_path = chrome_path
        self.user_data_dir = user_data_dir
        self.proxy = proxy
        self.user_agent = user_agent
        self.driver: Optional[webdriver.Chrome] = None

    def get_configured_driver(self, url: str) -> Optional[webdriver.Chrome]:
        """
        Configura y lanza una instancia de Chrome controlada por selenium-wire.
        """
        print("🚀 Configurando una nueva instancia de Chrome con Selenium-Wire...")
        
        # --- Configuración de Selenium-Wire ---
        seleniumwire_options = {}
        if self.proxy:
            proxy_options = {
                'proxy': {
                    'http': f"socks5://{self.proxy['user']}:{self.proxy['pass']}@{self.proxy['host']}:{self.proxy['port']}",
                    'https': f"socks5://{self.proxy['user']}:{self.proxy['pass']}@{self.proxy['host']}:{self.proxy['port']}",
                    'no_proxy': 'localhost,127.0.0.1'
                }
            }
            seleniumwire_options.update(proxy_options)
            print(f"   -> 🧅 Usando Proxy SOCKS5 (vía Selenium-Wire): {self.proxy['host']}:{self.proxy['port']}")

        # --- Configuración de Opciones de Chrome ---
        chrome_options = webdriver.ChromeOptions()
        
        if self.user_agent:
            chrome_options.add_argument(f'--user-agent={self.user_agent}')
            print(f"   -> 🎭 Usando User-Agent: {self.user_agent}")
        
        chrome_options.add_argument(f"--user-data-dir={self.user_data_dir}")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument('--ignore-certificate-errors')
        
        # --- Opciones para ocultar la automatización ---
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        print("   -> 🕵️  Aplicando opciones para ocultar la automatización.")
        
        chrome_options.add_argument('--log-level=3')
        print("   -> 🤫 Configurando nivel de log para una salida limpia.")

        try:
            service = ChromeService(ChromeDriverManager().install())
            
            self.driver = webdriver.Chrome(
                service=service, 
                options=chrome_options,
                seleniumwire_options=seleniumwire_options
            )
            
            print("   -> ✅ Navegador lanzado y controlado por Selenium-Wire.")
            self.driver.get(url)
            return self.driver
            
        except Exception as e:
            print(f"🚨 ERROR FATAL al lanzar el navegador con Selenium-Wire: {e}")
            self.quit_driver()
            return None

    def quit_driver(self):
        """Cierra la conexión de Selenium y finaliza el navegador."""
        if self.driver:
            self.driver.quit()
            print("🚪 Conexión de Selenium cerrada.")
            self.driver = None