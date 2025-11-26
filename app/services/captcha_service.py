# app/services/captcha_service.py
import os
import time
import json
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# 👇 NUEVOS imports para helpers de iframes
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

load_dotenv()

class TwoCaptchaSolver:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TWOCAPTCHA_API_KEY")
        if not self.api_key:
            raise ValueError("TWOCAPTCHA_API_KEY is missing.")
        self.base_url = "http://2captcha.com/in.php"
        self.res_url = "http://2captcha.com/res.php"

    def _send_request(self, url: str, data: Dict[str, Any], method: str = "post",
                      tolerate_not_ready: bool = False) -> Optional[Dict[str, Any]]:
        try:
            resp = requests.post(url, data=data, timeout=60) if method == "post" \
                   else requests.get(url, params=data, timeout=60)
            resp.raise_for_status()
            raw = resp.text
            if "ERROR" in raw and not raw.strip().startswith("{"):
                print(f"🚨 2Captcha Error: {raw}")
                return None
            try:
                data = resp.json()
            except json.JSONDecodeError:
                print(f"🚨 Respuesta no JSON: {raw}")
                return None
            if data.get("status") == 0 and not (tolerate_not_ready and data.get("request") == "CAPCHA_NOT_READY"):
                print(f"🚨 2Captcha: {data.get('request')}")
                return None
            return data
        except requests.RequestException as e:
            print(f"🚨 Error de red 2Captcha: {e}")
            return None

    def solve(self, method: str, poll_interval_sec: int = 5, max_wait_sec: int = 240, **kwargs) -> Optional[str]:
        payload = {"key": self.api_key, "method": method, "json": 1, **kwargs}
        print(f"🤖 Solicitando a 2Captcha: method={method}")
        rq = self._send_request(self.base_url, payload, method="post")
        if not rq: return None
        cap_id = rq.get("request")
        print(f"✅ Captcha ID: {cap_id}")

        deadline = time.time() + max_wait_sec
        while time.time() < deadline:
            time.sleep(poll_interval_sec)
            res = self._send_request(self.res_url, {
                "key": self.api_key, "action": "get", "id": cap_id, "json": 1
            }, method="get", tolerate_not_ready=True)
            if not res: return None
            if res.get("status") == 1 and res.get("request"):
                print("🎉 ¡Token recibido!")
                return res["request"]
            if res.get("request") != "CAPCHA_NOT_READY":
                print(f"🚨 2Captcha devolvió: {res.get('request')}")
                return None
            print("… Aún no listo. Reintentando…")
        print("🚨 Timeout esperando el token.")
        return None

    # --------- Helpers de alto nivel ----------
    def solve_recaptcha_v2_invisible(self, page_url: str, sitekey: str,
                                     data_s: Optional[str] = None,
                                     enterprise: bool = False,
                                     user_agent: Optional[str] = None,
                                     **extra) -> Optional[str]:
        """
        Para reCAPTCHA v2 invisible (incl. enterprise).
        """
        kwargs = {
            "googlekey": sitekey,
            "pageurl": page_url,
            "invisible": 1,
            **({"enterprise": 1} if enterprise else {}),
            **({"data-s": data_s} if data_s else {}),
        }
        if user_agent:
            kwargs["userAgent"] = user_agent
        kwargs.update(extra)
        return self.solve("userrecaptcha", **kwargs)

    def solve_hcaptcha(self, page_url: str, sitekey: str,
                       user_agent: Optional[str] = None,
                       **extra) -> Optional[str]:
        kwargs = {"sitekey": sitekey, "pageurl": page_url}
        if user_agent:
            kwargs["userAgent"] = user_agent
        kwargs.update(extra)
        return self.solve("hcaptcha", **kwargs)


