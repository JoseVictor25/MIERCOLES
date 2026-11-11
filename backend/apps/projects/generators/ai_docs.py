"""Documentación Java asistida por el modelo local."""

import logging

from apps.ai_core import llm

logger = logging.getLogger(__name__)


def generate_ai_docs_for_class(class_name: str, attributes: list, methods: list, project_name: str) -> dict:
    """Devuelve JavaDoc y Swagger, o un diccionario vacío si la IA falla."""
    attrs = ", ".join(f"{a.get('type', 'String')} {a.get('name', '')}" for a in attributes)
    meths = ", ".join(f"{m.get('return_type', 'void')} {m.get('name', '')}()" for m in methods)
    prompt = (f"Genera JavaDoc y anotaciones Swagger para {class_name} del proyecto {project_name}. "
              f"Atributos: {attrs}. Métodos: {meths}. "
              "Responde SOLO con JSON válido, sin texto adicional ni cercas de código. "
              'Ejemplo: {"class_javadoc":"/** Clase de ejemplo. */",'
              '"class_swagger":"@Tag(name = Ejemplo)",'
              '"attributes_docs":{},"methods_docs":{}}')
    try:
        raw = llm.chat([{"role": "user", "content": prompt}])
        from apps.ai_core.views import _parse_json_safe
        data = _parse_json_safe(raw)
        if not isinstance(data, dict):
            raise llm.LLMBadOutput("La IA devolvió JavaDoc con formato inválido.")
        return data
    except (llm.LLMUnavailable, llm.LLMBadOutput) as exc:
        logger.warning("JavaDoc omitido para %s: %s", class_name, exc)
        return {}
