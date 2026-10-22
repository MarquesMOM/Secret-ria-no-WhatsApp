"""Envio de mensagens pela WhatsApp Cloud API."""
import hashlib
import hmac
import logging

import httpx

from . import config

log = logging.getLogger(__name__)

# Erro da Meta quando a janela de 24h de atendimento já fechou
OUTSIDE_WINDOW_ERROR = 131047


def _url() -> str:
    return f"https://graph.facebook.com/{config.WHATSAPP_API_VERSION}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"


def _post(payload: dict) -> dict:
    resp = httpx.post(
        _url(),
        json={"messaging_product": "whatsapp", **payload},
        headers={"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"},
        timeout=20,
    )
    data = resp.json()
    if resp.status_code >= 400:
        log.error("Erro do WhatsApp: %s", data)
    return data


def send_text(to: str, text: str) -> dict:
    return _post({"to": to, "type": "text", "text": {"body": text[:4096]}})


def send_template(to: str, params: list[str]) -> dict:
    return _post({
        "to": to,
        "type": "template",
        "template": {
            "name": config.REMINDER_TEMPLATE,
            "language": {"code": config.REMINDER_TEMPLATE_LANG},
            "components": [{
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in params],
            }],
        },
    })


def send_proactive(to: str, text: str, template_params: list[str]) -> dict:
    """Tenta texto livre; se a janela de 24h fechou, usa o template aprovado."""
    data = send_text(to, text)
    if data.get("error", {}).get("code") == OUTSIDE_WINDOW_ERROR:
        return send_template(to, template_params)
    return data


def mark_read(message_id: str) -> None:
    _post({"status": "read", "message_id": message_id})


def valid_signature(body: bytes, signature_header: str | None) -> bool:
    if not config.WHATSAPP_APP_SECRET:
        return True  # validação desligada se o segredo não foi configurado
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(config.WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))
