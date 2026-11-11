import io
import json
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions, status
from rest_framework.response import Response
from . import llm
from .updates import validar_updates, resumen


def _parse_json_safe(text):
    """Encuentra el primer objeto JSON, incluso entre cercas o texto adicional."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char == "{":
            try:
                value, _ = decoder.raw_decode(text[index:])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
    return None


def _parse_vision_json(text):
    """Acepta objeto o lista JSON, incluso si el modelo añade cercas de código."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char in "{[":
            try:
                value, _ = decoder.raw_decode(text[index:])
                if isinstance(value, (dict, list)):
                    return value
            except json.JSONDecodeError:
                continue
    return None


def _json_del_modelo(messages, model=None, temperature=0.2):
    raw = llm.chat(messages, model=model, temperature=temperature)
    parsed = _parse_json_safe(raw)
    if parsed is None:
        correction = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "Corrige tu respuesta anterior. Responde SOLO con JSON v?lido, sin texto adicional ni cercas de c?digo."},
        ]
        parsed = _parse_json_safe(llm.chat(correction, model=model, temperature=temperature))
    if parsed is None:
        raise llm.LLMBadOutput("La IA no devolvi? JSON v?lido tras un reintento.")
    return parsed


def _error_ia(exc):
    return Response({"detail": str(exc)}, status=504 if isinstance(exc, llm.LLMTimeout) else 503 if isinstance(exc, llm.LLMUnavailable) else 502)


def serialize_diagram(diagram_data: dict) -> str:
    nodes = diagram_data.get("nodes", [])
    id_to_name = {str(n.get("id")): n.get("data", {}).get("name", "") for n in nodes}
    classes = []
    for node in nodes:
        data = node.get("data", {})
        attrs = ", ".join(f"{a.get('name')}: {a.get('data_type', '')}" for a in data.get("attributes", []))
        methods = ", ".join(f"{m.get('name')}(): {m.get('return_type', '')}" for m in data.get("methods", []))
        classes.append(f"{data.get('name')}: atributos [{attrs}], metodos [{methods}]")
    relations = []
    for edge in diagram_data.get("edges", []):
        source, target = id_to_name.get(str(edge.get("source"))), id_to_name.get(str(edge.get("target")))
        if source and target:
            data = edge.get("data", {})
            relations.append(f"{source} --[{data.get('relation_type', 'association')} | origen {data.get('sourceMultiplicity', '')} | destino {data.get('targetMultiplicity', '')}]--> {target}")
    return f"Clases:\n{chr(10).join(classes) or '(ninguna)'}\nRelaciones:\n{chr(10).join(relations) or '(ninguna)'}"


def _build_chat_prompt(diagram_data: dict, user_message: str) -> str:
    diagram_text = serialize_diagram(diagram_data)
    return f"""Eres un editor UML. Devuelve SOLO JSON valido sin texto ni cercas:
{{"message":"consejo breve","updates":[]}}
Acciones permitidas (lista cerrada):
add_class {{name}}; delete_class {{name}}; rename_class {{name,new_name}};
add_attribute {{class_name,attr_name,data_type,visibility}}; delete_attribute {{class_name,attr_name}};
add_relation {{source_class,target_class,relation_type,source_multiplicity?,target_multiplicity?}};
delete_relation {{source_class,target_class}};
update_relation_type {{source_class,target_class,relation_type}};
set_multiplicity {{source_class,target_class,source_multiplicity,target_multiplicity}}.
Tipos: association, dependency, inheritance, aggregation, composition, association_class.
Usa solo nombres existentes, salvo add_class previo. Multiplicidad nunca es atributo.
Para cambiar tipo usa update_relation_type; nunca crees clases para ello.
En herencia source_class es hija y target_class es padre.
Para update_relation_type y set_multiplicity la relacion puede estar dibujada en cualquier direccion.
Si no se puede hacer con esas acciones, updates=[] y explica por que.
Ejemplo 1 entrada: cambia la relacion entre Rol y Cliente a herencia.
Salida: {{"message":"","updates":[{{"action":"update_relation_type","source_class":"Rol","target_class":"Cliente","relation_type":"inheritance"}}]}}
Ejemplo 2 entrada: multiplicidad 1 en Rol y 1..* en Cliente.
Salida: {{"message":"","updates":[{{"action":"set_multiplicity","source_class":"Rol","target_class":"Cliente","source_multiplicity":"1","target_multiplicity":"1..*"}}]}}
Ejemplo 3 entrada: agrega la clase Factura.
Salida: {{"message":"","updates":[{{"action":"add_class","name":"Factura"}}]}}
{diagram_text}
Solicitud: {user_message}"""


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def ai_suggest(request):
    """Valida propuestas del modelo antes de enviarlas al editor."""
    message = request.data.get("message", "").strip()
    if not message:
        return Response({"detail": "El mensaje no puede estar vacio."}, status=400)
    diagram = request.data.get("diagram_data", {})
    try:
        parsed = _json_del_modelo([{"role": "user", "content": _build_chat_prompt(diagram, message)}], temperature=0)
        if not isinstance(parsed.get("updates", []), list):
            raise llm.LLMBadOutput("La IA devolvio acciones con formato invalido.")
        valid, rejected = validar_updates(diagram, parsed.get("updates", []))
        return Response({"reply": resumen(valid, rejected, parsed.get("message", "")),
                         "updates": valid, "rejected": rejected, "model": settings.LLM_TEXT_MODEL})
    except (llm.LLMUnavailable, llm.LLMBadOutput) as exc:
        return _error_ia(exc)


