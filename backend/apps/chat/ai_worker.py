"""Cola local y contexto del asistente del chat compartido."""

import asyncio
import json
import logging
import re
import weakref
import unicodedata

from channels.db import database_sync_to_async
from django.db.models import Q

from apps.ai_core import llm
from apps.ai_core.updates import _plain, resumen, validar_updates
from apps.ai_core.views import _parse_json_safe, serialize_diagram
from .models import ChatMessage, ProjectAISettings, message_data


MENTION = re.compile(r"(?<!\w)@ia\b", re.IGNORECASE)
ROOM_DIAGRAMS = {}
ACTION_WORDS = re.compile(r"\b(?:agreg\w*|anad\w*|crea\w*|relacion\w*|conect\w*|une\b|unir\b|asoci\w*|vincul\w*|hered\w*|orden\w*|pon\b|ponga\w*|coloc\w*|establec\w*|establez\w*|defin\w*|inclu\w*|cambi\w*|modific\w*|elimin\w*|borr\w*|renombr\w*|haz\b|hace\b|gener\w*|complet\w*|muev\w*|mov\w*)\b")
ADVICE_WORDS = re.compile(r"\b(?:recomend\w*|aconsej\w*|opin\w*|sugier\w*|suger\w*|explic\w*|revis\w*)\b")
QUESTION_START = re.compile(r"^(?:que|cual|como|por\s+que|donde|cuando|quien)\b")
PROMISE = re.compile(r"\b(?:propong\w*|voy\s+a|agreg\w*|anad\w*|cambi\w*|orden\w*|cre\w*|elimin\w*|renombr\w*|relacion\w*|conect\w*|hered\w*|modific\w*|aplic\w*)\b", re.IGNORECASE)
DELETE_ALL = re.compile(
    r"^\s*(?:elimina|borra|quita|remueve)\s+(?:(?:todos|todas)\s+)?(?:los|las)\s+"
    r"(atributos|m[eé]todos|relaciones)\s+de\s+(?:la\s+clase\s+)?(.+?)\s*$", re.IGNORECASE)
EMPTY_CLASS = re.compile(r"^\s*vac[ií]a\s+(?:la\s+clase\s+)?(.+?)\s*$", re.IGNORECASE)
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
                    "update_attribute", "reorder_attributes", "set_abstract", "add_method", "delete_method",
                    "add_relation", "delete_relation", "update_relation_type", "set_multiplicity",
                    "clear_attributes", "clear_methods", "delete_relations_of",
                ]},
                "name": {"type": "string"}, "new_name": {"type": "string"},
                "class_name": {"type": "string"}, "attr_name": {"type": "string"},
                "method_name": {"type": "string"}, "return_type": {"type": "string"},
                "order": {"type": "array", "items": {"type": "string"}},
                "is_abstract": {"type": "boolean"}, "label": {"type": "string"},
                "data_type": {"type": "string"}, "visibility": {"type": "string"},
                "source_class": {"type": "string"}, "target_class": {"type": "string"},
                "relation_type": {"type": "string"},
                "source_multiplicity": {"type": "string"},
                "target_multiplicity": {"type": "string"},
                "attr_names": {"type": "array", "items": {"type": "string"}},
                "attributes": {"type": "array", "items": {"type": "object", "properties": {
                    "name": {"type": "string"}, "data_type": {"type": "string"}},
                    "required": ["name", "data_type"], "additionalProperties": False}},
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


def _solo_consejo(content):
    texto = "".join(c for c in unicodedata.normalize("NFD", content.lower())
                    if unicodedata.category(c) != "Mn").strip().lstrip("¿")
    return not ACTION_WORDS.search(texto) and bool(
        QUESTION_START.search(texto) or ADVICE_WORDS.search(texto) or "?" in texto)


