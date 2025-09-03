# app/services/reddit/browser_service.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from fastapi import HTTPException
import subprocess
import os
import zipfile
from typing import Optional, Dict

class BrowserManager:
    """Gestiona el ciclo de vida del navegador, incluyendo la configuración de proxy."""
    
    def __init__(self, chrome_path: str, user_data_dir: str, port: str, proxy: Optional[Dict[str, str]] = None, user_agent: Optional[str] = None):
        self.chrome_path = chrome_path
        self.user_data_dir = user_data_dir
        self.port = port
        self.proxy = proxy
        self.user_agent = user_agent
        self.driver: Optional[webdriver.Chrome] = None

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
        
        # Añadir user-agent si está definido
        if self.user_agent:
            command.append(f'--user-agent={self.user_agent}')
            print(f"   -> 🎭 Usando User-Agent: {self.user_agent}")
        
        # Configurar la extensión del proxy
        proxy_extension_path = self._create_proxy_extension()
        if proxy_extension_path:
            command.append(f'--load-extension={proxy_extension_path}')
            print(f"   -> 🧅 Usando Proxy: {self.proxy['host']}:{self.proxy['port']}")

        command.append(url) # La URL siempre al final
        
        self._launch_chrome(command)
        print(f"🕵️ Chrome (Debug) abierto en el puerto {self.port}")

    def connect_to_browser(self):
        """Conecta Selenium a la instancia de Chrome previamente abierta."""
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