# --------- Funciones utilitarias para Selenium ---------
def detect_captcha_type_and_params(driver) -> Dict[str, Any]:
    """
    Intenta detectar reCAPTCHA v2/invisible/enterprise u hCaptcha en el DOM actual.
    Devuelve dict con: {type: 'recaptcha'|'hcaptcha'|None, sitekey, data_s, enterprise: bool}
    """
    js = r"""
    (function(){
      const out = {type:null, sitekey:null, data_s:null, enterprise:false};
      // reCAPTCHA v2 clásico/invisible
      let el = document.querySelector('[data-sitekey]');
      if (el && (el.className||'').toLowerCase().includes('g-recaptcha')) {
        out.type='recaptcha'; out.sitekey=el.getAttribute('data-sitekey')||null;
        out.data_s = el.getAttribute('data-s')||null;
        return out;
      }
      // hCaptcha
      let hc = document.querySelector('[data-hcaptcha-sitekey], [data-sitekey].h-captcha, .h-captcha[data-sitekey]');
      if (hc) {
        out.type='hcaptcha'; out.sitekey = hc.getAttribute('data-hcaptcha-sitekey') || hc.getAttribute('data-sitekey');
        return out;
      }
      // Heurística enterprise
      try {
        if (window.grecaptcha && window.grecaptcha.enterprise) {
          out.type='recaptcha'; out.enterprise=true;
        } else if (window.grecaptcha) {
          out.type='recaptcha';
        }
      } catch(e){}
      // Busca iframes de recaptcha
      const iframes = Array.from(document.querySelectorAll('iframe[src*="recaptcha"]'));
      if (out.type==='recaptcha' || iframes.length){
        for (const f of iframes){
          const u = new URL(f.src, location.href);
          const k = u.searchParams.get('k') || u.searchParams.get('render');
          if (k){ out.sitekey = out.sitekey || k; }
        }
        return out;
      }
      // Busca iframes de hcaptcha
      const ifrH = Array.from(document.querySelectorAll('iframe[src*="hcaptcha.com"]'));
      if (ifrH.length){
        out.type='hcaptcha';
        for (const f of ifrH){
          const u = new URL(f.src, location.href);
          const k = u.searchParams.get('sitekey');
          if (k){ out.sitekey = out.sitekey || k; }
        }
        return out;
      }
      return out;
    })();
    """
    return driver.execute_script(js)

def inject_recaptcha_token_and_submit(driver, token: str):
    """
    Inyecta token en reCAPTCHA v2 (invisible/normal) e intenta submit.
    """
    driver.execute_script("""
      (function(tok){
        let ta = document.getElementById('g-recaptcha-response');
        if (!ta){
          ta = document.createElement('textarea');
          ta.id = 'g-recaptcha-response';
          ta.name = 'g-recaptcha-response';
          ta.style.display='block';
          ta.style.width='1px'; ta.style.height='1px'; ta.style.opacity='0.01';
          document.body.appendChild(ta);
        }
        ta.value = tok;

        const all = document.querySelectorAll('textarea[name="g-recaptcha-response"]');
        all.forEach(e => e.value = tok);

        // Disparar eventos para frameworks
        try { ta.dispatchEvent(new Event('input', {bubbles:true})); } catch(e){}
        try { ta.dispatchEvent(new Event('change', {bubbles:true})); } catch(e){}

        // Intentar submit
        const form = ta.form || document.querySelector('form[method][action], form');
        if (form) {
          form.submit();
        } else {
          document.dispatchEvent(new Event('captcha-solved', {bubbles:true}));
        }
      })(arguments[0]);
    """, token)

def inject_hcaptcha_token_and_submit(driver, token: str):
    driver.execute_script("""
      (function(tok){
        let ta = document.querySelector('textarea[name="h-captcha-response"]');
        if (!ta){
          ta = document.createElement('textarea');
          ta.name = 'h-captcha-response';
          ta.style.display='block'; ta.style.width='1px'; ta.style.height='1px'; ta.style.opacity='0.01';
          document.body.appendChild(ta);
        }
        ta.value = tok;
        try { ta.dispatchEvent(new Event('input', {bubbles:true})); } catch(e){}
        try { ta.dispatchEvent(new Event('change', {bubbles:true})); } catch(e){}

        const form = ta.form || document.querySelector('form[method][action], form');
        if (form) form.submit();
      })(arguments[0]);
    """, token)

