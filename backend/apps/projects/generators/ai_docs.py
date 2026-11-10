import google.generativeai as genai
from django.conf import settings

def _get_gemini_key():
    key = settings.GEMINI_API_KEY
    return key.strip() if key else ""

def generate_ai_docs_for_class(class_name: str, attributes: list, methods: list, project_name: str) -> dict:
    """
    Llama a Gemini para generar JavaDoc y anotaciones de Swagger
    para una clase específica del diagrama.
    Retorna un diccionario con:
    {
       "class_javadoc": "/** ... */",
       "class_swagger": "@Tag(name=...)",
       "attributes_docs": { "attr_name": "/** ... */ @Schema(...)" },
       "methods_docs": { "method_name": "/** ... */ @Operation(...)" }
    }
    """
    key = _get_gemini_key()
    if not key:
        return {}

    genai.configure(api_key=key)
    
    # Usar un modelo rápido
    model = genai.GenerativeModel(settings.GEMINI_DOCS_MODEL)

    attrs_str = ", ".join([f"{a['type']} {a['name']}" for a in attributes])
    methods_str = ", ".join([f"{m['return_type']} {m['name']}()" for m in methods])

    prompt = f"""
Eres un Arquitecto de Software Experto en Java y Spring Boot.
Genera la documentación JavaDoc y Swagger (OpenAPI 3) para la siguiente clase de un proyecto llamado '{project_name}'.

Clase: {class_name}
Atributos: {attrs_str}
Métodos: {methods_str}

Responde ÚNICAMENTE con un objeto JSON estrictamente válido, sin markdown ni bloques de código, con este formato exacto:
{{
  "class_javadoc": "/**\\n * Descripción profesional de la clase.\\n */",
  "class_swagger": "@Tag(name = \"{class_name}\", description = \"API para la gestión de {class_name}\")",
  "attributes_docs": {{
    "nombreAtributo1": "/** Descripción. */\\n    @Schema(description = \"...\", example = \"...\")"
  }},
  "methods_docs": {{
    "nombreMetodo1": "/** Descripción. */\\n    @Operation(summary = \"...\", description = \"...\")"
  }}
}}
No incluyas explicaciones, solo el JSON parseable.
"""

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.2})
        text = response.text.strip()
        
        # Limpiar bloques markdown si la IA los devuelve
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
            
        import json
        data = json.loads(text.strip())
        return data
    except Exception as e:
        print(f"[AI_DOCS_ERROR] {e}")
        return {}
