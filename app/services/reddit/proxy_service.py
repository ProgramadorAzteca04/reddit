# app/services/reddit/proxy_service.py
import random
from typing import List, Dict, Optional

class ProxyManager:
    """
    Gestiona la carga y selección aleatoria de proxies y agentes de usuario.
    """
    _proxies: List[Dict[str, str]] = []
    _user_agents: List[str] = [
        # Windows / Chrome
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.89 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.6613.120 Safari/537.36",
        # Mac / Safari
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
        # Linux / Firefox
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
        # Edge (Windows 11)
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.6613.85 Safari/537.36 Edg/128.0.2739.67",
                ]

    def __init__(self, file_path: str = 'proxies.txt'):
        if not ProxyManager._proxies:
            self._load_proxies(file_path)

    def _load_proxies(self, file_path: str):
        """Carga los proxies desde el archivo de texto."""
        print(f"📂 Cargando proxies desde '{file_path}'...")
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if len(parts) == 4:
                        proxy = {
                            "host": parts[0],
                            "port": parts[1],
                            "user": parts[2],
                            "pass": parts[3]
                        }
                        ProxyManager._proxies.append(proxy)
            print(f"   -> ✅ {len(ProxyManager._proxies)} proxies cargados exitosamente.")
        except FileNotFoundError:
            print(f"   -> 🚨 ERROR: No se encontró el archivo de proxies en '{file_path}'.")
        except Exception as e:
            print(f"   -> 🚨 ERROR al leer el archivo de proxies: {e}")

    def get_random_proxy(self) -> Optional[Dict[str, str]]:
        """Devuelve un diccionario con los datos de un proxy aleatorio."""
        if not ProxyManager._proxies:
            return None
        return random.choice(ProxyManager._proxies)

    # --- ¡NUEVO MÉTODO AÑADIDO! ---
    def get_proxy_by_host_port(self, host: str, port: str) -> Optional[Dict[str, str]]:
        """
        Busca un proxy por host y puerto en la lista cargada.
        """
        if not host or not port:
            return None
        
        for proxy in ProxyManager._proxies:
            if proxy.get("host") == host and proxy.get("port") == port:
                return proxy
        return None
    # --------------------------------

    def get_random_user_agent(self) -> str:
        """Devuelve una cadena de agente de usuario aleatoria."""
        return random.choice(ProxyManager._user_agents)