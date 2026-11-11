"""Transiciones atómicas de propuestas del asistente."""

from django.db import transaction
from django.utils import timezone

from .models import ChatMessage, message_data


@transaction.atomic
def decide(project_id, user_id, role, message_id, decision):
    if role not in ("owner", "editor"):
        return None, "Solo lectura"
    if decision not in ("approve", "reject"):
        return None, "Decisión inválida"
    try:
        message = ChatMessage.objects.select_for_update().get(
            pk=message_id, project_id=project_id, kind="proposal")
    except (ChatMessage.DoesNotExist, ValueError, TypeError):
        return None, "La propuesta no existe"
    if message.reply_to_user_id != user_id:
        return None, "Solo quien solicitó la propuesta puede decidir"
    if message.meta.get("status") != "pending":
        return None, "La propuesta ya fue decidida"
    meta = dict(message.meta)
    meta.update(status="approved" if decision == "approve" else "rejected",
                decided_at=timezone.now().isoformat(), decided_by=user_id)
    message.meta = meta
    message.save(update_fields=["meta"])
    return message_data(message), None


@transaction.atomic
def record_result(project_id, user_id, role, message_id, applied, failed):
    if role not in ("owner", "editor"):
        return None, "Solo lectura"
    try:
        message = ChatMessage.objects.select_for_update().get(
            pk=message_id, project_id=project_id, kind="proposal")
    except (ChatMessage.DoesNotExist, ValueError, TypeError):
        return None, "La propuesta no existe"
    if message.reply_to_user_id != user_id or message.meta.get("decided_by") != user_id:
        return None, "Solo quien aprobó la propuesta puede informar el resultado"
    if message.meta.get("status") != "approved":
        return None, "La propuesta ya tiene resultado o no fue aprobada"
    total = len(message.meta.get("updates", []))
    if (not isinstance(applied, int) or isinstance(applied, bool) or applied < 0 or applied > total
            or not isinstance(failed, list) or len(failed) > total):
        return None, "Resultado inválido"
    cleaned = [{"reason": str(item.get("reason", "Error al aplicar"))[:200]}
               for item in failed if isinstance(item, dict)]
    if applied + len(cleaned) != total:
        return None, "El resultado no coincide con las acciones propuestas"
    meta = dict(message.meta)
    meta["result"] = {"applied": applied, "failed": cleaned}
    meta["status"] = "applied" if applied == total else "partial" if applied else "failed"
    message.meta = meta
    message.save(update_fields=["meta"])
    return message_data(message), None
