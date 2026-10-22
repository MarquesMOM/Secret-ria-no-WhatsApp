import os
from zoneinfo import ZoneInfo


def _req(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


# WhatsApp Cloud API (Meta)
WHATSAPP_TOKEN = _req("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = _req("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = _req("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "")
WHATSAPP_API_VERSION = os.environ.get("WHATSAPP_API_VERSION", "v21.0")
REMINDER_TEMPLATE = os.environ.get("REMINDER_TEMPLATE", "aviso_secretaria")
REMINDER_TEMPLATE_LANG = os.environ.get("REMINDER_TEMPLATE_LANG", "pt_BR")

# Só este número conversa com a secretária (formato internacional, só dígitos: 5511999999999)
OWNER_PHONE = _req("OWNER_PHONE")

# Google Agenda
GOOGLE_CLIENT_ID = _req("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = _req("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = _req("GOOGLE_REFRESH_TOKEN")
CALENDAR_ID = os.environ.get("CALENDAR_ID", "primary")

# Claude
ANTHROPIC_API_KEY = _req("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")

# Geral
TIMEZONE = os.environ.get("TIMEZONE", "America/Sao_Paulo")
TZ = ZoneInfo(TIMEZONE)
REMINDER_MINUTES_BEFORE = int(os.environ.get("REMINDER_MINUTES_BEFORE", "30"))
REMINDER_WINDOW_MINUTES = int(os.environ.get("REMINDER_WINDOW_MINUTES", "5"))
# Protege os endpoints /tasks/* chamados pelo agendador
TASKS_SECRET = _req("TASKS_SECRET")