HELP_SYSTEM_PROMPT = (
    "Eres el Asistente Oficial de UMLCraft (editor UML y generador Spring Boot).\n"
    "Guía rápida:\n"
    "- LIENZO: Doble clic o Toolbox agrega clases. Arrastra puntos para conectar relaciones (asociación, herencia, composición, agregación, dependencia).\n"
    "- EDITAR: Clic en nodo abre propiedades (atributos/métodos con tipos String, Integer, etc).\n"
    "- BACKEND: Botón 'Generar Backend' crea un .zip Spring Boot con 5 capas (Entity, DTO, Repository, Service, Controller). Descomprimir, configurar PostgreSQL en application.properties y ejecutar con 'mvn spring-boot:run'.\n"
    "- OTRAS FUNCIONES: Guardar (Ctrl+S), Historial, Exportar PNG, Colaboradores en tiempo real, Importar imagen UML.\n\n"
    "Responde siempre en español de forma concisa, clara y didáctica."
)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def ai_help_chat(request):
    """Responde preguntas sobre UMLCraft."""
    message = request.data.get("message", "").strip()
    if not message:
        return Response({"detail": "El mensaje no puede estar vac?o."}, status=400)
    try:
        reply = llm.chat([{"role": "system", "content": HELP_SYSTEM_PROMPT},
                          {"role": "user", "content": message}], temperature=0.4)
        return Response({"reply": reply, "model": settings.LLM_TEXT_MODEL})
    except (llm.LLMUnavailable, llm.LLMBadOutput) as exc:
        return _error_ia(exc)


CLASSES_PROMPT = """Lee SOLO las clases UML de la imagen. Responde SOLO JSON valido:
{"classes":[{"name":"Nombre","is_abstract":false,"attributes":[{"name":"campo","data_type":"Tipo","visibility":"-"}],"methods":[{"name":"metodo","return_type":"Tipo","visibility":"+"}]}]}
Copia nombres y tipos tal como aparecen. is_abstract=true SOLO si ves abstract o nombre en cursiva; en otro caso false.
No inventes clases ni atributos. Sin texto adicional ni cercas de codigo."""

RELATIONS_PROMPT = """Lee SOLO las relaciones UML de la imagen entre estas clases: {names}.
Responde SOLO JSON valido:
{"relations":[{"source":"ClaseHija","target":"ClasePadre","relation_type":"inheritance","source_multiplicity":"","target_multiplicity":"","label":""}]}
Usa solo nombres de la lista. Triangulo hueco=inheritance: source es hija, extremo SIN triangulo; target es padre, donde esta el triangulo.
Rombo relleno=composition; rombo hueco=aggregation; linea punteada con flecha abierta=dependency; linea simple=association.
Multiplicidades y label SOLO si hay texto escrito junto a la linea; si no, "". No inventes relaciones.
Sin texto adicional ni cercas de codigo."""


def _preparar_imagen(image_file):
    """Recorta bordes blancos antes de reducir y codificar en JPEG."""
    with Image.open(image_file) as original:
        image = original.convert("RGB")
        mask = image.convert("L").point(lambda pixel: 255 if pixel < 245 else 0)
        box = mask.getbbox()
        if box:
            left, top, right, bottom = box
            image = image.crop((max(0, left - 20), max(0, top - 20),
                                min(image.width, right + 20), min(image.height, bottom + 20)))
        image.thumbnail((1280, 1280))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90)
        return output.getvalue()


def _vision_error(exc):
    if isinstance(exc, llm.LLMModelMissing):
        return f"Falta cargar el modelo de visión: {settings.LLM_VISION_MODEL}."
    if isinstance(exc, llm.LLMTimeout):
        return "El modelo de visión tardó demasiado (normal en la primera carga). Espera un minuto y reintenta."
    if isinstance(exc, llm.LLMUnavailable):
        return "El servidor local de LM Studio no está disponible."
    return str(exc)


