from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from apps.accounts.models import User
from .models import Project, ProjectCollaborator, DiagramSnapshot
from .serializers import ProjectSerializer, ProjectCollaboratorSerializer, AddCollaboratorSerializer, DiagramSnapshotSerializer
from .permissions import IsProjectOwner, IsProjectMember
from .generators.xmi_uml251 import generate_xmi_251
from .generators.xmi_importer import parse_xmi_preview, MAX_XMI_BYTES


def check_access(project, user, require_editor=False):
    """Verifica si el usuario tiene acceso y permisos de edición."""
    if user.is_superuser or user.is_staff or project.owner == user:
        return True, None
    collab = ProjectCollaborator.objects.filter(project=project, user=user).first()
    if not collab:
        return False, "No tienes acceso a este proyecto."
    if require_editor and collab.role == ProjectCollaborator.Role.VIEWER:
        return False, "Los visualizadores no tienen permisos para editar."
    return True, None


class ProjectListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/projects/  — Lista proyectos donde el usuario es owner o colaborador.
    POST /api/projects/  — Crea un nuevo proyecto.
    """
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return Project.objects.all()
        # Proyectos propios + proyectos donde es colaborador
        owned = Project.objects.filter(owner=user)
        collaborated = Project.objects.filter(collaborators__user=user)
        return (owned | collaborated).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/projects/{id}/  — Detalle del proyecto.
    PATCH  /api/projects/{id}/  — Editar nombre/descripción (solo owner).
    DELETE /api/projects/{id}/  — Eliminar proyecto (solo owner).
    """
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated, IsProjectMember]
    queryset = Project.objects.all()

    def get_permissions(self):
        if self.request.method in ["PATCH", "PUT", "DELETE"]:
            return [permissions.IsAuthenticated(), IsProjectOwner()]
        return [permissions.IsAuthenticated(), IsProjectMember()]


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def add_collaborator(request, pk):
    """POST /api/projects/{id}/collaborators/ — Invitar colaborador (solo owner)."""
    project = get_object_or_404(Project, pk=pk)
    if project.owner_id != request.user.id:
        return Response({"detail": "Solo el dueño puede invitar colaboradores."}, status=status.HTTP_403_FORBIDDEN)

    serializer = AddCollaboratorSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    identifier = serializer.validated_data["identifier"]
    role = serializer.validated_data["role"]

    # Buscar por email o username
    try:
        user = User.objects.get(email=identifier)
    except User.DoesNotExist:
        try:
            user = User.objects.get(username=identifier)
        except User.DoesNotExist:
            return Response(
                {"detail": f"No se encontró ningún usuario con el identificador '{identifier}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

    if user.id == project.owner_id:
        return Response({"detail": "El dueño no puede ser agregado como colaborador."}, status=status.HTTP_400_BAD_REQUEST)

    collab, created = ProjectCollaborator.objects.get_or_create(
        project=project, user=user, defaults={"role": role}
    )
    if not created:
        return Response({"detail": "El usuario ya es colaborador de este proyecto."}, status=status.HTTP_400_BAD_REQUEST)

    return Response(ProjectCollaboratorSerializer(collab).data, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def remove_collaborator(request, pk, user_id):
    """DELETE /api/projects/{id}/collaborators/{user_id}/ — Remover colaborador (solo owner)."""
    project = get_object_or_404(Project, pk=pk)
    if project.owner_id != request.user.id:
        return Response({"detail": "Solo el dueño puede remover colaboradores."}, status=status.HTTP_403_FORBIDDEN)

    collab = get_object_or_404(ProjectCollaborator, project=project, user_id=user_id)
    collab.delete()
    return Response({"detail": "Colaborador removido exitosamente."}, status=status.HTTP_200_OK)


@api_view(["GET", "POST", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def project_diagram(request, pk):
    """
    GET   /api/projects/{id}/diagram/  — Obtiene el objeto datos_diagrama del proyecto.
    POST  /api/projects/{id}/diagram/  — Guarda o actualiza datos_diagrama ({ nodes, edges }).
    PATCH /api/projects/{id}/diagram/  — Guarda o actualiza datos_diagrama ({ nodes, edges }).
    """
    project = get_object_or_404(Project, pk=pk)

    allowed, err_msg = check_access(project, request.user, require_editor=(request.method in ["POST", "PATCH"]))
    if not allowed:
        return Response({"detail": err_msg}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        return Response(project.datos_diagrama or {"nodes": [], "edges": []}, status=status.HTTP_200_OK)

    data = request.data

    # Crear snapshot automático si el diagrama cambió
    old_data = project.datos_diagrama or {}
    if old_data != data:
        # Mantener solo los últimos 20 snapshots
        snapshots_count = DiagramSnapshot.objects.filter(project=project).count()
        if snapshots_count >= 20:
            oldest = DiagramSnapshot.objects.filter(project=project).last()
            oldest.delete()
        label = request.data.get("label", "")
        DiagramSnapshot.objects.create(
            project=project,
            saved_by=request.user,
            diagram_data=old_data,
            label=label,
        )

    project.datos_diagrama = data
    project.save(update_fields=["datos_diagrama", "updated_at"])
    return Response(project.datos_diagrama, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def project_snapshots(request, pk):
    """
    GET  /api/projects/{id}/snapshots/         — Lista los snapshots del proyecto (últimos 20).
    POST /api/projects/{id}/snapshots/         — Crea un snapshot manualmente con etiqueta.
    """
    project = get_object_or_404(Project, pk=pk)
    allowed, err_msg = check_access(project, request.user, require_editor=(request.method == "POST"))
    if not allowed:
        return Response({"detail": err_msg}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        snapshots = DiagramSnapshot.objects.filter(project=project)[:20]
        return Response(DiagramSnapshotSerializer(snapshots, many=True).data)

    # POST — crear snapshot manual
    label = request.data.get("label", "Guardado manual")
    snap = DiagramSnapshot.objects.create(
        project=project,
        saved_by=request.user,
        diagram_data=project.datos_diagrama or {},
        label=label,
    )
    return Response(DiagramSnapshotSerializer(snap).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def restore_snapshot(request, pk, snap_id):
    """
    POST /api/projects/{id}/snapshots/{snap_id}/restore/
    Restaura el diagrama al estado del snapshot indicado.
    """
    project = get_object_or_404(Project, pk=pk)
    snap = get_object_or_404(DiagramSnapshot, pk=snap_id, project=project)

    allowed, err_msg = check_access(project, request.user, require_editor=True)
    if not allowed:
        return Response({"detail": err_msg}, status=status.HTTP_403_FORBIDDEN)

    # Guardar el estado actual como snapshot antes de restaurar
    DiagramSnapshot.objects.create(
        project=project,
        saved_by=request.user,
        diagram_data=project.datos_diagrama or {},
        label="Antes de restaurar",
    )

    project.datos_diagrama = snap.diagram_data
    project.save(update_fields=["datos_diagrama", "updated_at"])
    return Response({"detail": "Diagrama restaurado exitosamente.", "diagram": project.datos_diagrama})

@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def generate_spring_boot(request, pk):
    """
    POST /api/projects/{id}/generate/spring-boot/
    Genera el backend en Spring Boot usando el diagrama actual.
    """
    project = get_object_or_404(Project, pk=pk)
    
    allowed, err_msg = check_access(project, request.user, require_editor=False)
    if not allowed:
        return Response({"detail": err_msg}, status=status.HTTP_403_FORBIDDEN)
        
    group_id = request.data.get("group_id", "com.example")
    artifact_id = request.data.get("artifact_id", "backend")
    include_ai_docs = request.data.get("include_ai_docs", False)
    
    diagram_data = project.datos_diagrama or {}
    
    from apps.generator.engine import SpringGenerator
    
    zip_bytes = SpringGenerator(
        datos_diagrama=diagram_data,
        group_id=group_id,
        artifact_id=artifact_id,
        project_name=project.name,
        include_ai_docs=include_ai_docs,
    ).generate_zip_bytes()
    
    response = HttpResponse(zip_bytes, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{artifact_id}-backend.zip"'
    return response

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def export_xmi(request, pk):
    """
    GET /api/projects/{id}/export-xmi/
    Exporta el diagrama en formato XMI (XML).
    """
    project = get_object_or_404(Project, pk=pk)
    
    allowed, err_msg = check_access(project, request.user, require_editor=False)
    if not allowed:
        return Response({"detail": err_msg}, status=status.HTTP_403_FORBIDDEN)
        
    diagram_data = project.datos_diagrama or {}
    
    from .generators.xmi_generator import generate_xmi
    xmi_str = generate_xmi(diagram_data, project.name)
    
    response = HttpResponse(xmi_str, content_type='application/xml')
    response['Content-Disposition'] = f'attachment; filename="{project.name.replace(" ", "_")}.xmi"'
    return response

@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def import_xmi(request, pk):
    """
    POST /api/projects/{id}/import-xmi/
    Sube un archivo .xmi o .xml, lo parsea y reemplaza el diagrama actual.
    """
    project = get_object_or_404(Project, pk=pk)
    
    allowed, err_msg = check_access(project, request.user, require_editor=True)
    if not allowed:
        return Response({"detail": err_msg}, status=status.HTTP_403_FORBIDDEN)
        
    if "file" not in request.FILES:
        return Response({"detail": "No se envió ningún archivo."}, status=status.HTTP_400_BAD_REQUEST)
        
    file_obj = request.FILES["file"]
    if file_obj.size > MAX_XMI_BYTES:
        return Response({"detail": "El archivo XMI supera el límite de 5 MB."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        raw_bytes = file_obj.read()
        import re
        if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", raw_bytes, re.IGNORECASE):
            return Response({"detail": "No se permiten DOCTYPE ni entidades XML."}, status=status.HTTP_400_BAD_REQUEST)
        from .generators.xmi_parser import parse_xmi
        diagram_data = parse_xmi(raw_bytes)
        
        # Guardar estado anterior
        DiagramSnapshot.objects.create(
            project=project,
            saved_by=request.user,
            diagram_data=project.datos_diagrama or {},
            label="Antes de importar XMI",
        )
        
        project.datos_diagrama = diagram_data
        project.save(update_fields=["datos_diagrama", "updated_at"])
        
        return Response({"detail": "XMI importado", "diagram": diagram_data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"detail": f"Error parseando XMI: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def project_xmi(request, pk):
    """Exporta XMI UML 2.5.1 o el formato 2.1 heredado."""
    project = get_object_or_404(Project, pk=pk)
    allowed, detail = check_access(project, request.user)
    if not allowed:
        return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)
    version = request.query_params.get("version", "2.5.1")
    if version == "2.5.1":
        content = generate_xmi_251(project.datos_diagrama or {}, project.name)
        suffix = "uml251"
    elif version == "2.1":
        from .generators.xmi_generator import generate_xmi
        content = generate_xmi(project.datos_diagrama or {}, project.name)
        suffix = "uml21"
    else:
        return Response({"detail": "Versión XMI no admitida. Usa 2.5.1 o 2.1."}, status=status.HTTP_400_BAD_REQUEST)
    response = HttpResponse(content, content_type="application/xml; charset=utf-8")
    filename = "".join(c if c.isalnum() or c in "-_" else "_" for c in project.name) or "proyecto"
    response["Content-Disposition"] = f'attachment; filename="{filename}_{suffix}.xmi"'
    return response


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def project_xmi_preview(request, pk):
    """Analiza un XMI antes de que el usuario decida aplicarlo al lienzo."""
    project = get_object_or_404(Project, pk=pk)
    allowed, detail = check_access(project, request.user, require_editor=True)
    if not allowed:
        return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)
    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response({"detail": "Selecciona un archivo XMI/XML."}, status=status.HTTP_400_BAD_REQUEST)
    if uploaded.size > MAX_XMI_BYTES:
        return Response({"detail": "El archivo XMI supera el límite de 5 MB."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        diagram = parse_xmi_preview(uploaded.read())
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    counts = {}
    for edge in diagram["edges"]:
        relation = edge.get("data", {}).get("relation_type", "association")
        counts[relation] = counts.get(relation, 0) + 1
    return Response({"classes": len(diagram["nodes"]), "relations": counts, "warnings": diagram["warnings"], "version": diagram["version"], "diagram": {"nodes": diagram["nodes"], "edges": diagram["edges"]}})

