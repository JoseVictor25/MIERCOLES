import base64
import json
import re
import requests as req
from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _get_gemini_key():
    key = settings.GEMINI_API_KEY
    return key.strip() if key else ""


def _gemini_post(model: str, payload: dict, key: str, timeout: int = 15):
    """Llama a la API de Gemini y devuelve el objeto Response."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    return req.post(url, json=payload, timeout=timeout)


def _parse_json_safe(text: str):
    """Extrae el primer objeto JSON válido de un texto."""
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None


# Modelos de Gemini disponibles (en orden de preferencia para visión)
GEMINI_MODELS = settings.GEMINI_MODELS


# ─── CU-09: Chat con IA (Asistente del diagrama) ──────────────────────────────

def _build_chat_prompt(diagram_data: dict, user_message: str) -> str:
    classes = []
    nodes = diagram_data.get("nodes", [])
    edges = diagram_data.get("edges", [])

    for node in nodes:
        d = node.get("data", {})
        name = d.get("name", "?")
        attrs = [
            f"  {a.get('visibility','')}{a.get('name','')}: {a.get('data_type','')}"
            for a in d.get("attributes", [])
        ]
        methods = [
            f"  {m.get('visibility','')}{m.get('name','')}: {m.get('return_type','')}"
            for m in d.get("methods", [])
        ]
        classes.append(f"Clase: {name}\n" + "\n".join(attrs + methods))

    relations = []
    for edge in edges:
        d = edge.get("data", {})
        rel_type = d.get("relation_type", "association")
        src = edge.get("source", "?")
        tgt = edge.get("target", "?")
        relations.append(f"  {src} --[{rel_type}]--> {tgt}")

    diagram_text = "\n\n".join(classes) if classes else "(Diagrama vacío)"
    relations_text = "\n".join(relations) if relations else "  (sin relaciones)"

    return f"""Eres un experto en diseño orientado a objetos y UML 2.5.
El usuario tiene este diagrama de clases UML actual:

=== CLASES ===
{diagram_text}

=== RELACIONES ===
{relations_text}

=== COMANDO / PREGUNTA DEL USUARIO ===
{user_message}

Debes responder ÚNICAMENTE con un objeto JSON válido con la siguiente estructura:
{{
  "message": "Respuesta en texto para el usuario, confirmando lo que hiciste o aconsejando.",
  "updates": [
    {{ "action": "add_class", "name": "NombreClase" }},
    {{ "action": "add_attribute", "class_name": "NombreClase", "attr_name": "nombre", "data_type": "String", "visibility": "-" }},
    {{ "action": "add_relation", "source_class": "ClaseA", "target_class": "ClaseB", "relation_type": "association" }},
    {{ "action": "delete_class", "name": "NombreClase" }},
    {{ "action": "delete_attribute", "class_name": "NombreClase", "attr_name": "nombre" }},
    {{ "action": "delete_relation", "source_class": "ClaseA", "target_class": "ClaseB" }}
  ]
}}
- Si el usuario te pide agregar o eliminar una clase, atributo o relación, incluye la acción en 'updates'.
- Tipos de relación soportados: 'association', 'dependency', 'inheritance', 'aggregation', 'composition', 'association_class'.
- Si el usuario solo hace una pregunta, 'updates' debe ser una lista vacía [].
"""


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def ai_suggest(request):
    """POST /api/ai/suggest/ — Chat con IA sobre el diagrama (solo Gemini)."""
    message = request.data.get("message", "").strip()
    diagram_data = request.data.get("diagram_data", {})

    if not message:
        return Response(
            {"detail": "El mensaje no puede estar vacío."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    gemini_key = _get_gemini_key()
    if not gemini_key:
        return Response(
            {"detail": "GEMINI_API_KEY no configurada. Agrégala al archivo .env del backend."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    prompt = _build_chat_prompt(diagram_data, message)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"},
    }
    errors = []

    for model in GEMINI_MODELS:
        try:
            resp = _gemini_post(model, payload, gemini_key, timeout=15)
            if resp.status_code == 200:
                _rdata = resp.json()
                _parts = _rdata.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                raw = _parts[0].get("text", "") if _parts else ""
                parsed = _parse_json_safe(raw)
                if parsed:
                    return Response({
                        "reply": parsed.get("message", "Hecho."),
                        "updates": parsed.get("updates", []),
                        "model": f"Gemini ({model})",
                    })
                return Response({
                    "reply": "Se ejecutó el comando pero no se pudo leer la respuesta.",
                    "updates": [],
                    "model": f"Gemini ({model})",
                })
            elif resp.status_code == 503:
                errors.append(f"{model}: sobrecargado (503)")
                continue
            elif resp.status_code in (400, 403):
                errors.append(f"{model}: clave inválida (HTTP {resp.status_code})")
                break
            else:
                errors.append(f"{model}: HTTP {resp.status_code} — {resp.text[:120]}")
        except Exception as e:
            errors.append(f"{model}: {str(e)}")

    error_detail = "\n".join(f"• {e}" for e in errors)
    return Response(
        {"detail": f"Error al conectar con Gemini.\n\n{error_detail}"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# ─── CU-10: Imagen → Diagrama UML (solo Gemini Vision) ────────────────────────



# --- Chatbot Guia de Usuario (UMLCraft Help Assistant) ---

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
    """POST /api/ai/help/ -- Chatbot guia de usuario para aprender a usar UMLCraft."""
    message = request.data.get("message", "").strip()
    if not message:
        return Response(
            {"detail": "El mensaje no puede estar vacio."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    gemini_key = _get_gemini_key()
    if not gemini_key:
        return Response(
            {"detail": "GEMINI_API_KEY no configurada."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    full_prompt = HELP_SYSTEM_PROMPT + "\n\n=== PREGUNTA DEL USUARIO ===\n" + message
    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024},
    }
    errors = []
    for model in GEMINI_MODELS:
        try:
            resp = _gemini_post(model, payload, gemini_key, timeout=15)
            if resp.status_code == 200:
                _rdata = resp.json()
                _parts = _rdata.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                raw = _parts[0].get("text", "") if _parts else ""
                return Response({"reply": raw.strip(), "model": "Gemini (" + model + ")" })
            elif resp.status_code == 503:
                errors.append(model + ": sobrecargado")
                continue
            elif resp.status_code in (400, 403):
                errors.append(model + ": clave invalida")
                break
            else:
                errors.append(model + ": HTTP " + str(resp.status_code))
        except Exception as e:
            errors.append(model + ": " + str(e))

    return Response(
        {"detail": "Error Gemini: " + " | ".join(errors)},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


VISION_PROMPT = """Analiza esta imagen y extrae TODAS las clases UML que puedas ver, junto con sus relaciones, multiplicidades y etiquetas.

