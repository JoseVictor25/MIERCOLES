"""Pruebas del historial y de la difusión del chat compartido."""

from asgiref.sync import async_to_sync
import asyncio
import io
import tempfile
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.projects.models import Project, ProjectCollaborator
from apps.realtime.consumers import DiagramConsumer
from .models import ChatMessage, ProjectAISettings
from .ai_worker import ROOM_DIAGRAMS, _answer, _context, _prompt, enqueue, has_mention
from .decisions import decide, record_result


class ChatTests(TransactionTestCase):
    def _diagram_for_clearing(self, attributes=True):
        diagram = {"nodes": [
            {"id": "m", "data": {"name": "Médico", "attributes":
                ([{"name": "id"}, {"name": "especialidad"}, {"name": "consultorio_id"}]
                 if attributes else []), "methods": [{"name": "atender"}]}},
            {"id": "p", "data": {"name": "Paciente", "attributes": [], "methods": []}}],
            "edges": []}
        self.project.datos_diagrama = diagram
        self.project.save(update_fields=["datos_diagrama"])
        return diagram

    def _ask_to_clear(self, content):
        current = ChatMessage.objects.create(project=self.project, author=self.owner, content=content)
        layer = SimpleNamespace(group_send=AsyncMock())
        async_to_sync(_answer)(self.project.id, self.owner.id, "owner", "owner", current.id, layer)
        return ChatMessage.objects.filter(is_ai=True).latest("id")

    def test_atajo_elimina_tres_atributos_sin_modelo_y_acepta_tildes(self):
        ProjectAISettings.objects.create(project=self.project, mode="proposer")
        self._diagram_for_clearing()
        with patch("apps.chat.ai_worker.llm.chat") as chat:
            for content in ("@ia elimina todos los atributos de medico",
                            "@ia elimina los atributos de Médico"):
                answer = self._ask_to_clear(content)
                self.assertEqual(answer.kind, "proposal")
                self.assertEqual([item["attr_name"] for item in answer.meta["updates"]],
                                 ["id", "especialidad", "consultorio_id"])
                self.assertTrue(all(set(item) == {"action", "class_name", "attr_name"}
                                    for item in answer.meta["updates"]))
                self.assertIn("eliminar todos los atributos de Médico (3)", answer.content)
            emptied = self._ask_to_clear("@ia vacía la clase Médico")
            self.assertEqual(emptied.kind, "proposal")
            self.assertEqual(len(emptied.meta["updates"]), 4)
            chat.assert_not_called()

    def test_nombres_concretos_usan_modelo_y_compuesta_del_modelo_se_expande(self):
        ProjectAISettings.objects.create(project=self.project, mode="proposer")
        self._diagram_for_clearing()
        named = '{"reply":"Propongo borrar id","updates":[{"action":"delete_attribute","class_name":"Médico","attr_name":"id"}]}'
        compound = '{"reply":"Propongo vaciar","updates":[{"action":"clear_attributes","class_name":"medico"}]}'
        with patch("apps.chat.ai_worker.llm.chat", side_effect=[named, compound]) as chat:
            answer = self._ask_to_clear("@ia elimina id y especialidad de Medico")
            self.assertEqual(answer.kind, "proposal")
            self.assertEqual(len(answer.meta["updates"]), 1)
            answer = self._ask_to_clear("@ia quita cuanto sea posible de Medico")
            self.assertEqual(len(answer.meta["updates"]), 3)
            self.assertEqual(chat.call_count, 2)

    def test_atajo_clase_vacia_inexistente_y_modo_asesor(self):
        settings = ProjectAISettings.objects.create(project=self.project, mode="proposer")
        self._diagram_for_clearing(attributes=False)
        with patch("apps.chat.ai_worker.llm.chat") as chat:
            empty = self._ask_to_clear("@ia borra los atributos de Medico")
            self.assertEqual(empty.kind, "text")
            self.assertEqual(empty.content, "La clase Médico no tiene atributos.")
            missing = self._ask_to_clear("@ia elimina todos los atributos de Fantasma")
            self.assertEqual(missing.kind, "text")
            self.assertIn("La clase Fantasma no existe. Clases del diagrama: Médico, Paciente.", missing.content)
            settings.mode = "advisor"
            settings.save(update_fields=["mode"])
            advisor = self._ask_to_clear("@ia elimina los atributos de Médico")
            self.assertEqual(advisor.kind, "text")
            self.assertEqual(advisor.content, "En modo asesor no se aplicaron cambios al lienzo.")
            chat.assert_not_called()

    def test_reintento_sin_acciones_explicita_clase_vacia_o_inexistente(self):
        ProjectAISettings.objects.create(project=self.project, mode="proposer")
        self._diagram_for_clearing(attributes=False)
        response = '{"reply":"Propongo borrar atributos","updates":[]}'
        with patch("apps.chat.ai_worker.llm.chat", side_effect=[response] * 4) as chat:
            empty = self._ask_to_clear("@ia remueve cada atributo de Medico")
            self.assertEqual(empty.content, "La clase Médico no tiene atributos.")
            missing = self._ask_to_clear("@ia cambia atributos de Fantasma")
            self.assertIn("La clase Fantasma no existe. Clases del diagrama: Médico, Paciente.", missing.content)
            self.assertEqual(chat.call_count, 4)

    def setUp(self):
        ROOM_DIAGRAMS.clear()
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="owner", email="owner@example.com", password="clave")
        self.editor = user_model.objects.create_user(username="editor", email="editor@example.com", password="clave")
        self.viewer = user_model.objects.create_user(username="viewer", email="viewer@example.com", password="clave")
        self.other = user_model.objects.create_user(username="other", email="other@example.com", password="clave")
        self.project = Project.objects.create(name="Proyecto", owner=self.owner)
        ProjectCollaborator.objects.create(project=self.project, user=self.editor, role="editor")
        ProjectCollaborator.objects.create(project=self.project, user=self.viewer, role="viewer")
        self.client = APIClient()

    def test_historial_paginado_y_permisos(self):
        for index in range(5):
            ChatMessage.objects.create(project=self.project, author=self.owner, content=f"Mensaje {index}")
        self.client.force_authenticate(user=self.viewer)
        recent = self.client.get(f"/api/projects/{self.project.id}/chat/?limit=2")
        self.assertEqual(recent.status_code, 200)
        self.assertEqual([m["content"] for m in recent.data["messages"]], ["Mensaje 3", "Mensaje 4"])
        self.assertTrue(recent.data["has_more"])
        before = recent.data["messages"][0]["id"]
        older = self.client.get(f"/api/projects/{self.project.id}/chat/?limit=2&before={before}")
        self.assertEqual([m["content"] for m in older.data["messages"]], ["Mensaje 1", "Mensaje 2"])
        after = self.client.get(f"/api/projects/{self.project.id}/chat/?limit=2&after={older.data['messages'][-1]['id']}")
        self.assertEqual([m["content"] for m in after.data["messages"]], ["Mensaje 3", "Mensaje 4"])
        self.client.force_authenticate(user=self.other)
        self.assertIn(self.client.get(f"/api/projects/{self.project.id}/chat/").status_code, (403, 404))
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.get("/api/projects/999999/chat/").status_code, 404)

    def _image_file(self):
        output = io.BytesIO()
        Image.new("RGB", (96, 72), "white").save(output, format="PNG")
        return SimpleUploadedFile("diagrama.png", output.getvalue(), content_type="image/png")

    def _private_images(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        setting = override_settings(CHAT_IMAGE_ROOT=folder.name)
        setting.enable()
        self.addCleanup(setting.disable)
        return folder.name

    def test_imagen_privada_historial_y_permisos(self):
        from pathlib import Path
        folder = self._private_images()
        url = f"/api/projects/{self.project.id}/chat/images/"
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(url, {"image": self._image_file(), "content": "  Diagrama inicial  "}, format="multipart")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["kind"], "image")
        self.assertEqual(response.data["content"], "Diagrama inicial")
        self.assertNotIn("image_path", response.data["meta"])
        self.assertTrue(response.data["meta"]["thumbnail_url"])
        message = ChatMessage.objects.get(pk=response.data["id"])
        original_path = Path(folder) / message.meta["image_path"]
        self.assertTrue(original_path.is_file())

        self.client.force_authenticate(user=self.viewer)
        history = self.client.get(f"/api/projects/{self.project.id}/chat/")
        self.assertEqual(history.data["messages"][-1]["kind"], "image")
        image = self.client.get("/api/" + response.data["meta"]["image_url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(b"".join(image.streaming_content), original_path.read_bytes())
        image.close()
        thumbnail = self.client.get("/api/" + response.data["meta"]["thumbnail_url"])
        self.assertEqual(thumbnail.status_code, 200)
        self.assertEqual(thumbnail["Content-Type"], "image/jpeg")
        thumbnail.close()
        self.assertEqual(self.client.post(url, {"image": self._image_file()}, format="multipart").status_code, 403)
        self.assertEqual(self.client.post(f"/api/projects/{self.project.id}/chat/{message.id}/analyze/").status_code, 403)

        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.get("/api/" + response.data["meta"]["image_url"]).status_code, 403)
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.post(url, {"image": SimpleUploadedFile("falso.png", b"no es imagen")}, format="multipart").status_code, 400)
        self.assertEqual(self.client.post(url, {"image": SimpleUploadedFile("grande.png", b"x" * (8 * 1024 * 1024 + 1))}, format="multipart").status_code, 400)
        message.delete()
        self.assertFalse(original_path.exists())

    def test_analisis_de_imagen_reutiliza_vision_y_cache(self):
        self._private_images()
        self.client.force_authenticate(user=self.editor)
        uploaded = self.client.post(f"/api/projects/{self.project.id}/chat/images/", {"image": self._image_file()}, format="multipart")
        self.assertEqual(uploaded.status_code, 201)
        analyze_url = f"/api/projects/{self.project.id}/chat/{uploaded.data['id']}/analyze/"
        classes = '{"classes":[{"name":"Paciente","is_abstract":false,"attributes":[],"methods":[]},{"name":"Persona","is_abstract":true,"attributes":[],"methods":[]}]}'
        relations = '{"relations":[{"source":"Paciente","target":"Persona","relation_type":"inheritance","source_multiplicity":"","target_multiplicity":"","label":""}]}'
        with patch("apps.ai_core.views.llm.vision", side_effect=[classes, relations]) as vision:
            result = self.client.post(analyze_url)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(len(result.data["nodes"]), 2)
            self.assertEqual(result.data["edges"][0]["data"]["relation_type"], "inheritance")
            self.assertEqual(self.client.post(analyze_url).data["nodes"], result.data["nodes"])
            self.assertEqual(vision.call_count, 2)
        self.project.refresh_from_db()
        self.assertEqual(self.project.datos_diagrama, {})

    def test_imagen_se_difunde_a_dos_clientes(self):
        self._private_images()
        async_to_sync(self._image_websocket_scenario)()

    async def _image_websocket_scenario(self):
        from asgiref.sync import sync_to_async

        async def connect(user):
            client = WebsocketCommunicator(DiagramConsumer.as_asgi(), f"/ws/diagram/{self.project.id}/")
            client.scope["user"] = user
            client.scope["url_route"] = {"kwargs": {"diagram_id": str(self.project.id)}}
            accepted, _ = await client.connect()
            self.assertTrue(accepted)
            return client

        owner = await connect(self.owner)
        await owner.receive_json_from()
        viewer = await connect(self.viewer)
        await owner.receive_json_from()
        await viewer.receive_json_from()

        def upload():
            client = APIClient()
            client.force_authenticate(user=self.owner)
            return client.post(f"/api/projects/{self.project.id}/chat/images/",
                               {"image": self._image_file()}, format="multipart")

        response = await sync_to_async(upload, thread_sensitive=True)()
        self.assertEqual(response.status_code, 201)
        for client in (owner, viewer):
            event = await client.receive_json_from()
            self.assertEqual(event["type"], "chat_message")
            self.assertEqual(event["message"]["kind"], "image")
            self.assertEqual(event["message"]["id"], response.data["id"])
        await viewer.disconnect()
        await owner.disconnect()

    def test_websocket_persistencia_difusion_y_rechazos(self):
        async_to_sync(self._websocket_scenario)()
        self.assertEqual(list(ChatMessage.objects.filter(project=self.project).values_list("content", flat=True)), ["Hola equipo"])

    async def _websocket_scenario(self):
        async def connect(user):
            client = WebsocketCommunicator(DiagramConsumer.as_asgi(), f"/ws/diagram/{self.project.id}/")
            client.scope["user"] = user
            client.scope["url_route"] = {"kwargs": {"diagram_id": str(self.project.id)}}
            accepted, _ = await client.connect()
            self.assertTrue(accepted)
            return client

        owner = await connect(self.owner)
        await owner.receive_json_from()  # user_join propio
        editor = await connect(self.editor)
        await owner.receive_json_from()  # user_join editor
        await editor.receive_json_from()  # user_join propio
        viewer = await connect(self.viewer)
        await owner.receive_json_from()
        await editor.receive_json_from()
        await viewer.receive_json_from()

        await owner.send_json_to({"type": "chat_message", "content": "  Hola equipo  "})
        for client in (owner, editor, viewer):
            event = await client.receive_json_from()
            self.assertEqual(event["type"], "chat_message")
            self.assertEqual(event["message"]["content"], "Hola equipo")
            self.assertEqual(event["message"]["username"], "owner")
        await viewer.send_json_to({"type": "chat_message", "content": "@ia No permitido"})
        self.assertEqual((await viewer.receive_json_from())["detail"], "Solo lectura")
        for content in ("   ", "x" * 2001):
            await editor.send_json_to({"type": "chat_message", "content": content})
            self.assertEqual((await editor.receive_json_from())["type"], "chat_error")
        for client in (viewer, editor, owner):
            await client.disconnect()

    def test_mencion_y_configuracion_solo_dueño(self):
        self.assertTrue(has_mention("Hola @IA, revisa esto"))
        self.assertFalse(has_mention("hola@iax"))
        url = f"/api/projects/{self.project.id}/ai-settings/"
        self.client.force_authenticate(user=self.viewer)
        self.assertEqual(self.client.get(url).data["mode"], "advisor")
        self.assertEqual(self.client.patch(url, {"mode": "proposer"}, format="json").status_code, 403)
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.patch(url, {"mode": "proposer", "persona": "moderator"}, format="json").status_code, 200)
        self.assertEqual(ProjectAISettings.objects.get(project=self.project).persona, "moderator")

    def test_contexto_individual_y_modo_asesor(self):
        ChatMessage.objects.create(project=self.project, author=self.editor, content="@ia pregunta ajena")
        ChatMessage.objects.create(project=self.project, author=self.owner, content="@ia mi primera pregunta")
        ChatMessage.objects.create(project=self.project, is_ai=True, reply_to_user=self.owner, content="Respuesta propia")
        current = ChatMessage.objects.create(project=self.project, author=self.owner, content="@ia agrega Factura")
        _, _, mode, persona, individual, room = async_to_sync(_context)(self.project.id, self.owner.id, current.id)
        prompt = _prompt("owner", "owner", "agrega Factura", {}, persona, mode, individual, room)
        own_section = prompt.split("Últimos intercambios individuales:")[1].split("Mensajes recientes de la sala:")[0]
        self.assertIn("Te consulta owner (rol owner)", prompt)
        self.assertIn("mi primera pregunta", own_section)
        self.assertIn("Respuesta propia", own_section)
        self.assertNotIn("pregunta ajena", own_section)

        class Layer:
            def __init__(self):
                self.events = []

            async def group_send(self, group, event):
                self.events.append(event)

        layer = Layer()
        response = '{"reply":"Agregué la clase","updates":[{"action":"add_class","name":"Factura"}]}'
        with patch("apps.chat.ai_worker.llm.chat", return_value=response) as chat:
            async_to_sync(_answer)(self.project.id, self.owner.id, "owner", "owner", current.id, layer)
        self.assertIn("Te consulta owner", chat.call_args.args[0][0]["content"])
        answer = ChatMessage.objects.filter(is_ai=True).order_by("-id").first()
        self.assertEqual(answer.kind, "text")
        self.assertEqual(answer.meta, {})
        self.assertEqual(answer.reply_to_user_id, self.owner.id)
        self.assertIn("no se aplicaron cambios", answer.content)

    def test_cola_ordenada_y_un_pedido_pendiente_por_usuario(self):
        async_to_sync(self._queue_scenario)()

    async def _queue_scenario(self):
        class Layer:
            async def group_send(self, group, event):
                pass

        started = asyncio.Event()
        release = asyncio.Event()
        order = []

        async def fake_answer(project_id, user_id, username, role, message_id, layer, diagram=None):
            order.append(username)
            if username == "owner":
                started.set()
                await release.wait()

        with patch("apps.chat.ai_worker._answer", side_effect=fake_answer):
            self.assertIsNone(enqueue(self.project.id, self.owner.id, "owner", "owner", 1, Layer()))
            await started.wait()
            self.assertEqual(enqueue(self.project.id, self.owner.id, "owner", "owner", 2, Layer()),
                             "Ya tienes una consulta en curso")
            self.assertIsNone(enqueue(self.project.id, self.editor.id, "editor", "editor", 3, Layer()))
            for extra in range(4):
                self.assertIsNone(enqueue(self.project.id, 100 + extra, f"extra{extra}", "editor", 4 + extra, Layer()))
            self.assertEqual(enqueue(self.project.id, 200, "sin_sitio", "editor", 9, Layer()),
                             "La IA está ocupada, intenta en un momento")
            release.set()
            await asyncio.sleep(0.05)
        self.assertEqual(order, ["owner", "editor", "extra0", "extra1", "extra2", "extra3"])

    def test_decision_atomica_y_resultado(self):
        message = ChatMessage.objects.create(project=self.project, is_ai=True, reply_to_user=self.editor,
                                             kind="proposal", content="Propongo agregar Factura",
                                             meta={"status": "pending", "updates": [{"action": "add_class", "name": "Factura"}]})
        _, error = decide(self.project.id, self.owner.id, "owner", message.id, "approve")
        self.assertIn("Solo quien solicitó", error)
        approved, error = decide(self.project.id, self.editor.id, "editor", message.id, "approve")
        self.assertIsNone(error)
        self.assertEqual(approved["meta"]["status"], "approved")
        _, error = decide(self.project.id, self.editor.id, "editor", message.id, "reject")
        self.assertIn("ya fue decidida", error)
        result, error = record_result(self.project.id, self.editor.id, "editor", message.id, 1, [])
        self.assertIsNone(error)
        self.assertEqual(result["meta"]["status"], "applied")
        _, error = record_result(self.project.id, self.editor.id, "editor", message.id, 1, [])
        self.assertIsNotNone(error)

    def test_modo_proponente_guarda_propuesta_pendiente(self):
        ProjectAISettings.objects.create(project=self.project, mode="proposer")
        current = ChatMessage.objects.create(project=self.project, author=self.editor, content="@ia agrega Factura")

        class Layer:
            async def group_send(self, group, event):
                pass

        response = '{"reply":"Ya agregué la clase","updates":[{"action":"add_class","name":"Factura"}]}'
        with patch("apps.chat.ai_worker.llm.chat", return_value=response):
            async_to_sync(_answer)(self.project.id, self.editor.id, "editor", "editor", current.id, Layer())
        answer = ChatMessage.objects.filter(is_ai=True).get()
        self.assertEqual(answer.kind, "proposal")
        self.assertEqual(answer.meta["status"], "pending")
        self.assertEqual(answer.meta["requested_by"], self.editor.id)
        self.assertIn("Propongo:", answer.content)
        self.assertNotIn("Ya agregué", answer.content)

    def test_json_roto_reintenta_y_recupera_reply(self):
        ProjectAISettings.objects.create(project=self.project, mode="proposer")
        current = ChatMessage.objects.create(project=self.project, author=self.owner, content="@ia qué clases faltan")

        class Layer:
            async def group_send(self, group, event):
                pass

        broken = '{"reply":"Revisa clases","updates:[}'
        still_broken = '{"reply":"Revisa relaciones","updates":[}'
        with patch("apps.chat.ai_worker.llm.chat", side_effect=[broken, still_broken]) as chat:
            async_to_sync(_answer)(self.project.id, self.owner.id, "owner", "owner", current.id, Layer())
        answer = ChatMessage.objects.filter(is_ai=True).get()
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(answer.kind, "text")
        self.assertEqual(answer.content, "Revisa relaciones")
        self.assertEqual(answer.meta, {})

    def test_respuesta_ilegible_se_guarda_como_error(self):
        ProjectAISettings.objects.create(project=self.project, mode="proposer")
        current = ChatMessage.objects.create(project=self.project, author=self.owner, content="@ia revisa el diseño")

        class Layer:
            async def group_send(self, group, event):
                pass

        with patch("apps.chat.ai_worker.llm.chat", side_effect=["texto roto", "sigue roto"]):
            async_to_sync(_answer)(self.project.id, self.owner.id, "owner", "owner", current.id, Layer())
        answer = ChatMessage.objects.filter(is_ai=True).get()
        self.assertEqual(answer.kind, "error")
        self.assertTrue(answer.meta["error"])
        self.assertIn("respuesta ilegible", answer.content)

    def test_errores_previos_no_contaminan_prompt(self):
        ChatMessage.objects.create(project=self.project, is_ai=True, reply_to_user=self.owner,
                                   content="ERROR MARCADO", kind="error", meta={"error": True})
        ChatMessage.objects.create(project=self.project, is_ai=True, reply_to_user=self.owner,
                                   content="No pude procesar la consulta. Intenta de nuevo.")
        ChatMessage.objects.create(project=self.project, is_ai=True, reply_to_user=self.owner, content="")
        current = ChatMessage.objects.create(project=self.project, author=self.owner, content="@ia pregunta nueva")
        diagram, _, mode, persona, individual, room = async_to_sync(_context)(self.project.id, self.owner.id, current.id)
        prompt = _prompt("owner", "owner", "pregunta nueva", diagram, persona, mode, individual, room)
        self.assertNotIn("ERROR MARCADO", prompt)
        self.assertNotIn("No pude procesar", prompt)

    def test_consejo_en_modo_proponente_no_crea_propuesta(self):
        ProjectAISettings.objects.create(project=self.project, mode="proposer")
        current = ChatMessage.objects.create(project=self.project, author=self.owner, content="@ia qué clases faltan")

        class Layer:
            async def group_send(self, group, event):
                pass

        with patch("apps.chat.ai_worker.llm.chat", return_value='{"reply":"Revisa si falta una clase de Servicio.","updates":[]}') as chat:
            async_to_sync(_answer)(self.project.id, self.owner.id, "owner", "owner", current.id, Layer())
        answer = ChatMessage.objects.filter(is_ai=True).get()
        self.assertEqual(answer.kind, "text")
        self.assertEqual(answer.content, "Revisa si falta una clase de Servicio.")
        self.assertIn("Preguntas de consejo", chat.call_args.args[0][0]["content"])

    def test_decision_websocket_informa_errores_al_remitente(self):
        message = ChatMessage.objects.create(project=self.project, is_ai=True, reply_to_user=self.editor,
                                             kind="proposal", content="Propongo agregar Factura",
                                             meta={"status": "pending", "updates": [{"action": "add_class", "name": "Factura"}]})
        async_to_sync(self._decision_scenario)(message.id)

    def test_relacionar_publica_tarjeta_y_omite_atributo_repetido(self):
        ProjectAISettings.objects.create(project=self.project, mode="proposer")
        diagram = {"nodes": [
            {"id": "m", "data": {"name": "Medico", "attributes": [{"id": "a", "name": "nombre"}]}},
            {"id": "p", "data": {"name": "Paciente", "attributes": []}}], "edges": []}
        self.project.datos_diagrama = diagram
        self.project.save(update_fields=["datos_diagrama"])

        class Layer:
            async def group_send(self, group, event):
                pass

        current = ChatMessage.objects.create(project=self.project, author=self.owner,
                                             content="@ia relaciona Medico con Paciente")
        response = '{"reply":"Propongo relación","updates":[{"action":"add_relation","source_class":"Medico","target_class":"Paciente","relation_type":"association"}]}'
        with patch("apps.chat.ai_worker.llm.chat", return_value=response):
            async_to_sync(_answer)(self.project.id, self.owner.id, "owner", "owner", current.id, Layer())
        answer = ChatMessage.objects.filter(is_ai=True).latest("id")
        self.assertEqual(answer.kind, "proposal")
        self.assertEqual(answer.meta["updates"][0]["action"], "add_relation")

        current = ChatMessage.objects.create(project=self.project, author=self.owner,
                                             content="@ia agrega nombre y licencia a Medico")
        response = '{"reply":"Propongo atributos","updates":[{"action":"add_attribute","class_name":"Medico","attributes":[{"name":"nombre","data_type":"String"},{"name":"licencia","data_type":"String"}]}]}'
        with patch("apps.chat.ai_worker.llm.chat", return_value=response):
            async_to_sync(_answer)(self.project.id, self.owner.id, "owner", "owner", current.id, Layer())
        answer = ChatMessage.objects.filter(is_ai=True).latest("id")
        self.assertEqual([item["attr_name"] for item in answer.meta["updates"]], ["licencia"])
        self.assertEqual(answer.meta["rejected"][0]["code"], "duplicate_attribute")
        self.assertIn("ya existían", answer.content)

    def test_promesa_sin_acciones_reintenta_y_pide_aclaracion(self):
        ProjectAISettings.objects.create(project=self.project, mode="proposer")
        current = ChatMessage.objects.create(project=self.project, author=self.owner,
                                             content="@ia relaciona Medico con Paciente")

        class Layer:
            async def group_send(self, group, event):
                pass

        response = '{"reply":"Propongo relacionarlos","updates":[]}'
        with patch("apps.chat.ai_worker.llm.chat", side_effect=[response, response]) as chat:
            async_to_sync(_answer)(self.project.id, self.owner.id, "owner", "owner", current.id, Layer())
        answer = ChatMessage.objects.filter(is_ai=True).get()
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(answer.kind, "text")
        self.assertIn("No pude convertir tu pedido", answer.content)
        self.assertNotIn("Propongo relacionarlos", answer.content)

    def test_consulta_adjunta_diagrama_actual(self):
        async_to_sync(self._diagram_scenario)()

    async def _diagram_scenario(self):
        client = WebsocketCommunicator(DiagramConsumer.as_asgi(), f"/ws/diagram/{self.project.id}/")
        client.scope["user"] = self.owner
        client.scope["url_route"] = {"kwargs": {"diagram_id": str(self.project.id)}}
        accepted, _ = await client.connect()
        self.assertTrue(accepted)
        await client.receive_json_from()
        diagram = {"nodes": [{"id": "m", "data": {"name": "Medico"}}], "edges": []}
        with patch("apps.realtime.consumers.enqueue", return_value=None) as enqueue_mock:
            await client.send_json_to({"type": "chat_message", "content": "@ia revisa Medico",
                                       "diagram": diagram})
            await client.receive_json_from()
            self.assertEqual(enqueue_mock.call_args.kwargs["diagram"], diagram)
            self.assertEqual(ROOM_DIAGRAMS[f"diagram_{self.project.id}"], diagram)
        await client.disconnect()

    async def _decision_scenario(self, message_id):
        async def connect(user):
            client = WebsocketCommunicator(DiagramConsumer.as_asgi(), f"/ws/diagram/{self.project.id}/")
            client.scope["user"] = user
            client.scope["url_route"] = {"kwargs": {"diagram_id": str(self.project.id)}}
            accepted, _ = await client.connect()
            self.assertTrue(accepted)
            return client

        owner = await connect(self.owner)
        await owner.receive_json_from()
        editor = await connect(self.editor)
        await owner.receive_json_from()
        await editor.receive_json_from()
        await owner.send_json_to({"type": "proposal_decision", "message_id": message_id, "decision": "approve"})
        self.assertEqual((await owner.receive_json_from())["type"], "chat_error")
        await editor.send_json_to({"type": "proposal_decision", "message_id": message_id, "decision": "approve"})
        for client in (owner, editor):
            self.assertEqual((await client.receive_json_from())["message"]["meta"]["status"], "approved")
        await editor.send_json_to({"type": "proposal_decision", "message_id": message_id, "decision": "reject"})
        self.assertEqual((await editor.receive_json_from())["type"], "chat_error")
        await editor.disconnect()
        await owner.disconnect()
