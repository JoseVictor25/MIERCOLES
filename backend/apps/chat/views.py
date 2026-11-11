from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from apps.projects.models import Project
from apps.projects.views import check_access
from .models import ChatMessage, ProjectAISettings, message_data, settings_data
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def project_chat(request, pk):
    """Historial reciente o página anterior de mensajes del proyecto."""
    project = get_object_or_404(Project, pk=pk)
    allowed, detail = check_access(project, request.user)
    if not allowed:
        return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)
    try:
        limit = max(1, min(int(request.query_params.get("limit", 50)), 100))
        before = request.query_params.get("before")
        before_id = int(before) if before is not None else None
        if before_id is not None and before_id <= 0:
            raise ValueError
        after = request.query_params.get("after")
        after_id = int(after) if after is not None else None
        if after_id is not None and after_id < 0 or (after_id is not None and before_id is not None):
            raise ValueError
    except (TypeError, ValueError):
        return Response({"detail": "Parámetros de paginación inválidos."}, status=400)
    query = ChatMessage.objects.filter(project=project).select_related("author", "reply_to_user")
    if before_id is not None:
        query = query.filter(id__lt=before_id)
    if after_id is not None:
        page = list(query.filter(id__gt=after_id).order_by("id")[:limit + 1])
        return Response({"messages": [message_data(m) for m in page[:limit]],
                         "has_more": len(page) > limit})
    page = list(query.order_by("-id")[:limit + 1])
    return Response({"messages": [message_data(m) for m in reversed(page[:limit])],
                     "has_more": len(page) > limit})


@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def project_ai_settings(request, pk):
    """Consulta o modifica la configuración de IA del proyecto."""
    project = get_object_or_404(Project, pk=pk)
    allowed, detail = check_access(project, request.user)
    if not allowed:
        return Response({"detail": detail}, status=403)
    if request.method == "PATCH" and project.owner_id != request.user.id:
        return Response({"detail": "Solo el dueño puede configurar la IA."}, status=403)
    configuration, _ = ProjectAISettings.objects.get_or_create(project=project)
    if request.method == "PATCH":
        data = request.data
        if not isinstance(data, dict) or set(data) - {"enabled", "mode", "persona"}:
            return Response({"detail": "Campos de configuración inválidos."}, status=400)
        if "enabled" in data and not isinstance(data["enabled"], bool):
            return Response({"detail": "enabled debe ser booleano."}, status=400)
        if "mode" in data and data["mode"] not in ProjectAISettings.Mode.values:
            return Response({"detail": "Modo inválido."}, status=400)
        if "persona" in data and data["persona"] not in ProjectAISettings.Persona.values:
            return Response({"detail": "Persona inválida."}, status=400)
        for field in ("enabled", "mode", "persona"):
            if field in data:
                setattr(configuration, field, data[field])
        configuration.save()
        async_to_sync(get_channel_layer().group_send)(f"diagram_{pk}", {
            "type": "broadcast_ai_settings", "settings": settings_data(configuration),
        })
    return Response(settings_data(configuration))