Responde ÚNICAMENTE con un JSON válido con esta estructura exacta (sin markdown, sin texto extra):
{
  "classes": [
    {
      "name": "NombreClase",
      "is_abstract": false,
      "attributes": [
        {"name": "nombreAtributo", "data_type": "String", "visibility": "-"}
      ],
      "methods": [
        {"name": "nombreMetodo", "return_type": "void", "visibility": "+"}
      ]
    }
  ],
  "relations": [
    {
      "source": "ClaseOrigen",
      "target": "ClaseDestino",
      "relation_type": "association",
      "source_multiplicity": "1",
      "target_multiplicity": "*",
      "label": "nombre de la relacion si aparece",
      "association_class": ""
    }
  ],
  "description": "Breve descripcion de lo que se encontro en la imagen"
}

Reglas IMPORTANTES:
- visibility: "+" para public, "-" para private, "#" para protected
- relation_type: "association", "inheritance", "composition", "aggregation", "dependency", "association_class"
  * Herencia/Generalizacion (flecha triangular hueca) -> "inheritance"
  * Composicion (rombo relleno) -> "composition"
  * Agregacion (rombo hueco) -> "aggregation"
  * Dependencia (linea punteada con flecha abierta) -> "dependency"
  * Asociacion simple (linea solida sin punta especial) -> "association"
  * Clase de Asociacion (relacion muchos-a-muchos con clase intermedia conectada por linea punteada) -> usa "association" para el edge principal entre las dos clases. En el campo "association_class" pon el nombre de la clase intermedia.
- DETECCION DE CLASE DE ASOCIACION: Cuando veas una clase conectada al CENTRO de una linea de asociacion mediante una linea punteada (sin punta de flecha), eso es una clase de asociacion. La clase intermedia (ej: DetalleCompra, DetalleVenta) es la clase de asociacion.
  Ejemplo: Si Producto y Compra tienen una asociacion muchos-a-muchos y DetalleCompra esta conectada al centro con linea punteada, crea:
    {"source": "Producto", "target": "Compra", "relation_type": "association", "source_multiplicity": "0..*", "target_multiplicity": "1..*", "association_class": "DetalleCompra"}
  NO crees relaciones separadas entre DetalleCompra y Producto/Compra.
- source_multiplicity y target_multiplicity: extrae los valores EXACTOS que aparecen en la imagen,
  por ejemplo "1", "0..1", "1..*", "*", "0..*", "1..1". Si no hay multiplicidad visible, usa "".
