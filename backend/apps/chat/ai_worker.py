"""Cola local y contexto del asistente del chat compartido."""

import asyncio
import json
import logging
import re
import weakref

from channels.db import database_sync_to_async
from django.db.models import Q

from apps.ai_core import llm
from apps.ai_core.updates import resumen, validar_updates
from apps.ai_core.views import _parse_json_safe, serialize_diagram
from .models import ChatMessage, ProjectAISettings, message_data


MENTION = re.compile(r"(?<!\w)@ia\b", re.IGNORECASE)
EXPLICIT_ACTION = re.compile(r"\b(?:agreg\w*|cambi\w*|elimin\w*|renombr\w*|añad\w*|borr\w*|modific\w*)\b", re.IGNORECASE)
ROOM_DIAGRAMS = {}
_STATES = weakref.WeakKeyDictionary()
logger = logging.getLogger(__name__)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "updates": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": [
                    "add_class", "delete_class", "rename_class", "add_attribute", "delete_attribute",
                    "add_relation", "delete_relation", "update_relation_type", "set_multiplicity",
                ]},
                "name": {"type": "string"}, "new_name": {"type": "string"},
                "class_name": {"type": "string"}, "attr_name": {"type": "string"},
                "data_type": {"type": "string"}, "visibility": {"type": "string"},
                "source_class": {"type": "string"}, "target_class": {"type": "string"},
                "relation_type": {"type": "string"},
                "source_multiplicity": {"type": "string"},
                "target_multiplicity": {"type": "string"},
            },
            "required": ["action"], "additionalProperties": False,
        }},
    },
    "required": ["reply", "updates"], "additionalProperties": False,
}


def has_mention(content):
    return bool(MENTION.search(content or ""))


def without_mention(content):
    return MENTION.sub("", content).strip()


class _QueueState:
    def __init__(self):
        self.waiting = asyncio.Queue(maxsize=5)
        self.pending = set()
        self.worker = None


def enqueue(project_id, user_id, username, role, message_id, channel_layer):
    """Acepta una consulta si hay lugar y el usuario no tiene otra pendiente."""
    loop = asyncio.get_running_loop()
    state = _STATES.setdefault(loop, _QueueState())
    key = (int(project_id), int(user_id))
    if key in state.pending:
        return "Ya tienes una consulta en curso"
    if state.waiting.full():
        return "La IA está ocupada, intenta en un momento"
    state.pending.add(key)
    state.waiting.put_nowait((key, username, role, message_id, channel_layer))
    if state.worker is None or state.worker.done():
        state.worker = asyncio.create_task(_drain(state))
    return None


async def _drain(state):
    while not state.waiting.empty():
        key, username, role, message_id, layer = state.waiting.get_nowait()
        project_id, user_id = key
        room = f"diagram_{project_id}"
        try:
            await layer.group_send(room, {"type": "broadcast_ai_typing", "active": True,
                                          "for_user_id": user_id, "for_username": username})
            await _answer(project_id, user_id, username, role, message_id, layer)
        except Exception as exc:
            # Ninguna excepción del trabajo debe detener el resto de la cola.
            logger.exception("Fallo de IA tipo=%s respuesta_cruda=%r", type(exc).__name__,
                             str(getattr(exc, "raw", ""))[:800])
            await _save_error(project_id, user_id, layer, exc)
        finally:
            await layer.group_send(room, {"type": "broadcast_ai_typing", "active": False,
                                          "for_user_id": user_id, "for_username": username})
            state.pending.discard(key)
            state.waiting.task_done()