def solve_current_captcha_with_2captcha(driver, solver: TwoCaptchaSolver,
                                        enterprise_hint: bool = False,
                                        user_agent: Optional[str] = None) -> bool:
    """
    Detección -> Solución -> Inyección -> Submit
    Devuelve True si inyectó token y disparó el submit.
    """
    params = detect_captcha_type_and_params(driver)
    ctype = params.get("type")
    sitekey = params.get("sitekey")
    data_s = params.get("data_s")
    enterprise = params.get("enterprise") or enterprise_hint
    page_url = driver.current_url

    if not ctype or not sitekey:
        print("⚠️ No se detectó reCAPTCHA/hCaptcha o falta sitekey.")
        return False

    if ctype == "recaptcha":
        token = solver.solve_recaptcha_v2_invisible(
            page_url=page_url,
            sitekey=sitekey,
            data_s=data_s,
            enterprise=enterprise,
            user_agent=user_agent
        )
        if not token: return False
        inject_recaptcha_token_and_submit(driver, token)
        return True

    if ctype == "hcaptcha":
        token = solver.solve_hcaptcha(
            page_url=page_url,
            sitekey=sitekey,
            user_agent=user_agent
        )
        if not token: return False
        inject_hcaptcha_token_and_submit(driver, token)
        return True

    return False


# =========================
# NUEVOS helpers movidos aquí
# =========================
def _extract_sitekey_from_bframe_src(src: str) -> Optional[str]:
    """Extrae el sitekey (param 'k') desde la URL del iframe bframe de reCAPTCHA."""
    if not src:
        return None
    try:
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(src).query)
        return q.get("k", [None])[0]
    except Exception:
        return None

def inject_recaptcha_token_no_submit(driver, token: str) -> None:
    """
    Inyecta token en g-recaptcha-response e intenta disparar callbacks sin hacer submit.
    Útil cuando el submit lo realiza la app tras validar el token.
    """
    driver.execute_script("""
      (function(tok){
        var ta = document.getElementById('g-recaptcha-response');
        if(!ta){
          ta = document.createElement('textarea');
          ta.id = 'g-recaptcha-response';
          ta.name = 'g-recaptcha-response';
          ta.style.display='block';
          ta.style.width='1px';
          ta.style.height='1px';
          ta.style.opacity='0.01';
          ta.style.position='absolute';
          ta.style.left='-9999px';
          document.body.appendChild(ta);
        }
        ta.value = tok;
        var all = document.querySelectorAll('textarea[name="g-recaptcha-response"]');
        all.forEach(function(e){ e.value = tok; });

        ['input','change'].forEach(function(ev){
          try { ta.dispatchEvent(new Event(ev, {bubbles:true})); } catch(_){}
        });

        function safeInvoke(cb){ try { cb(tok); } catch(e){} }
        var invoked = false;
        try {
          if (window.grecaptcha && window.grecaptcha.enterprise && typeof window.grecaptcha.enterprise.getResponse === 'function') {
            var cfg = window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients || {};
            for (var i in cfg){ var ci = cfg[i];
              for (var j in ci){ var cj = ci[j];
                for (var k in cj){ var ck = cj[k];
                  if (ck && typeof ck.callback === 'function') { safeInvoke(ck.callback); invoked = true; }
                  if (ck && ck.sitekey) { if (ck.b && typeof ck.b.callback === 'function') { safeInvoke(ck.b.callback); invoked = true; } }
        }}}}
          else if (window.grecaptcha) {
            var cfg2 = window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients || {};
            for (var i2 in cfg2){ var c2 = cfg2[i2];
              for (var j2 in c2){ var cj2 = c2[j2];
                for (var k2 in cj2){ var ck2 = cj2[k2];
                  if (ck2 && typeof ck2.callback === 'function') { safeInvoke(ck2.callback); invoked = true; }
                  if (ck2 && ck2.b && typeof ck2.b.callback === 'function') { safeInvoke(ck2.b.callback); invoked = true; }
        }}}}
        } catch(e){}
        if (!invoked) {
          try { document.dispatchEvent(new CustomEvent('recaptcha-token-injected', {detail:{token: tok}})); } catch(_){}
        }
      })(arguments[0]);
    """, token)

