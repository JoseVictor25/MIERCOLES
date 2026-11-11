from django.shortcuts import get_object_or_404
from django.http import FileResponse
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from apps.projects.models import Project
from apps.projects.views import check_access
from .models import ChatMessage, ProjectAISettings, message_data, settings_data
from .images import save_image, delete_image, private_path
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


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_chat_image(request, pk):
    """Guarda una imagen privada y la publica como mensaje del proyecto."""
    project = get_object_or_404(Project, pk=pk)
    allowed, detail = check_access(project, request.user, require_editor=True)
    if not allowed:
        return Response({"detail": detail}, status=403)
    uploaded = request.FILES.get("image")
    if uploaded is None:
        return Response({"detail": "Selecciona una imagen."}, status=400)
    caption = request.data.get("content", "")
    if not isinstance(caption, str) or len(caption.strip()) > 2000:
        return Response({"detail": "El texto debe tener hasta 2000 caracteres."}, status=400)
    try:
        meta = save_image(uploaded, project.id)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    try:
        message = ChatMessage.objects.create(project=project, author=request.user,
                                             content=caption.strip(), kind="image", meta=meta)
    except Exception:
        delete_image(meta)
        raise
    result = message_data(message)
    async_to_sync(get_channel_layer().group_send)(f"diagram_{pk}", {
        "type": "broadcast_chat_message", "message": result,
    })
    return Response(result, status=201)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def chat_image_file(request, pk, message_id):
    """Sirve la imagen solo a miembros del proyecto autenticados."""
    project = get_object_or_404(Project, pk=pk)
    allowed, detail = check_access(project, request.user)
    if not allowed:
        return Response({"detail": detail}, status=403)
    message = get_object_or_404(ChatMessage, pk=message_id, project=project, kind="image")
    thumbnail = request.query_params.get("size") == "thumb"
    key = "thumbnail_path" if thumbnail else "image_path"
    try:
        path = private_path(message.meta.get(key))
        if not path.is_file():
            raise ValueError
        handle = path.open("rb")
    except (ValueError, OSError):
        return Response({"detail": "La imagen no está disponible."}, status=404)
    response = FileResponse(handle, content_type="image/jpeg" if thumbnail else message.meta.get("mime_type", "image/jpeg"))
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def analyze_chat_image(request, pk, message_id):
    """Analiza una imagen del chat sin alterar todavía el diagrama."""
    project = get_object_or_404(Project, pk=pk)
    allowed, detail = check_access(project, request.user, require_editor=True)
    if not allowed:
        return Response({"detail": detail}, status=403)
    message = get_object_or_404(ChatMessage, pk=message_id, project=project, kind="image")
    if message.meta.get("analysis"):
        return Response(message.meta["analysis"])
    try:
        path = private_path(message.meta.get("image_path"))
        from apps.ai_core.views import analyze_uml_image
        with path.open("rb") as image_file:
            result = analyze_uml_image(image_file)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    except OSError:
        return Response({"detail": "La imagen no está disponible."}, status=404)
    if result.get("nodes"):
        message.meta = {**message.meta, "analysis": result}
        message.save(update_fields=["meta"])
    return Response(result)