@database_sync_to_async
def _context(project_id, user_id, message_id):
    """Lee otra vez los mensajes al empezar el trabajo, no al encolarlo."""
    from apps.projects.models import Project
    project = Project.objects.get(pk=project_id)
    configuration, _ = ProjectAISettings.objects.get_or_create(project=project)
    unwanted = Q(kind="error") | (Q(meta__has_key="error") & Q(meta__error=True)) | (
        Q(is_ai=True) & (Q(content__regex=r"^\s*$") |
                          Q(content__istartswith="No pude procesar la consulta")))
    room = list(ChatMessage.objects.filter(project=project).exclude(unwanted)
                .select_related("author", "reply_to_user").order_by("-id")[:8])
    individual = list(ChatMessage.objects.filter(project=project, id__lt=message_id).exclude(unwanted).filter(
        Q(author_id=user_id, content__icontains="@ia") | Q(is_ai=True, reply_to_user_id=user_id)
    ).select_related("author").order_by("-id")[:16])
    individual = [m for m in individual if m.is_ai or has_mention(m.content)][:8]
    return project.datos_diagrama or {}, configuration.enabled, configuration.mode, configuration.persona, list(reversed(individual)), list(reversed(room))


def _prompt(username, role, request_text, diagram, persona, mode, individual, room):
    persona_text = ("Modera la conversación, resume y ordena decisiones; pide aclaraciones ante desacuerdos."
                    if persona == "moderator" else
                    "Da recomendaciones técnicas de UML y bases de datos, patrones, normalización y nombres.")
    sections = [
        f"Eres Asistente IA del proyecto. {persona_text} Responde en español, máximo 6 líneas. "
        'Devuelve SOLO JSON válido con "reply" y "updates". Las claves y los textos van siempre entre comillas dobles. '
        + ("No propongas cambios al lienzo." if mode == "advisor" else
           'Acciones permitidas: add_class{name}, delete_class{name}, rename_class{name,new_name}, '
           'add_attribute{class_name,attr_name,data_type}, delete_attribute{class_name,attr_name}, '
           'add_relation{source_class,target_class,relation_type}, delete_relation{source_class,target_class}, '
           'update_relation_type{source_class,target_class,relation_type}, '
           'set_multiplicity{source_class,target_class,source_multiplicity,target_multiplicity}. '
           'Preguntas de consejo (qué falta, qué recomiendas): responde SOLO con reply y updates []. '
           'Genera updates SOLO si piden una acción explícita: agrega, cambia, elimina o renombra. '
           'En herencia source_class=hija y target_class=padre. Nunca afirmes que ya se aplicaron.'),
        'Ejemplo sin cambios: {"reply":"Conviene revisar las relaciones.","updates":[]}',
        ('Ejemplo con cambios, si piden agregar Cuenta: {"reply":"Propongo agregar Cuenta.","updates":[{"action":"add_class","name":"Cuenta"}]}'
         if mode == "proposer" else ""),
        f"Te consulta {username} (rol {role}). Responde SOLO a su pedido. Otros usuarios también escriben en la sala: no mezcles sus pedidos con el de {username}.",
        f"Petición actual de {username}: {request_text}",
        "Diagrama actual:\n" + serialize_diagram(diagram),
        "Últimos intercambios individuales:\n" + "\n".join(
            f"{'IA para ' + username if m.is_ai else username}: {m.content[:300]}" for m in individual),
        "Mensajes recientes de la sala:\n" + "\n".join(
            f"{'Asistente IA' if m.is_ai else (m.author.username if m.author else 'Usuario')}: {m.content[:300]}"
            for m in room),
    ]
    result = ""
    for section in sections:
        room_left = 8000 - len(result)
        if room_left <= 0:
            break
        result += section[:room_left] + "\n"
    return result[:8000]


