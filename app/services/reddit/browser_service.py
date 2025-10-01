# app/services/reddit/browser_service.py
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import os
from typing import Optional, Dict
from selenium.webdriver.chrome.options import Options
from fastapi import HTTPException
import subprocess
import zipfile

# Importaciones específicas para cada clase
from selenium import webdriver as standard_webdriver
from seleniumwire import webdriver as wire_webdriver

class BrowserManager:
    """Gestiona el ciclo de vida del navegador, incluyendo la configuración de proxy."""
    
    def __init__(self, chrome_path: str, user_data_dir: str, port: str, proxy: Optional[Dict[str, str]] = None, user_agent: Optional[str] = None):
        self.chrome_path = chrome_path
        self.user_data_dir = user_data_dir
        self.port = port
        self.proxy = proxy
        self.user_agent = user_agent
        self.driver: Optional[standard_webdriver.Chrome] = None

    def _create_proxy_extension(self) -> Optional[str]:
        """Crea una extensión de Chrome para la autenticación del proxy."""
        if not self.proxy:
            return None

        manifest_json = """
        {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Chrome Proxy Auth",
            "permissions": [
                "proxy", "tabs", "unlimitedStorage", "storage",
                "<all_urls>", "webRequest", "webRequestBlocking"
            ],
            "background": { "scripts": ["background.js"] },
            "minimum_chrome_version":"22.0.0"
        }
        """
        background_js = f"""
        var config = {{
            mode: "fixed_servers",
            rules: {{
              singleProxy: {{
                scheme: "http",
                host: "{self.proxy['host']}",
                port: parseInt({self.proxy['port']})
              }},
              bypassList: ["localhost"]
            }}
          }};
        chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
        function callbackFn(details) {{
            return {{
                authCredentials: {{
                    username: "{self.proxy['user']}",
                    password: "{self.proxy['pass']}"
                }}
            }};
        }}
        chrome.webRequest.onAuthRequired.addListener(
                    callbackFn,
                    {{urls: ["<all_urls>"]}},
                    ['blocking']
        );
        """
        
        plugin_dir = os.path.join(os.getcwd(), 'proxy_extension')
        if not os.path.exists(plugin_dir):
            os.makedirs(plugin_dir)
            
        manifest_path = os.path.join(plugin_dir, 'manifest.json')
        background_path = os.path.join(plugin_dir, 'background.js')
        
        with open(manifest_path, 'w') as f:
            f.write(manifest_json)
        with open(background_path, 'w') as f:
            f.write(background_js)
            
        return plugin_dir

    def _launch_chrome(self, command: list):
        """Lanza una instancia de Chrome con la configuración especificada."""
        try:
            subprocess.Popen(command)
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail=f"No se encontró Chrome en: {self.chrome_path}")
        except Exception as e:
            print(f"⚠️ No se pudo lanzar Chrome con el método estándar: {e}")
            subprocess.Popen(command)

    def open_chrome_with_debugging(self, url: str) -> None:
        """Abre Chrome con depuración remota, proxy y user-agent personalizados."""
        command = [
            self.chrome_path,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.user_data_dir}",
        ]
        
        if self.user_agent:
            command.append(f'--user-agent={self.user_agent}')
            print(f"   -> 🎭 Usando User-Agent: {self.user_agent}")
        
        proxy_extension_path = self._create_proxy_extension()
        if proxy_extension_path:
            command.append(f'--load-extension={proxy_extension_path}')
            print(f"   -> 🧅 Usando Proxy: {self.proxy['host']}:{self.proxy['port']}")

        command.append(url)
        
        self._launch_chrome(command)
        print(f"🕵️ Chrome (Debug) abierto en el puerto {self.port}")

    def connect_to_browser(self):
        """Conecta Selenium a la instancia de Chrome previamente abierta."""
        print("🔗 Conectando Selenium al navegador existente...")
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.port}")
        service = ChromeService(ChromeDriverManager().install())
        self.driver = standard_webdriver.Chrome(service=service, options=chrome_options)
        print("✅ Selenium conectado exitosamente.")
        return self.driver

    def quit_driver(self):
        """Cierra la conexión de Selenium y finaliza el navegador."""
        if self.driver:
            self.driver.quit()
            print("🚪 Conexión de Selenium cerrada.")
            self.driver = None

class BrowserManagerProxy:
    """Gestiona el ciclo de vida del navegador usando selenium-wire para un manejo de proxy robusto."""
    
    def __init__(self, chrome_path: str, user_data_dir: str, port: str, proxy: Optional[Dict[str, str]] = None, user_agent: Optional[str] = None):
        self.chrome_path = chrome_path
        self.user_data_dir = user_data_dir
        self.proxy = proxy
        self.user_agent = user_agent
        self.driver: Optional[wire_webdriver.Chrome] = None

    def get_configured_driver(self, url: str) -> Optional[wire_webdriver.Chrome]:
        """
        Configura y lanza una instancia de Chrome controlada por selenium-wire.
        """
        print("🚀 Configurando una nueva instancia de Chrome con Selenium-Wire...")
        
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

        chrome_options = wire_webdriver.ChromeOptions()
        chrome_options.add_argument("--incognito")
        
        if self.user_agent:
            chrome_options.add_argument(f'--user-agent={self.user_agent}')
            print(f"   -> 🎭 Usando User-Agent: {self.user_agent}")
        
        chrome_options.add_argument(f"--user-data-dir={self.user_data_dir}")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument('--ignore-certificate-errors')
        
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        print("   -> 🕵️  Aplicando opciones para ocultar la automatización.")
        
        chrome_options.add_argument('--log-level=3')
        print("   -> 🤫 Configurando nivel de log para una salida limpia.")

        try:
            service = ChromeService(ChromeDriverManager().install())
            
            self.driver = wire_webdriver.Chrome(
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