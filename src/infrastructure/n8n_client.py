import os
import requests

from src.infrastructure.safe_console import safe_console_line

DEFAULT_NOM_WEBHOOK_URL = (
    "http://localhost:5678/webhook/7f1955c0-9016-4cdd-b116-5e7c9476f6d8"
)


class N8NClient:
    def __init__(self):
        self.webhook_url = os.getenv("N8N_WEBHOOK_URL")
        self.nom_webhook_url = os.getenv("N8N_NOM_WEBHOOK_URL", DEFAULT_NOM_WEBHOOK_URL)
        safe_console_line(f"DEBUG: URL n8n chargée depuis le .env -> {self.webhook_url}")
        safe_console_line(f"DEBUG: URL webhook nom -> {self.nom_webhook_url}")

    @staticmethod
    def _parse_response_body(response: requests.Response):
        """JSON si possible, sinon texte brut (évite JSONDecodeError sur réponse Text n8n)."""
        text = (response.text or "").strip()
        if not text:
            return {"status": "ok", "raw": ""}
        try:
            return response.json()
        except ValueError:
            return {"output": text, "raw": text}

    def trigger_webhook(self, url: str, data: dict, timeout: int = 120):
        if not url:
            return {"status": "error", "message": "URL webhook non configurée"}

        try:
            safe_console_line(f"[N8N] POST {url} payload={data}")
            response = requests.post(url, json=data, timeout=timeout)
            response.raise_for_status()
            parsed = self._parse_response_body(response)
            safe_console_line(f"[N8N] Réponse (HTTP {response.status_code}): {parsed}")
            return parsed
        except requests.HTTPError as e:
            safe_console_line(f"[N8N] HTTP error: {e}")
            return {"status": "error", "message": str(e), "http_status": e.response.status_code if e.response else None}
        except Exception as e:
            safe_console_line(f"[N8N] Erreur lors de l'appel n8n: {e}")
            return {"status": "error", "message": str(e)}

    def trigger_workflow(self, data: dict):
        if not self.webhook_url:
            return {"status": "error", "message": "N8N_WEBHOOK_URL non configuré dans le .env"}
        return self.trigger_webhook(self.webhook_url, data)

    def trigger_nom_webhook(self, nom: str):
        """Webhook dédié : envoie un nom et retourne la réponse n8n."""
        payload = {"nom": nom.strip()}
        return self.trigger_webhook(self.nom_webhook_url, payload)