def solve_recaptcha_in_iframes(driver,
                               wait: "WebDriverWait",
                               user_agent: Optional[str] = None,
                               max_attempts: int = 2,
                               submit: bool = False) -> bool:
    """
    Detecta iframes de reCAPTCHA (api2/bframe), extrae sitekey, pide token a 2Captcha e inyecta.
    Si submit=True, usa inject_recaptcha_token_and_submit; de lo contrario, inject_recaptcha_token_no_submit.
    No lanza; devuelve True si se inyectó correctamente.
    """
    try:
        time.sleep(2)
        iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='api2/bframe' i], iframe[src*='recaptcha' i]")
        print(f"   -> Detección de iframes reCAPTCHA: encontrados {len(iframes)}")
        if not iframes:
            print("   -> No se detectó iframe de reCAPTCHA; no se resuelve.")
            return False

        sitekey = None
        for ifr in iframes:
            src = ifr.get_attribute("src") or ""
            k = _extract_sitekey_from_bframe_src(src)
            if k:
                sitekey = k
                break

        if not sitekey:
            print("   -> ⚠️ No se pudo extraer sitekey (param k) de los iframes.")
            return False

        print(f"   -> 🎯 Sitekey detectado: {sitekey}")
        solver = TwoCaptchaSolver()
        for attempt in range(1, max_attempts + 1):
            print(f"      -> Solicitando token a 2Captcha (intento {attempt}/{max_attempts})...")
            token = solver.solve(
                method="userrecaptcha",
                googlekey=sitekey,
                pageurl=driver.current_url,
                invisible=1,
                **({"userAgent": user_agent} if user_agent else {})
            )
            if token:
                print("      -> ✅ Token recibido. Inyectando en la página...")
                if submit:
                    inject_recaptcha_token_and_submit(driver, token)
                else:
                    inject_recaptcha_token_no_submit(driver, token)
                try:
                    WebDriverWait(driver, 10).until_not(
                        lambda d: d.find_elements(By.CSS_SELECTOR, "iframe[src*='api2/bframe' i], .sso-recaptcha-popup, .sso-recaptcha-wrapper")
                    )
                except TimeoutException:
                    pass # El timeout aquí es esperado si la página simplemente no actualiza el DOM
                return True
            print("      -> ❌ 2Captcha no devolvió token en este intento.")
            time.sleep(3)

        print("   -> 🚨 No se pudo resolver el reCAPTCHA tras los reintentos.")
        return False
    except Exception as e:
        print(f"   -> ❌ Error general al resolver el reCAPTCHA: {e}")
        return False

def detect_github_captcha_params(driver) -> Optional[Dict[str, Any]]:
    """
    Detecta el iframe del captcha personalizado de GitHub ("Octocaptcha") y extrae
    todos los parámetros relevantes para su resolución.
    """
    from selenium.common.exceptions import NoSuchElementException
    from urllib.parse import urlparse, parse_qs

    print("   -> 🕵️  Buscando el iframe del CAPTCHA personalizado de GitHub ('Octocaptcha')...")
    try:
        # 1. Encontrar el iframe del captcha
        iframe = driver.find_element(By.CSS_SELECTOR, "iframe.js-octocaptcha-frame")
        
        params = {"type": "GitHub Octocaptcha"}

        # 2. Extraer la URL de origen del captcha y sus parámetros
        src = iframe.get_attribute("data-src") or iframe.get_attribute("src")
        if src:
            params["iframe_src"] = src
            # Parsear la URL para obtener los query params
            parsed_url = urlparse(src)
            query_params = parse_qs(parsed_url.query)
            # Aplanar los valores de la lista si solo hay uno
            for key, value in query_params.items():
                if len(value) == 1:
                    params[f"param_{key}"] = value[0]
                else:
                    params[f"param_{key}"] = value
        
        # 3. Extraer el host del captcha desde el input del token
        try:
            token_input = driver.find_element(By.CSS_SELECTOR, "input.js-octocaptcha-token")
            params["data_octocaptcha_url"] = token_input.get_attribute("data-octocaptcha-url")
        except NoSuchElementException:
            pass # Es opcional

        # 4. Extraer el timestamp y el secret
        try:
            timestamp_input = driver.find_element(By.NAME, "timestamp")
            params["timestamp"] = timestamp_input.get_attribute("value")
            
            secret_input = driver.find_element(By.NAME, "timestamp_secret")
            params["timestamp_secret"] = secret_input.get_attribute("value")
        except NoSuchElementException:
            pass # Son opcionales pero útiles

        return params

    except NoSuchElementException:
        print("   -> ❌ No se encontró el iframe de Octocaptcha en la página.")
        return None
    except Exception as e:
        print(f"   -> 🚨 Ocurrió un error inesperado al extraer los datos del captcha: {e}")
        return None