"""Acceso único a servidores locales compatibles con la API de OpenAI."""

import base64
import re

import requests
from django.conf import settings


_SCHEMA_UNSUPPORTED = False


class LLMUnavailable(Exception):
    """El servidor no responde o rechaza la petición."""


class LLMTimeout(LLMUnavailable):
    """El servidor tardó más del tiempo permitido."""


class LLMBadOutput(Exception):
    """La respuesta del modelo no tiene el formato esperado."""


class LLMModelMissing(LLMUnavailable):
    """El modelo configurado no está cargado o disponible."""


def _url(path):
    return f"{settings.LLM_BASE_URL.rstrip('/')}/{path}"


def _headers():
    return {"Authorization": f"Bearer {settings.LLM_API_KEY}", "Content-Type": "application/json"}


def _check_response(response, model):
    if response.status_code == 404 or (response.status_code == 400 and "model" in response.text.lower()):
        raise LLMModelMissing(f"Falta el modelo '{model}'. Inicia el servidor local de LM Studio y verifica los modelos.")
    if not response.ok:
        raise LLMUnavailable(f"El servidor local de IA rechazó la solicitud (HTTP {response.status_code}): {response.text[:180]}")


def chat(messages, model=None, timeout=None, temperature=0.2, response_schema=None) -> str:
    model = model or settings.LLM_TEXT_MODEL
    global _SCHEMA_UNSUPPORTED
    try:
        payload = {"model": model, "messages": messages, "temperature": temperature, "stream": False}
        if response_schema is not None and not _SCHEMA_UNSUPPORTED:
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "respuesta_ia", "strict": True, "schema": response_schema,
            }}
        response = requests.post(
            _url("chat/completions"),
            headers=_headers(),
            json=payload,
            timeout=timeout or settings.LLM_TIMEOUT,
        )
        if ("response_format" in payload and response.status_code == 400
                and re.search(r"response_format|json_schema|structured.output|grammar|schema|format", response.text, re.IGNORECASE)):
            _SCHEMA_UNSUPPORTED = True
            payload = {key: value for key, value in payload.items() if key != "response_format"}
            response = requests.post(
                _url("chat/completions"), headers=_headers(), json=payload,
                timeout=timeout or settings.LLM_TIMEOUT,
            )
        _check_response(response, model)
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("contenido vacío")
        return content.strip()
    except requests.Timeout as exc:
        raise LLMTimeout("La IA local tardó demasiado. Espera a que cargue el modelo y vuelve a intentar.") from exc
    except requests.RequestException as exc:
        raise LLMUnavailable("No se puede conectar con la IA. Inicia el servidor local de LM Studio y verifica los modelos.") from exc
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMBadOutput("La IA devolvió una respuesta vacía o con formato inesperado.") from exc


def vision(prompt, image_bytes, mime="image/jpeg") -> str:
    image_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": image_url}},
    ]}]
    return chat(messages, model=settings.LLM_VISION_MODEL,
                timeout=settings.LLM_VISION_TIMEOUT, temperature=0)


def health() -> dict:
    """Consulta modelos sin cargar ninguno; útil con GPU de memoria limitada."""
    result = {"status": "error", "server_accessible": False, "models": [],
              "text_model": settings.LLM_TEXT_MODEL, "vision_model": settings.LLM_VISION_MODEL,
              "text_model_available": False, "vision_model_available": False}
    try:
        response = requests.get(_url("models"), headers=_headers(), timeout=10)
        _check_response(response, "modelos")
        models = [item["id"] for item in response.json().get("data", []) if isinstance(item, dict) and "id" in item]
        result.update(server_accessible=True, models=models,
                      text_model_available=settings.LLM_TEXT_MODEL in models,
                      vision_model_available=settings.LLM_VISION_MODEL in models)
        result["status"] = "ok" if result["text_model_available"] and result["vision_model_available"] else "error"
        result["detail"] = ("Servidor local y modelos disponibles." if result["status"] == "ok"
                            else "Falta un modelo configurado. Inicia el servidor local de LM Studio y verifica los modelos.")
    except (requests.RequestException, LLMUnavailable, ValueError, KeyError, TypeError):
        result["detail"] = "No se puede conectar con la IA. Inicia el servidor local de LM Studio y verifica los modelos."
    return result
