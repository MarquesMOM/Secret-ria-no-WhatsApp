"""Servidor HTTP: webhook do WhatsApp e tarefas agendadas (lembretes e resumo diário)."""
import logging
from datetime import datetime, timedelta

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from . import agent, config, whatsapp
from . import calendar_client as cal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("secretaria")

app = FastAPI(title="Secretária")

# A Meta pode reenviar o mesmo webhook; guardamos os ids recentes para não responder duas vezes
_seen_ids: list[str] = []


@app.get("/")
def health():
    return {"ok": True}


@app.get("/webhook")
def verify(
    mode: str = Query(alias="hub.mode", default=""),
    token: str = Query(alias="hub.verify_token", default=""),
    challenge: str = Query(alias="hub.challenge", default=""),
):
    if mode == "subscribe" and token == config.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403)


@app.post("/webhook")
async def receive(request: Request,
                  x_hub_signature_256: str | None = Header(default=None)):
    body = await request.body()
    if not whatsapp.valid_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401)

    data = await request.json()
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                if msg.get("from") != config.OWNER_PHONE:
                    log.warning("Mensagem ignorada de número não autorizado")
                    continue
                if msg["id"] in _seen_ids:
                    continue
                _seen_ids.append(msg["id"])
                del _seen_ids[:-200]
                # Processa antes de responder: no Cloud Run a CPU é congelada depois da resposta.
                # Se a Meta reenviar por demora, o filtro de ids acima evita resposta duplicada.
                await run_in_threadpool(_handle, msg)
    return {"ok": True}


def _handle(msg: dict) -> None:
    whatsapp.mark_read(msg["id"])
    if msg.get("type") != "text":
        whatsapp.send_text(msg["from"], "Por enquanto eu só entendo mensagens de texto. 🙂")
        return
    try:
        answer = agent.reply(msg["text"]["body"])
    except Exception:
        log.exception("Falha ao responder")
        answer = "Tive um problema para responder agora. Pode tentar de novo em instantes?"
    whatsapp.send_text(msg["from"], answer)


def _check_secret(secret: str | None) -> None:
    if secret != config.TASKS_SECRET:
        raise HTTPException(status_code=403)


@app.post("/tasks/reminders")
def reminders(x_tasks_secret: str | None = Header(default=None)):
    """Chamado a cada REMINDER_WINDOW_MINUTES pelo agendador.

    Avisa dos eventos que começam entre (agora + antecedência) e (agora + antecedência + janela).
    Como as janelas não se sobrepõem, cada evento é lembrado uma vez, sem precisar de banco de dados.
    """
    _check_secret(x_tasks_secret)
    now = datetime.now(config.TZ).replace(second=0, microsecond=0)
    start = now + timedelta(minutes=config.REMINDER_MINUTES_BEFORE)
    end = start + timedelta(minutes=config.REMINDER_WINDOW_MINUTES)
    sent = 0
    for ev in cal.list_events(start.isoformat(), end.isoformat()):
        if ev["dia_inteiro"]:
            continue
        begins = datetime.fromisoformat(ev["inicio"])
        if not (start <= begins < end):
            continue  # evento que já tinha começado antes da janela
        hora = begins.astimezone(config.TZ).strftime("%Hh%M").replace("h00", "h")
        text = f"⏰ Lembrete: *{ev['titulo']}* às {hora}"
        if ev.get("local"):
            text += f" em {ev['local']}"
        whatsapp.send_proactive(config.OWNER_PHONE, text, [ev["titulo"], hora])
        sent += 1
    return {"enviados": sent}


@app.post("/tasks/daily-summary")
def daily_summary(x_tasks_secret: str | None = Header(default=None)):
    _check_secret(x_tasks_secret)
    text = agent.daily_summary()
    hoje = datetime.now(config.TZ).strftime("%d/%m")
    whatsapp.send_proactive(config.OWNER_PHONE, text, ["Resumo da agenda de hoje", hoje])
    return {"ok": True}
