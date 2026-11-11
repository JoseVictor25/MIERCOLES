"""Pruebas del acceso a la IA local y de la recuperación de JSON."""

from unittest.mock import Mock, patch
import io

import requests
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from . import llm
from .updates import validar_updates
from .views import _build_chat_prompt, _preparar_imagen, _vision_error


class AIEndpointsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user = get_user_model().objects.create_user(username="tester", password="clave-segura")
        self.client.force_authenticate(user=user)

    @staticmethod
    def completion(content):
        response = Mock(status_code=200, ok=True)
        response.json.return_value = {"choices": [{"message": {"content": content}}]}
        return response

    @patch("apps.ai_core.llm.requests.post")
    def test_chat_valido(self, post):
        post.return_value = self.completion('{"message":"Clase creada","updates":[{"action":"add_class","name":"Cliente"}]}')
        response = self.client.post("/api/ai/suggest/", {"message": "Agrega Cliente", "diagram_data": {}}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updates"][0]["name"], "Cliente")
        payload = post.call_args.kwargs["json"]
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["model"], llm.settings.LLM_TEXT_MODEL)

    @patch("apps.ai_core.llm.requests.post")
    def test_json_invalido_con_un_reintento(self, post):
        post.side_effect = [self.completion("respuesta inválida"),
                            self.completion('```json\n{"message":"Listo","updates":[]}\n```')]
        response = self.client.post("/api/ai/suggest/", {"message": "Revisa", "diagram_data": {}}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reply"], "Listo")
        self.assertEqual(post.call_count, 2)

    @patch("apps.ai_core.llm.requests.post", side_effect=requests.ConnectionError("caído"))
    def test_servidor_caido(self, post):
        response = self.client.post("/api/ai/suggest/", {"message": "Revisa"}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Inicia el servidor local", response.data["detail"])

    @patch("apps.ai_core.llm.requests.post", side_effect=requests.Timeout("agotado"))
    def test_timeout(self, post):
        response = self.client.post("/api/ai/suggest/", {"message": "Revisa"}, format="json")
        self.assertEqual(response.status_code, 504)
        self.assertIn("tardó demasiado", response.data["detail"])

    def test_validacion_de_relacion_y_clases(self):
        diagram = {"nodes": [{"id": "n1", "data": {"name": "Rol"}},
                             {"id": "n2", "data": {"name": "Cliente"}}],
                   "edges": [{"source": "n1", "target": "n2", "data": {"relation_type": "association",
                                                                "sourceMultiplicity": "1",
                                                                "targetMultiplicity": "1..*"}}]}
        updates = [
            {"action": "update_relation_type", "source_class": "Rol", "target_class": "Cliente", "relation_type": "inheritance"},
            {"action": "set_multiplicity", "source_class": "Cliente", "target_class": "Rol", "source_multiplicity": "1..*", "target_multiplicity": "1"},
            {"action": "add_attribute", "class_name": "Fantasma", "attr_name": "x"},
            {"action": "delete_relation", "source_class": "Rol", "target_class": "Fantasma"},
        ]
        valid, rejected = validar_updates(diagram, updates)
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(rejected), 2)
        prompt = _build_chat_prompt(diagram, "revisa")
        self.assertIn("Rol --[association | origen 1 | destino 1..*]--> Cliente", prompt)
        self.assertNotIn("n1 --[", prompt)

    def test_recorte_y_mensajes_de_vision(self):
        image = Image.new("RGB", (200, 160), "white")
        for x in range(80, 120):
            for y in range(60, 100):
                image.putpixel((x, y), (0, 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        jpeg = _preparar_imagen(io.BytesIO(buffer.getvalue()))
        with Image.open(io.BytesIO(jpeg)) as cropped:
            self.assertEqual(cropped.size, (80, 80))
        self.assertIn("tardó demasiado", _vision_error(llm.LLMTimeout()))
        self.assertIn("no está disponible", _vision_error(llm.LLMUnavailable()))
        self.assertIn(llm.settings.LLM_VISION_MODEL, _vision_error(llm.LLMModelMissing()))

    @patch("apps.ai_core.llm.vision")
    def test_vision_devuelve_clases_si_fallan_relaciones(self, vision):
        vision.side_effect = ['{"classes":[{"name":"Persona","is_abstract":false,"attributes":[],"methods":[]}]}',
                              llm.LLMTimeout()]
        image = Image.new("RGB", (50, 50), "white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        upload = SimpleUploadedFile("uml.png", buffer.getvalue(), content_type="image/png")
        response = self.client.post("/api/ai/vision/", {"image": upload}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["nodes"]), 1)
        self.assertIn("No se pudieron extraer relaciones", response.data["description"])

    @patch("apps.ai_core.llm.vision")
    def test_vision_acepta_listas_de_clases_y_relaciones(self, vision):
        vision.side_effect = [
            '[{"name":"Paciente","is_abstract":false,"attributes":[],"methods":[]},'
            '{"name":"Persona","is_abstract":false,"attributes":[],"methods":[]}]',
            '[{"source":"Paciente","target":"Persona","relation_type":"inheritance",'
            '"source_multiplicity":"","target_multiplicity":"","label":""}]',
        ]
        image = Image.new("RGB", (40, 40), "white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        upload = SimpleUploadedFile("uml.png", buffer.getvalue(), content_type="image/png")
        response = self.client.post("/api/ai/vision/", {"image": upload}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["nodes"]), 2)
        self.assertEqual(len(response.data["edges"]), 1)

    @patch("apps.ai_core.llm.requests.post")
    def test_schema_reintenta_sin_formato_si_servidor_rechaza(self, post):
        rejected = Mock(status_code=400, ok=False, text="response_format json_schema no soportado")
        post.side_effect = [rejected, self.completion('{"reply":"Bien","updates":[]}'),
                            self.completion('{"reply":"Otra","updates":[]}')]
        previous = llm._SCHEMA_UNSUPPORTED
        llm._SCHEMA_UNSUPPORTED = False
        try:
            schema = {"type": "object", "properties": {}}
            self.assertIn("Bien", llm.chat([{"role": "user", "content": "hola"}], response_schema=schema))
            self.assertIn("response_format", post.call_args_list[0].kwargs["json"])
            self.assertNotIn("response_format", post.call_args_list[1].kwargs["json"])
            llm.chat([{"role": "user", "content": "hola"}], response_schema=schema)
            self.assertNotIn("response_format", post.call_args_list[2].kwargs["json"])
        finally:
            llm._SCHEMA_UNSUPPORTED = previous