def _build_reactflow_data(parsed: dict):
    """Convierte la respuesta del modelo a formato React Flow (nodes + edges)."""
    import time
    nodes = []
    edges = []
    class_id_map = {}

    for i, cls in enumerate(parsed.get("classes", [])):
        node_id = f"class-vision-{i}-{int(time.time() * 1000) + i}"
        class_name = cls.get("name", f"Clase{i + 1}")
        class_id_map[class_name] = node_id

        col = i % 4
        row = i // 4

        nodes.append({
            "id": node_id,
            "type": "classNode",
            "position": {"x": 80 + col * 300, "y": 80 + row * 260},
            "data": {
                "id": node_id,
                "name": class_name,
                "is_abstract": cls.get("is_abstract", False),
                "attributes": [
                    {
                        "id": f"attr-{node_id}-{j}",
                        "name": a.get("name", "attr"),
                        "data_type": a.get("data_type", "String"),
                        "visibility": a.get("visibility", "-"),
                    }
                    for j, a in enumerate(cls.get("attributes", []))
                ],
                "methods": [
                    {
                        "id": f"method-{node_id}-{j}",
                        "name": m.get("name", "metodo"),
                        "return_type": m.get("return_type", "void"),
                        "visibility": m.get("visibility", "+"),
                        "parameters": [],
                    }
                    for j, m in enumerate(cls.get("methods", []))
                ],
            },
        })

    for k, rel in enumerate(parsed.get("relations", [])):
        src_name = rel.get("source", "")
        tgt_name = rel.get("target", "")
        src_id = class_id_map.get(src_name)
        tgt_id = class_id_map.get(tgt_name)
        if src_id and tgt_id:
            rel_type = rel.get("relation_type", "association")
            edge_data = {
                "relation_type": rel_type,
                "sourceMultiplicity": rel.get("source_multiplicity", ""),
                "targetMultiplicity": rel.get("target_multiplicity", ""),
                "label": rel.get("label", ""),
                "bendX": 0,
                "bendY": 0,
            }
            edges.append({
                "id": f"edge-vision-{k}",
                "type": "umlEdge",
                "reconnectable": True,
                "source": src_id,
                "target": tgt_id,
                "sourceHandle": "bottom-source",
                "targetHandle": "top-target",
                "data": edge_data,
            })

    return nodes, edges


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def ai_vision(request):
    """Extrae clases y relaciones UML en dos consultas estrechas."""
    image_file = request.FILES.get("image")
    if not image_file:
        return Response({"detail": "Se requiere una imagen."}, status=400)
    if image_file.size > 8 * 1024 * 1024:
        return Response({"detail": "La imagen supera el limite de 8 MB."}, status=400)
    try:
        image_bytes = _preparar_imagen(image_file)
    except (UnidentifiedImageError, OSError, ValueError):
        return Response({"detail": "El archivo no es una imagen valida."}, status=400)

    try:
        classes_data = _parse_vision_json(llm.vision(CLASSES_PROMPT, image_bytes))
        classes = classes_data if isinstance(classes_data, list) else classes_data.get("classes") if isinstance(classes_data, dict) else None
        if not isinstance(classes, list):
            raise llm.LLMBadOutput("El modelo no devolvio las clases en JSON valido.")
        classes = [c for c in classes if isinstance(c, dict) and isinstance(c.get("name"), str) and c["name"].strip()]
        if not classes:
            raise llm.LLMBadOutput("No se encontraron clases UML en la imagen.")
    except (llm.LLMUnavailable, llm.LLMBadOutput) as exc:
        return Response({"nodes": [], "edges": [], "description": "", "model": "none",
                         "error": _vision_error(exc)}, status=200)

    names = [c["name"] for c in classes]
    description = f"Se detectaron {len(classes)} clases."
    relations = []
    try:
        data = _parse_vision_json(llm.vision(RELATIONS_PROMPT.replace("{names}", ", ".join(names)), image_bytes))
        found_relations = data if isinstance(data, list) else data.get("relations") if isinstance(data, dict) else None
        if not isinstance(found_relations, list):
            raise llm.LLMBadOutput("El modelo no devolvio relaciones en JSON valido.")
        known = set(names)
        seen = set()
        for rel in found_relations:
            if not isinstance(rel, dict) or rel.get("source") not in known or rel.get("target") not in known:
                continue
            pair = frozenset((rel["source"], rel["target"]))
            if len(pair) != 2 or pair in seen:
                continue
            seen.add(pair)
            relations.append(rel)
    except (llm.LLMUnavailable, llm.LLMBadOutput) as exc:
        description += " No se pudieron extraer relaciones: " + _vision_error(exc)

    nodes, edges = _build_reactflow_data({"classes": classes, "relations": relations})
    return Response({"nodes": nodes, "edges": edges, "description": description,
                     "model": settings.LLM_VISION_MODEL,
                     "classes_found": len(nodes), "relations_found": len(edges)})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def ai_diagnose(request):
    """Consulta el servidor y la disponibilidad de los modelos."""
    return Response({"llm": llm.health()})
