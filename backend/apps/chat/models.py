from django.db import models
from django.conf import settings
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.db import transaction
from apps.projects.models import Project


class ChatMessage(models.Model):
    """Mensaje persistente de un proyecto; los campos de IA quedan reservados."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="chat_messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    is_ai = models.BooleanField(default=False)
    reply_to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                      null=True, related_name="+")
    content = models.TextField()
    kind = models.CharField(max_length=30, default="text")
    meta = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_mensaje"
        indexes = [models.Index(fields=["project", "id"], name="chat_project_id_idx")]


def message_data(message):
    """Formato compartido por REST y WebSocket."""
    meta = dict(message.meta or {})
    if message.kind == "image":
        meta.pop("image_path", None)
        meta.pop("thumbnail_path", None)
        meta.pop("analysis", None)
        base = f"projects/{message.project_id}/chat/{message.id}/image/"
        meta["image_url"] = base
        meta["thumbnail_url"] = f"{base}?size=thumb"
        meta["analyzed"] = bool(message.meta.get("analysis"))
    return {
        "id": message.id,
        "author_id": message.author_id,
        "username": message.author.username if message.author else None,
        "is_ai": message.is_ai,
        "reply_to_user_id": message.reply_to_user_id,
        "reply_to_username": message.reply_to_user.username if message.reply_to_user else None,
        "content": message.content,
        "kind": message.kind,
        "meta": meta,
        "created_at": message.created_at.isoformat(),
    }


class ProjectAISettings(models.Model):
    """Preferencias de la IA de una sala, creadas al primer acceso."""
    class Mode(models.TextChoices):
        ADVISOR = "advisor", "Consejero"
        PROPOSER = "proposer", "Proponente"

    class Persona(models.TextChoices):
        MODERATOR = "moderator", "Moderador"
        SENIOR_DEV = "senior_dev", "Desarrollador senior"

    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="ai_settings")
    enabled = models.BooleanField(default=True)
    mode = models.CharField(max_length=12, choices=Mode.choices, default=Mode.ADVISOR)
    persona = models.CharField(max_length=12, choices=Persona.choices, default=Persona.SENIOR_DEV)

    class Meta:
        db_table = "chat_config_ia"


def settings_data(configuration):
    return {"enabled": configuration.enabled, "mode": configuration.mode, "persona": configuration.persona}


@receiver(post_delete, sender=ChatMessage)
def delete_chat_image(sender, instance, **kwargs):
    """Limpia las imágenes privadas al borrar un mensaje o su proyecto."""
    if instance.kind == "image":
        from .images import delete_image
        meta = dict(instance.meta or {})
        transaction.on_commit(lambda: delete_image(meta))