def _atajo_borrado(content):
    """Reconoce únicamente pedidos de vaciado sin atributos concretos nombrados."""
    match = DELETE_ALL.fullmatch(content)
    if match:
        kind = _plain(match.group(1))
        action = {"atributos": "clear_attributes", "metodos": "clear_methods",
                  "relaciones": "delete_relations_of"}[kind]
        name = match.group(2).strip(" .!?")
        return [{"action": action, "class_name": name}] if name else None
    match = EMPTY_CLASS.fullmatch(content)
    if match:
        name = match.group(1).strip(" .!?")
        return ([{"action": "clear_attributes", "class_name": name},
                 {"action": "clear_methods", "class_name": name}] if name else None)
    return None


def _motivo_concreto(diagram, request_text, rejected):
    """Da prioridad a la causa comprobable sobre una aclaración genérica."""
    nodes = diagram.get("nodes", []) if isinstance(diagram, dict) else []
    classes = [node.get("data", {}).get("name", "") for node in nodes]
    available = ", ".join(classes) or "(ninguna)"
    for item in rejected:
        reason = item.get("reason", "")
        if reason.startswith("La clase ") and reason.endswith(" no existe."):
            return f"{reason} Clases del diagrama: {available}."
        if reason.startswith("La clase ") and " no tiene " in reason:
            return reason
    match = re.search(r"\b(?:de|en)\s+(?:la\s+clase\s+)?([^,.;!?]+)\s*$", request_text, re.IGNORECASE)
    if not match:
        return None
    asked = match.group(1).strip()
    node = next((node for node in nodes if _plain(node.get("data", {}).get("name")) == _plain(asked)), None)
    if node is None:
        return f"La clase {asked} no existe. Clases del diagrama: {available}."
    name = node.get("data", {}).get("name", asked)
    text = _plain(request_text)
    if "atribut" in text and not node.get("data", {}).get("attributes"):
        return f"La clase {name} no tiene atributos."
    if "metod" in text and not node.get("data", {}).get("methods"):
        return f"La clase {name} no tiene métodos."
    if "relacion" in text:
        node_id = str(node.get("id"))
        edges = diagram.get("edges", [])
        if not any(node_id in (str(edge.get("source")), str(edge.get("target"))) for edge in edges):
            return f"La clase {name} no tiene relaciones."
    return None


def _public_updates(valid):
    """La tarjeta recibe solo acciones que entiende el lienzo."""
    return [{key: value for key, value in update.items() if not key.startswith("_batch_")}
            for update in valid]


class _QueueState:
    def __init__(self):
        self.waiting = asyncio.Queue(maxsize=5)
        self.pending = set()
        self.worker = None


def enqueue(project_id, user_id, username, role, message_id, channel_layer, diagram=None):
    """Acepta una consulta si hay lugar y el usuario no tiene otra pendiente."""
    loop = asyncio.get_running_loop()
    state = _STATES.setdefault(loop, _QueueState())
    key = (int(project_id), int(user_id))
    if key in state.pending:
        return "Ya tienes una consulta en curso"
    if state.waiting.full():
        return "La IA está ocupada, intenta en un momento"
    state.pending.add(key)
    state.waiting.put_nowait((key, username, role, message_id, channel_layer, diagram))
    if state.worker is None or state.worker.done():
        state.worker = asyncio.create_task(_drain(state))
    return None


