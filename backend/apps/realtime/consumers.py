"""
DiagramConsumer — WebSocket consumer para colaboración en tiempo real.

Protocolo de mensajes (JSON):
  type: "diagram_update"   → nodos y edges completos del diagrama
  type: "cursor_move"      → posición del cursor de un colaborador
  type: "user_join"        → un usuario se unió al diagrama
  type: "user_leave"       → un usuario salió del diagrama
  type: "ping"             → keepalive desde el cliente

Autenticación: se espera el JWT en el query-string ?token=<JWT>
"""

import json
import logging
from apps.chat.ai_worker import ROOM_DIAGRAMS, enqueue, has_mention
from apps.chat.decisions import decide, record_result

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class DiagramConsumer(AsyncWebsocketConsumer):
    """Gestiona la sesión WebSocket de un usuario en un diagrama compartido."""

    # ─── Ciclo de vida ──────────────────────────────────────────────────────────

    async def connect(self):
        self.diagram_id = self.scope["url_route"]["kwargs"]["diagram_id"]
        self.room_group = f"diagram_{self.diagram_id}"

        # Verificar autenticación (el middleware JWT lo resuelve)
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser):
            # Intentar autenticar desde query string
            user = await self._authenticate_from_token()
            if not user:
                await self.close(code=4001)
                return
            self.scope["user"] = user

        # Verificar que el usuario tiene acceso al proyecto
        self.project_role = await self._get_project_role(user, self.diagram_id)
        if not self.project_role:
            await self.close(code=4003)
            return

        self.user = user
        self.username = user.username

        # Unirse al grupo de sala
        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()

        # Notificar a los demás que un usuario se unió
        await self.channel_layer.group_send(
            self.room_group,
            {
                "type": "broadcast_user_join",
                "username": self.username,
                "user_id": user.id,
            },
        )
        logger.info("WS connect: user=%s diagram=%s", self.username, self.diagram_id)

    async def disconnect(self, close_code):
        username = getattr(self, "username", "unknown")

        # Notificar a los demás que el usuario salió
        await self.channel_layer.group_send(
            self.room_group,
            {
                "type": "broadcast_user_leave",
                "username": username,
                "user_id": getattr(getattr(self, "user", None), "id", None),
            },
        )

        await self.channel_layer.group_discard(self.room_group, self.channel_name)
        logger.info("WS disconnect: user=%s diagram=%s code=%s", username, self.diagram_id, close_code)

    async def receive(self, text_data):
        """Recibe mensajes del cliente y los re-difunde al grupo."""
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type")

        if msg_type == "chat_message":
            if self.project_role not in ("owner", "editor"):
                await self.send(text_data=json.dumps({"type": "chat_error", "detail": "Solo lectura"}))
                return
            content = data.get("content")
            content = content.strip() if isinstance(content, str) else ""
            if not 1 <= len(content) <= 2000:
                await self.send(text_data=json.dumps({"type": "chat_error", "detail": "El mensaje debe tener entre 1 y 2000 caracteres."}))
                return
            message = await self._save_chat_message(content)
            await self.channel_layer.group_send(self.room_group, {
                "type": "broadcast_chat_message", "message": message,
            })
            if has_mention(content) and await self._ai_is_enabled():
                diagram = data.get("diagram")
                if (not isinstance(diagram, dict) or
                        not isinstance(diagram.get("nodes"), list) or
                        not isinstance(diagram.get("edges"), list) or
                        len(json.dumps(diagram, ensure_ascii=False).encode("utf-8")) > 1024 * 1024):
                    diagram = None
                if diagram is not None:
                    ROOM_DIAGRAMS[self.room_group] = diagram
                error = enqueue(self.diagram_id, self.user.id, self.username, self.project_role,
                                message["id"], self.channel_layer, diagram=diagram)
                if error:
                    await self.send(text_data=json.dumps({"type": "chat_error", "detail": error}))
            return

        if msg_type == "proposal_decision":
            message, error = await database_sync_to_async(decide)(
                self.diagram_id, self.user.id, self.project_role,
                data.get("message_id"), data.get("decision"))
            if error:
                await self.send(text_data=json.dumps({"type": "chat_error", "detail": error}))
            else:
                await self.channel_layer.group_send(self.room_group, {
                    "type": "broadcast_chat_message_update", "message": message})
            return

        if msg_type == "proposal_result":
            message, error = await database_sync_to_async(record_result)(
                self.diagram_id, self.user.id, self.project_role, data.get("message_id"),
                data.get("applied"), data.get("failed"))
            if error:
                await self.send(text_data=json.dumps({"type": "chat_error", "detail": error}))
            else:
                await self.channel_layer.group_send(self.room_group, {
                    "type": "broadcast_chat_message_update", "message": message})
            return

        if self.project_role == "viewer" and msg_type in ("diagram_update", "cursor_move"):
            return

        if msg_type == "diagram_update":
            ROOM_DIAGRAMS[self.room_group] = {"nodes": data.get("nodes", []), "edges": data.get("edges", [])}
            # Re-difundir el estado completo del diagrama a todos excepto el remitente
            await self.channel_layer.group_send(
                self.room_group,
                {
                    "type": "broadcast_diagram_update",
                    "sender_channel": self.channel_name,
                    "username": self.username,
                    "user_id": self.user.id,
                    "nodes": data.get("nodes", []),
                    "edges": data.get("edges", []),
                    "timestamp": data.get("timestamp"),
                },
            )

        elif msg_type == "cursor_move":
            await self.channel_layer.group_send(
                self.room_group,
                {
                    "type": "broadcast_cursor_move",
                    "sender_channel": self.channel_name,
                    "username": self.username,
                    "user_id": self.user.id,
                    "x": data.get("x", 0),
                    "y": data.get("y", 0),
                    "color": data.get("color", "#2563eb"),
                },
            )

        elif msg_type == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))

    # ─── Handlers de grupo (channel_layer → websocket) ─────────────────────────

    async def broadcast_diagram_update(self, event):
        """Reenvía actualización del diagrama a este cliente (excepto al remitente)."""
        if event.get("sender_channel") == self.channel_name:
            return  # No enviar de vuelta al emisor

        await self.send(text_data=json.dumps({
            "type": "diagram_update",
            "username": event["username"],
            "user_id": event["user_id"],
            "nodes": event["nodes"],
            "edges": event["edges"],
            "timestamp": event.get("timestamp"),
        }))

    async def broadcast_cursor_move(self, event):
        """Reenvía posición de cursor (excepto al emisor)."""
        if event.get("sender_channel") == self.channel_name:
            return

        await self.send(text_data=json.dumps({
            "type": "cursor_move",
            "username": event["username"],
            "user_id": event["user_id"],
            "x": event["x"],
            "y": event["y"],
            "color": event.get("color", "#2563eb"),
        }))

    async def broadcast_user_join(self, event):
        """Notifica a todos (incluyendo al nuevo) que alguien se unió."""
        await self.send(text_data=json.dumps({
            "type": "user_join",
            "username": event["username"],
            "user_id": event["user_id"],
        }))

    async def broadcast_chat_message(self, event):
        """Entrega el mensaje persistido a todos, incluido su autor."""
        await self.send(text_data=json.dumps({"type": "chat_message", "message": event["message"]}))

    async def broadcast_chat_message_update(self, event):
        await self.send(text_data=json.dumps({"type": "chat_message_update", "message": event["message"]}))

    async def broadcast_ai_typing(self, event):
        await self.send(text_data=json.dumps({"type": "ai_typing", "active": event["active"],
                                              "for_user_id": event["for_user_id"],
                                              "for_username": event["for_username"]}))

    async def broadcast_ai_settings(self, event):
        await self.send(text_data=json.dumps({"type": "ai_settings", "settings": event["settings"]}))

    async def broadcast_user_leave(self, event):
        """Notifica a todos que alguien salió."""
        await self.send(text_data=json.dumps({
            "type": "user_leave",
            "username": event["username"],
            "user_id": event["user_id"],
        }))

    # ─── Helpers de BD (síncronos → asíncronos) ─────────────────────────────────

    @database_sync_to_async
    def _save_chat_message(self, content):
        from apps.chat.models import ChatMessage, message_data
        message = ChatMessage.objects.create(project_id=self.diagram_id, author=self.user, content=content)
        return message_data(message)

    @database_sync_to_async
    def _ai_is_enabled(self):
        from apps.chat.models import ProjectAISettings
        configuration, _ = ProjectAISettings.objects.get_or_create(project_id=self.diagram_id)
        return configuration.enabled

    @database_sync_to_async
    def _authenticate_from_token(self):
        """
        Intenta autenticar al usuario desde el JWT en el query-string.
        Retorna el User o None si falla.
        """
        from urllib.parse import parse_qs
        from rest_framework_simplejwt.tokens import AccessToken
        from rest_framework_simplejwt.exceptions import TokenError
        from django.contrib.auth import get_user_model

        User = get_user_model()
        query_string = self.scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token_list = params.get("token", [])
        if not token_list:
            return None
        try:
            access_token = AccessToken(token_list[0])
            return User.objects.get(id=access_token["user_id"])
        except (TokenError, User.DoesNotExist, Exception):
            return None

    @database_sync_to_async
    def _get_project_role(self, user, diagram_id):
        """
        Verifica que el usuario es dueño o colaborador del proyecto
        cuyo id coincide con diagram_id.
        """
        from apps.projects.models import Project, ProjectCollaborator
        try:
            project = Project.objects.get(id=diagram_id)
            if project.owner == user:
                return "owner"
            return ProjectCollaborator.objects.filter(project=project, user=user).values_list("role", flat=True).first()
        except Project.DoesNotExist:
            return None
