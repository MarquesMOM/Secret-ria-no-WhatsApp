"""O cérebro da secretária: Claude com ferramentas do Google Agenda."""
import json
import logging
from collections import deque
from datetime import datetime

import anthropic

from . import calendar_client as cal
from . import config

log = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Histórico curto em memória (some quando o servidor reinicia, o que é aceitável aqui)
MAX_TURNS = 20
_history: deque = deque(maxlen=MAX_TURNS * 2)

SYSTEM_PROMPT = """Você é a secretária pessoal do Matheus e conversa com ele pelo WhatsApp.
Responda sempre em português do Brasil, de forma curta, simpática e direta, como numa conversa de WhatsApp.
Você gerencia o Google Agenda dele com as ferramentas disponíveis.

Regras:
- Agora é {agora} (fuso {fuso}). Resolva datas relativas ("amanhã", "sexta", "semana que vem") a partir disso.
- Para consultar a agenda, use listar_eventos. Nunca invente compromissos.
- Para criar, remarcar ou cancelar, se faltar uma informação essencial (dia ou horário), pergunte antes.
- Antes de cancelar, confirme qual evento é, caso haja mais de um parecido.
- Se a duração não for informada, use 1 hora.
- Formate horários como "14h" ou "14h30" e datas como "sex, 24/10".
- Use no máximo um emoji por mensagem, e só quando ajudar.
"""

TOOLS = [
    {
        "name": "listar_eventos",
        "description": "Lista os compromissos do Google Agenda entre duas datas/horas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "inicio": {"type": "string", "description": "Data/hora ISO 8601 de início, ex.: 2026-10-23T00:00:00"},
                "fim": {"type": "string", "description": "Data/hora ISO 8601 de fim, ex.: 2026-10-23T23:59:59"},
                "busca": {"type": "string", "description": "Texto opcional para filtrar pelo título ou descrição"},
            },
            "required": ["inicio", "fim"],
        },
    },
    {
        "name": "criar_evento",
        "description": "Cria um compromisso no Google Agenda.",
        "input_schema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "inicio": {"type": "string", "description": "ISO 8601, ex.: 2026-10-24T15:00:00 (ou só a data para dia inteiro)"},
                "fim": {"type": "string", "description": "ISO 8601 opcional; padrão é 1 hora após o início"},
                "local": {"type": "string"},
                "descricao": {"type": "string"},
                "dia_inteiro": {"type": "boolean"},
            },
            "required": ["titulo", "inicio"],
        },
    },
    {
        "name": "atualizar_evento",
        "description": "Altera ou remarca um compromisso existente. Use o id obtido em listar_eventos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "titulo": {"type": "string"},
                "inicio": {"type": "string"},
                "fim": {"type": "string"},
                "local": {"type": "string"},
                "descricao": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "cancelar_evento",
        "description": "Apaga um compromisso. Use o id obtido em listar_eventos.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
]


def _run_tool(name: str, args: dict):
    if name == "listar_eventos":
        return cal.list_events(args["inicio"], args["fim"], args.get("busca"))
    if name == "criar_evento":
        return cal.create_event(
            args["titulo"], args["inicio"], args.get("fim"),
            args.get("local"), args.get("descricao"), args.get("dia_inteiro", False),
        )
    if name == "atualizar_evento":
        return cal.update_event(
            args["id"], args.get("titulo"), args.get("inicio"), args.get("fim"),
            args.get("local"), args.get("descricao"),
        )
    if name == "cancelar_evento":
        return cal.delete_event(args["id"])
    raise ValueError(f"Ferramenta desconhecida: {name}")


DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def _system() -> str:
    now = datetime.now(config.TZ)
    agora = f"{DIAS[now.weekday()]}, {now:%d/%m/%Y %H:%M}"
    return SYSTEM_PROMPT.format(agora=agora, fuso=config.TIMEZONE)


def reply(user_text: str) -> str:
    """Recebe a mensagem do usuário e devolve a resposta da secretária."""
    messages = list(_history) + [{"role": "user", "content": user_text}]

    for _ in range(8):  # limite de rodadas de ferramentas
        resp = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            system=_system(),
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            break

        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            try:
                output = _run_tool(block.name, block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(output, ensure_ascii=False)})
            except Exception as exc:  # devolve o erro para o Claude explicar ao usuário
                log.exception("Falha na ferramenta %s", block.name)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": f"Erro: {exc}", "is_error": True})
        messages.append({"role": "user", "content": results})

    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    text = text or "Desculpe, não consegui concluir isso agora. Pode tentar de novo?"

    # Guarda só o texto da conversa, sem o vai e vem das ferramentas
    _history.append({"role": "user", "content": user_text})
    _history.append({"role": "assistant", "content": text})
    return text


def daily_summary() -> str:
    """Gera o resumo da agenda do dia."""
    hoje = datetime.now(config.TZ).date().isoformat()
    events = cal.list_events(f"{hoje}T00:00:00", f"{hoje}T23:59:59")
    if not events:
        return "Bom dia! ☀️ Sua agenda de hoje está livre."
    resp = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=600,
        system=_system(),
        messages=[{
            "role": "user",
            "content": "Escreva um resumo curto de bom dia com a minha agenda de hoje, "
                       "em lista, por ordem de horário:\n" + json.dumps(events, ensure_ascii=False),
        }],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()