async def _drain(state):
    while not state.waiting.empty():
        key, username, role, message_id, layer, diagram = state.waiting.get_nowait()
        project_id, user_id = key
        room = f"diagram_{project_id}"
        try:
            await layer.group_send(room, {"type": "broadcast_ai_typing", "active": True,
                                          "for_user_id": user_id, "for_username": username})
            await _answer(project_id, user_id, username, role, message_id, layer, diagram)
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
    persona_text = ("Modera, resume decisiones y pide aclaraciones ante desacuerdos."
                    if persona == "moderator" else
                    "Da consejos técnicos de UML y BD: patrones, normalización y nombres.")
    reglas = ("No propongas cambios al lienzo." if mode == "advisor" else
        "Acciones cerradas: add_class{name}; delete_class{name}; rename_class{name,new_name}; "
        "set_abstract{name,is_abstract}; add_attribute{class_name,attr_name,data_type?,visibility?}; "
        "delete_attribute{class_name,attr_name}; "
        "update_attribute{class_name,attr_name,new_name?,data_type?,visibility?}; "
        "reorder_attributes{class_name,order:[nombres]}; "
        "add_method{class_name,method_name,return_type?}; delete_method{class_name,method_name}; "
        "clear_attributes{class_name}; clear_methods{class_name}; delete_relations_of{class_name}; "
        "add_relation{source_class,target_class,relation_type,source_multiplicity?,target_multiplicity?,label?}; "
        "delete_relation{source_class,target_class}; "
        "update_relation_type{source_class,target_class,relation_type}; "
        "set_multiplicity{source_class,target_class,source_multiplicity,target_multiplicity}. "
        "Tipos: association=asociación; directed_association=asociación dirigida; "
        "dependency=dependencia; aggregation=agregación; composition=composición; "
        "inheritance=herencia; realization=realización; association_class=clase de asociación. "
        "Usa nombres de clases existentes o creadas antes en updates. "
        "En herencia source_class=hija y target_class=padre. Nunca agregues un atributo que ya existe. "
        "Para eliminar todos los atributos, métodos o relaciones de una clase usa clear_attributes, "
        "clear_methods o delete_relations_of; no elijas solo algunos. "
        "Preguntas de consejo: responde con updates []. Nunca afirmes que se aplicó un cambio.")
    ejemplos = ("Ejemplos de pedido -> salida JSON:\n"
        "¿Qué clases faltan? -> {\"reply\":\"Revisa responsabilidades.\",\"updates\":[]}\n"
        "Relaciona A con B con asociación 1 a * -> {\"reply\":\"Propongo relación.\",\"updates\":[{\"action\":\"add_relation\",\"source_class\":\"A\",\"target_class\":\"B\",\"relation_type\":\"association\",\"source_multiplicity\":\"1\",\"target_multiplicity\":\"*\"}]}\n"
        "X hereda de Y -> {\"reply\":\"Propongo herencia.\",\"updates\":[{\"action\":\"add_relation\",\"source_class\":\"X\",\"target_class\":\"Y\",\"relation_type\":\"inheritance\"}]}\n"
        "Composición A-B -> {\"reply\":\"Propongo composición.\",\"updates\":[{\"action\":\"add_relation\",\"source_class\":\"A\",\"target_class\":\"B\",\"relation_type\":\"composition\"}]}\n"
        "Realización A-B -> {\"reply\":\"Propongo realización.\",\"updates\":[{\"action\":\"add_relation\",\"source_class\":\"A\",\"target_class\":\"B\",\"relation_type\":\"realization\"}]}\n"
        "Agrega edad:int y nombre:String a A -> {\"reply\":\"Propongo atributos.\",\"updates\":[{\"action\":\"add_attribute\",\"class_name\":\"A\",\"attr_name\":\"edad\",\"data_type\":\"int\"},{\"action\":\"add_attribute\",\"class_name\":\"A\",\"attr_name\":\"nombre\",\"data_type\":\"String\"}]}\n"
        "Ordena atributos de A: nombre, edad -> {\"reply\":\"Propongo orden.\",\"updates\":[{\"action\":\"reorder_attributes\",\"class_name\":\"A\",\"order\":[\"nombre\",\"edad\"]}]}\n"
        "Elimina todos los atributos de A -> {\"reply\":\"Propongo vaciar atributos.\",\"updates\":[{\"action\":\"clear_attributes\",\"class_name\":\"A\"}]}") if mode == "proposer" else ""
    sections = [
        f"Eres Asistente IA. {persona_text} Responde en español, máximo 6 líneas. "
        'Devuelve SOLO JSON válido con "reply" y "updates". Claves y textos siempre entre comillas dobles. ' + reglas,
        ejemplos,
        f"Te consulta {username} (rol {role}). Responde SOLO a su pedido. Otros usuarios escriben en la sala: no mezcles sus pedidos con el de {username}.",
        f"Petición actual de {username}: {request_text}",
        "Diagrama actual (incluye atributos existentes):\n" + serialize_diagram(diagram),
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


async def _answer(project_id, user_id, username, role, message_id, layer, diagram=None):
    fallback, enabled, mode, persona, individual, room = await _context(project_id, user_id, message_id)
    if not enabled:
        return
    diagram = diagram or ROOM_DIAGRAMS.get(f"diagram_{project_id}") or fallback
    current = next((m for m in room if m.id == message_id), None)
    if current is None:
        current = await _message(message_id)
    request_text = without_mention(current.content)
    shortcut = _atajo_borrado(request_text)
    if shortcut is not None:
        if mode == "advisor":
            content, kind, meta = "En modo asesor no se aplicaron cambios al lienzo.", "text", {}
        else:
            valid, rejected = validar_updates(diagram, shortcut)
            if valid:
                content = resumen(valid, rejected)
                kind = "proposal"
                meta = {"status": "pending", "requested_by": user_id, "updates": _public_updates(valid),
                        "rejected": rejected, "summary": content}
            else:
                content = _motivo_concreto(diagram, request_text, rejected) or resumen(valid, rejected)
                kind, meta = "text", {}
        message = await _save_ai_message(project_id, user_id, content, kind, meta)
        await layer.group_send(f"diagram_{project_id}", {"type": "broadcast_chat_message", "message": message})
        return
    prompt = _prompt(username, role, request_text, diagram, persona, mode, individual, room)
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
                if (mode == "proposer" and not _solo_consejo(without_mention(current.content))
                        and PROMISE.search(reply)):
                    reply = (_motivo_concreto(diagram, request_text, []) or
                             "No pude convertir tu pedido en un cambio concreto. Indica la clase y la acción, "
                             "por ejemplo: @ia relaciona Medico con Paciente con asociación 1 a *")
                message = await _save_ai_message(project_id, user_id, reply, "text", {})
            else:
                message = await _save_ai_message(project_id, user_id,
                    "La IA devolvió una respuesta ilegible; reformula tu petición", "error", {"error": True})
            await layer.group_send(f"diagram_{project_id}", {"type": "broadcast_chat_message", "message": message})
            return
    updates = parsed.get("updates", [])
    if not isinstance(updates, list):
        updates = []
    if mode == "proposer" and _solo_consejo(without_mention(current.content)):
        updates = []
    valid, rejected = validar_updates(diagram, updates)
    if mode == "proposer" and not valid and not _solo_consejo(without_mention(current.content)):
        # Un texto que promete cambios sin acciones no debe publicarse como éxito.
        if PROMISE.search(parsed.get("reply", "")):
            retry = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Debes devolver al menos una acción en updates. Responde SOLO JSON válido."},
            ]
            corrected = await asyncio.to_thread(llm.chat, retry, temperature=0,
                                                response_schema=RESPONSE_SCHEMA)
            try:
                parsed_retry = _structured(corrected)
                valid_retry, rejected_retry = validar_updates(diagram, parsed_retry["updates"])
                if valid_retry:
                    valid, rejected = valid_retry, rejected_retry
                else:
                    rejected = rejected_retry or rejected
            except llm.LLMBadOutput:
                logger.exception("Reintento sin acciones tipo=LLMBadOutput respuesta_cruda=%r", corrected[:800])
            if not valid:
                parsed["reply"] = (_motivo_concreto(diagram, request_text, rejected) or
                                   "No pude convertir tu pedido en un cambio concreto. Indica la clase y la acción, "
                                   "por ejemplo: @ia relaciona Medico con Paciente con asociación 1 a *")
                rejected = []
    if mode == "advisor":
        valid = []
        rejected = []
    if valid:
        summary = resumen(valid, rejected)
        content = summary
        meta = {"status": "pending", "requested_by": user_id, "updates": _public_updates(valid),
                "rejected": rejected, "summary": summary}
        kind = "proposal"
    else:
        specific = _motivo_concreto(diagram, request_text, rejected) if mode == "proposer" else None
        content = ("En modo asesor no se aplicaron cambios al lienzo." if mode == "advisor" and updates
                   else specific if specific
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