- label: etiqueta de la relacion si aparece (ej: "tiene", "realiza", "pertenece"). Si no hay, usa "".
- association_class: nombre de la clase de asociacion si existe, si no hay usa "".
- Si no hay clases detectables, retorna {"classes": [], "relations": [], "description": "No se encontraron clases UML"}
- Los nombres de clases deben estar en PascalCase sin espacios
- Responde en español en el campo description
- Es FUNDAMENTAL que detectes TODAS las relaciones entre clases del diagrama"""


def _build_reactflow_data(parsed: dict):
    """Convierte la respuesta de Gemini a formato React Flow (nodes + edges)."""
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
            assoc_class_name = rel.get("association_class", "") or ""
            assoc_class_id = class_id_map.get(assoc_class_name) if assoc_class_name else None
            # Forzar relation_type a 'association' cuando hay una clase de asociacion
            rel_type = rel.get("relation_type", "association")
            if assoc_class_id:
                rel_type = "association"
            edge_data = {
                "relation_type": rel_type,
                "sourceMultiplicity": rel.get("source_multiplicity", ""),
                "targetMultiplicity": rel.get("target_multiplicity", ""),
                "label": rel.get("label", ""),
                "bendX": 0,
                "bendY": 0,
            }
            if assoc_class_id:
                edge_data["associationClassId"] = assoc_class_id
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
    """
    POST /api/ai/vision/
    Analiza una imagen con Gemini Vision y genera un diagrama de clases UML.
    Body (multipart/form-data): { image: File }
    Respuesta: { nodes, edges, description, model }
    """
    image_file = request.FILES.get("image")
    if not image_file:
        return Response(
            {"detail": "Se requiere una imagen."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    gemini_key = _get_gemini_key()
    if not gemini_key:
        return Response(
            {
                "nodes": [], "edges": [], "description": "", "model": "none",
                "error": (
                    "GEMINI_API_KEY no configurada.\n\n"
                    "1. Ve a https://aistudio.google.com -> Get API Key\n"
                    "2. Agrega GEMINI_API_KEY=tu_clave al archivo .env del backend\n"
                    "3. Reinicia el servidor Django"
                ),
            },
            status=status.HTTP_200_OK,
        )

    image_data = image_file.read()
    image_b64 = base64.b64encode(image_data).decode("utf-8")
    mime_type = image_file.content_type or "image/jpeg"

    payload = {
        "contents": [{
            "parts": [
                {"text": VISION_PROMPT},
                {"inline_data": {"mime_type": mime_type, "data": image_b64}},
            ]
        }]
    }

    errors = []

    for model in GEMINI_MODELS:
        try:
            resp = _gemini_post(model, payload, gemini_key, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    raw = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    parsed = _parse_json_safe(raw)
                    if parsed and "classes" in parsed and len(parsed.get("classes", [])) > 0:
                        nodes, edges = _build_reactflow_data(parsed)
                        return Response({
                            "nodes": nodes,
                            "edges": edges,
                            "description": parsed.get("description", f"Clases extraídas con {model}"),
                            "model": f"Gemini Vision ({model})",
                            "classes_found": len(nodes),
                            "relations_found": len(edges),
                        })
                    elif parsed and "classes" in parsed:
                        errors.append(f"{model}: no se detectaron clases ({parsed.get('description', '')})")
                    else:
                        errors.append(f"{model}: respuesta no parseable -> {raw[:150]}")
            elif resp.status_code == 503:
                errors.append(f"{model}: sobrecargado (503), probando siguiente...")
                continue
            elif resp.status_code in (400, 403):
                errors.append(f"{model}: clave inválida o sin permisos (HTTP {resp.status_code}) — {resp.text[:150]}")
                break  # No tiene sentido probar más modelos con la misma clave inválida
            else:
                errors.append(f"{model}: HTTP {resp.status_code} — {resp.text[:120]}")
        except Exception as e:
            errors.append(f"{model}: {str(e)}")

    error_detail = "\n".join(f"• {e}" for e in errors)
    return Response(
        {
            "nodes": [], "edges": [], "description": "", "model": "none",
            "errors": errors,
            "error": (
                f"No se pudieron extraer clases de la imagen.\n\n"
                f"Detalles:\n{error_detail}\n\n"
                f"Sugerencias:\n"
                f"1. Verifica que la GEMINI_API_KEY en el .env sea válida.\n"
                f"2. Obtén una clave gratis en https://aistudio.google.com\n"
                f"3. Usa una imagen nítida con texto legible."
            ),
        },
        status=status.HTTP_200_OK,
    )


# ─── Diagnóstico de Gemini ─────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def ai_diagnose(request):
    """GET /api/ai/diagnose/ — Verifica el estado de Gemini."""
    results = {}

    gemini_key = _get_gemini_key()
    if not gemini_key:
        results["gemini"] = {
            "status": "error",
            "detail": "GEMINI_API_KEY no configurada en .env",
        }
    else:
        try:
            payload = {"contents": [{"parts": [{"text": "Responde solo: OK"}]}]}
            resp = _gemini_post(settings.GEMINI_DIAGNOSE_MODEL, payload, gemini_key, timeout=15)
            if resp.status_code == 200:
                results["gemini"] = {
                    "status": "ok",
                    "model": settings.GEMINI_DIAGNOSE_MODEL,
                    "detail": "Gemini disponible y funcionando correctamente",
                }
            elif resp.status_code == 400:
                results["gemini"] = {
                    "status": "error",
                    "detail": f"Clave inválida o mal formateada: {resp.text[:200]}",
                }
            elif resp.status_code == 403:
                results["gemini"] = {
                    "status": "error",
                    "detail": "Clave sin permisos o inválida (403). Genera una nueva en aistudio.google.com",
                }
            else:
                results["gemini"] = {
                    "status": "error",
                    "detail": f"HTTP {resp.status_code}: {resp.text[:200]}",
                }
        except Exception as e:
            results["gemini"] = {"status": "error", "detail": str(e)}

    return Response(results)