async def _answer(project_id, user_id, username, role, message_id, layer):
    fallback, enabled, mode, persona, individual, room = await _context(project_id, user_id, message_id)
    if not enabled:
        return
    diagram = ROOM_DIAGRAMS.get(f"diagram_{project_id}") or fallback
    current = next((m for m in room if m.id == message_id), None)
    if current is None:
        current = await _message(message_id)
    prompt = _prompt(username, role, without_mention(current.content), diagram, persona, mode, individual, room)
    messages = [{"role": "user", "content": prompt}]
    raw = await asyncio.to_thread(llm.chat, messages, temperature=0, response_schema=RESPONSE_SCHEMA)
    try:
        parsed = _structured(raw)
    except llm.LLMBadOutput:
        logger.exception("Respuesta estructurada inválida tipo=%s respuesta_cruda=%r", "LLMBadOutput", raw[:800])
        correction = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": 'Corrige el JSON anterior. Devuelve SOLO {"reply":"texto","updates":[]} con comillas dobles y sintaxis válida.'},
        ]
        corrected = await asyncio.to_thread(llm.chat, correction, temperature=0, response_schema=RESPONSE_SCHEMA)
        try:
            parsed = _structured(corrected)
        except llm.LLMBadOutput:
            logger.exception("Reintento inválido tipo=%s respuesta_cruda=%r", "LLMBadOutput", corrected[:800])
            reply = _extract_reply(corrected) or _extract_reply(raw)
            if reply:
                message = await _save_ai_message(project_id, user_id, reply, "text", {})
            else:
                message = await _save_ai_message(project_id, user_id,
                    "La IA devolvió una respuesta ilegible; reformula tu petición", "error", {"error": True})
            await layer.group_send(f"diagram_{project_id}", {"type": "broadcast_chat_message", "message": message})
            return
    updates = parsed.get("updates", [])
    if not isinstance(updates, list):
        updates = []
    if mode == "proposer" and not EXPLICIT_ACTION.search(without_mention(current.content)):
        updates = []
    valid, rejected = validar_updates(diagram, updates)
    if mode == "advisor":
        valid = []
        rejected = []
    if valid:
        summary = resumen(valid, rejected)
        content = summary
        meta = {"status": "pending", "requested_by": user_id, "updates": valid,
                "rejected": rejected, "summary": summary}
        kind = "proposal"
    else:
        content = ("En modo asesor no se aplicaron cambios al lienzo." if mode == "advisor" and updates
                   else "No pude proponer cambios: " + "; ".join(item["reason"] for item in rejected)
                   if rejected else str(parsed.get("reply") or "No tengo una respuesta por ahora.")[:1000])
        meta, kind = {}, "text"
    message = await _save_ai_message(project_id, user_id, content, kind, meta)
    await layer.group_send(f"diagram_{project_id}", {"type": "broadcast_chat_message", "message": message})


@database_sync_to_async
def _message(message_id):
    return ChatMessage.objects.get(pk=message_id)


@database_sync_to_async
def _save_ai_message(project_id, user_id, content, kind, meta):
    message = ChatMessage.objects.create(project_id=project_id, author=None, is_ai=True,
                                         reply_to_user_id=user_id, content=content, kind=kind, meta=meta)
    return message_data(message)


async def _save_error(project_id, user_id, layer, exc):
    if isinstance(exc, llm.LLMModelMissing):
        detail = "No está disponible el modelo local configurado. Pide al dueño revisar los modelos."
    elif isinstance(exc, llm.LLMTimeout):
        detail = "El modelo local tardó demasiado. Espera un momento y vuelve a intentarlo."
    elif isinstance(exc, llm.LLMUnavailable):
        detail = "El servidor local de IA no está disponible."
    elif isinstance(exc, llm.LLMBadOutput):
        detail = "La IA devolvió una respuesta ilegible; reformula tu petición"
    else:
        detail = "Ocurrió un error interno al procesar la consulta. Intenta de nuevo."
    message = await _save_ai_message(project_id, user_id, detail, "error", {"error": True})
    await layer.group_send(f"diagram_{project_id}", {"type": "broadcast_chat_message", "message": message})


def _structured(raw):
    parsed = _parse_json_safe(raw)
    if (not isinstance(parsed, dict) or not isinstance(parsed.get("reply"), str)
            or not isinstance(parsed.get("updates"), list)):
        raise llm.LLMBadOutput("La IA devolvió JSON inválido o incompleto.")
    return parsed


def _extract_reply(raw):
    match = re.search(r'"reply"\s*:\s*"((?:\\.|[^"\\])*)"', raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads('"' + match.group(1) + '"').strip()[:1000] or None
    except json.JSONDecodeError:
        return None
