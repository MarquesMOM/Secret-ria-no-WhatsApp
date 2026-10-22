import os
from datetime import datetime, timedelta
from types import SimpleNamespace

for k in ["WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "GOOGLE_CLIENT_ID",
          "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "ANTHROPIC_API_KEY"]:
    os.environ.setdefault(k, "x")
os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", "verif")
os.environ.setdefault("OWNER_PHONE", "5511999999999")
os.environ.setdefault("TASKS_SECRET", "segredo")

from fastapi.testclient import TestClient  # noqa: E402

from app import agent, config, main, whatsapp  # noqa: E402

client = TestClient(main.app)


def test_verificacao_webhook():
    r = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verif", "hub.challenge": "42"})
    assert r.status_code == 200 and r.text == "42"
    r = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "errado", "hub.challenge": "42"})
    assert r.status_code == 403


def _payload(sender, mid="m1", text="oi"):
    return {"entry": [{"changes": [{"value": {"messages": [
        {"from": sender, "id": mid, "type": "text", "text": {"body": text}}]}}]}]}


def test_so_responde_ao_dono(monkeypatch):
    handled = []
    monkeypatch.setattr(main, "_handle", lambda m: handled.append(m["id"]))
    client.post("/webhook", json=_payload("5500000000000", "a"))
    client.post("/webhook", json=_payload(config.OWNER_PHONE, "b"))
    client.post("/webhook", json=_payload(config.OWNER_PHONE, "b"))  # reenvio da Meta
    assert handled == ["b"]


def test_lembretes_janela(monkeypatch):
    now = datetime.now(config.TZ).replace(second=0, microsecond=0)
    dentro = now + timedelta(minutes=config.REMINDER_MINUTES_BEFORE + 2)
    antes = now + timedelta(minutes=config.REMINDER_MINUTES_BEFORE - 10)
    events = [
        {"titulo": "Dentista", "inicio": dentro.isoformat(), "dia_inteiro": False, "local": "Centro"},
        {"titulo": "Já começou", "inicio": antes.isoformat(), "dia_inteiro": False, "local": None},
        {"titulo": "Feriado", "inicio": now.date().isoformat(), "dia_inteiro": True, "local": None},
    ]
    monkeypatch.setattr(main.cal, "list_events", lambda s, e: events)
    sent = []
    monkeypatch.setattr(whatsapp, "send_proactive", lambda to, text, params: sent.append(text))
    assert client.post("/tasks/reminders").status_code == 403
    r = client.post("/tasks/reminders", headers={"x-tasks-secret": "segredo"})
    assert r.json() == {"enviados": 1}
    assert "Dentista" in sent[0] and "Centro" in sent[0]


def test_janela_24h_usa_template(monkeypatch):
    calls = []
    monkeypatch.setattr(whatsapp, "send_text", lambda to, t: calls.append("text") or {"error": {"code": 131047}})
    monkeypatch.setattr(whatsapp, "send_template", lambda to, p: calls.append("template") or {})
    whatsapp.send_proactive("1", "oi", ["a", "b"])
    assert calls == ["text", "template"]


def test_agente_usa_ferramenta(monkeypatch):
    replies = [
        SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(
            type="tool_use", id="t1", name="criar_evento",
            input={"titulo": "Dentista", "inicio": "2026-10-24T15:00:00"})]),
        SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Marcado! sex, 24/10 às 15h.")]),
    ]
    monkeypatch.setattr(agent.client.messages, "create", lambda **kw: replies.pop(0))
    created = []
    monkeypatch.setattr(agent.cal, "create_event", lambda *a: created.append(a) or {"id": "e1"})
    assert agent.reply("marca dentista sexta 15h") == "Marcado! sex, 24/10 às 15h."
    assert created[0][:2] == ("Dentista", "2026-10-24T15:00:00")
