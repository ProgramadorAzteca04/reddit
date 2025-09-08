# app/services/captcha_service.py
import os
import time
import json
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

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
        - googlekey: sitekey del sitio
        - pageurl:   URL actual (aunque no cambie)
        - invisible=1
        - enterprise=1 si aplica
        - data-s: si ves atributo data-s o rqdata en el DOM
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
      // Si el widget se monta vía JS (invisible/enterprise), intenta leer claves globales
      // Heurística para enterprise: grecaptcha.enterprise presente
      try {
        if (window.grecaptcha && window.grecaptcha.enterprise) {
          out.type='recaptcha'; out.enterprise=true;
        } else if (window.grecaptcha) {
          out.type='recaptcha';
        }
      } catch(e){}
      // Busca iframes de recaptcha/hcaptcha
      const iframes = Array.from(document.querySelectorAll('iframe[src*="recaptcha"]'));
      if (out.type==='recaptcha' || iframes.length){
        // A veces el sitekey está como k= en el src del iframe
        for (const f of iframes){
          const u = new URL(f.src, location.href);
          const k = u.searchParams.get('k') || u.searchParams.get('render');
          if (k){ out.sitekey = out.sitekey || k; }
        }
        return out;
      }
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
    Inyecta token en reCAPTCHA v2 (invisible/normal). Intenta disparar callback o submit.
    """
    driver.execute_script("""
      (function(tok){
        // Asegurar el textarea
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

        // Muchas integraciones usan input oculto 'g-recaptcha-response'
        const all = document.querySelectorAll('textarea[name="g-recaptcha-response"]');
        all.forEach(e => e.value = tok);

        // Tratar de ejecutar callback si existe
        if (window.grecaptcha){
          try{
            if (grecaptcha.getResponse && !grecaptcha.getResponse()){
              // No hace falta ejecutar, ya tenemos respuesta
            }
          }catch(e){}
        }
        // Si hay form visible, intenta submit
        const form = ta.form || document.querySelector('form[method][action], form');
        if (form) {
          // Disparar un change/input para que frameworks detecten el valor
          ta.dispatchEvent(new Event('input', {bubbles:true}));
          ta.dispatchEvent(new Event('change', {bubbles:true}));
          form.submit();
        } else {
          // fallback: dispara eventos globales comunes
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
        ta.dispatchEvent(new Event('input', {bubbles:true}));
        ta.dispatchEvent(new Event('change', {bubbles:true}));

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
