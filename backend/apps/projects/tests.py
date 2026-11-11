"""Pruebas del intercambio XMI UML y de la vista previa."""

import xml.etree.ElementTree as ET

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from apps.accounts.models import User
from .generators.xmi_generator import generate_xmi
from .generators.xmi_importer import parse_xmi_preview
from .generators.xmi_uml251 import generate_xmi_251, XMI, UML
from .models import Project, ProjectCollaborator


def sample_diagram():
    def node(key, name, x, y, **extra):
        return {"id": key, "type": "classNode", "position": {"x": x, "y": y}, "data": {"id": key, "name": name, "is_abstract": False, "attributes": [], "methods": [], **extra}}

    def edge(key, source, target, rel, source_mult="", target_mult=""):
        return {"id": key, "type": "umlEdge", "source": source, "target": target, "data": {"relation_type": rel, "sourceMultiplicity": source_mult, "targetMultiplicity": target_mult}}

    return {"nodes": [
        node("persona", "Persona", 21, 42, is_abstract=True, attributes=[{"id": "nombre", "name": "nombre", "data_type": "String", "visibility": "-"}], methods=[{"id": "saludar", "name": "saludar", "return_type": "String", "visibility": "+"}]),
        node("cliente", "Cliente", 310, 42),
        node("pedido", "Pedido", 310, 260),
        node("servicio", "Servicio", 610, 40, is_interface=True),
    ], "edges": [
        edge("hereda", "cliente", "persona", "inheritance"),
        edge("compone", "cliente", "pedido", "composition", "1", "1..*"),
        edge("agrega", "persona", "pedido", "aggregation"),
        edge("asocia", "persona", "servicio", "association", "1", "1..*"),
        edge("depende", "pedido", "servicio", "dependency"),
        edge("realiza", "cliente", "servicio", "realization"),
        edge("dirige", "pedido", "persona", "directed_association"),
    ]}


class XMITests(SimpleTestCase):
    def test_exportacion_referencias_y_namespaces(self):
        root = ET.fromstring(generate_xmi_251(sample_diagram(), "Proyecto & Uno"))
        self.assertEqual(root.tag, f"{{{XMI}}}XMI")
        self.assertIsNotNone(root.find(f"{{{UML}}}Model"))
        ids = [el.get(f"{{{XMI}}}id") for el in root.iter() if el.get(f"{{{XMI}}}id")]
        self.assertEqual(len(ids), len(set(ids)))
        refs = set(ids)
        for el in root.find(f"{{{UML}}}Model").iter():
            if el.get(f"{{{XMI}}}idref"):
                self.assertIn(el.get(f"{{{XMI}}}idref"), refs)
            for key in ("type", "general", "client", "supplier", "association"):
                if el.get(key):
                    self.assertIn(el.get(key), refs)
            for key in ("memberEnd", "navigableOwnedEnd"):
                for ref in el.get(key, "").split():
                    self.assertIn(ref, refs)

    def test_ida_y_vuelta(self):
        diagram = sample_diagram()
        parsed = parse_xmi_preview(generate_xmi_251(diagram, "Prueba"))
        actual_nodes = {n["data"]["name"]: n for n in parsed["nodes"]}
        self.assertEqual(set(actual_nodes), {n["data"]["name"] for n in diagram["nodes"]})
        self.assertTrue(actual_nodes["Persona"]["data"]["is_abstract"])
        self.assertTrue(actual_nodes["Servicio"]["data"]["is_interface"])
        self.assertEqual(actual_nodes["Persona"]["data"]["attributes"][0]["data_type"], "String")
        self.assertEqual(actual_nodes["Persona"]["data"]["methods"][0]["return_type"], "String")
        self.assertEqual(actual_nodes["Persona"]["position"], {"x": 21.0, "y": 42.0})
        relations = {e["data"]["relation_type"]: e for e in parsed["edges"]}
        self.assertEqual(set(relations), {"inheritance", "composition", "aggregation", "association", "dependency", "realization", "directed_association"})
        self.assertEqual(relations["composition"]["data"]["targetMultiplicity"], "1..*")
        self.assertEqual(relations["association"]["data"]["sourceMultiplicity"], "1")

    def test_xmi_21_existente(self):
        parsed = parse_xmi_preview(generate_xmi(sample_diagram(), "Legado"))
        self.assertEqual(len(parsed["nodes"]), 4)
        self.assertGreaterEqual(len(parsed["edges"]), 6)

    def test_enumeracion_y_clase_de_asociacion(self):
        diagram = sample_diagram()
        diagram["nodes"].append({"id": "estado", "type": "classNode", "position": {"x": 900, "y": 90}, "data": {"name": "Estado", "is_enum": True, "literals": ["Nuevo", "Cerrado"], "attributes": [], "methods": []}})
        diagram["nodes"].append({"id": "detalle", "type": "classNode", "position": {"x": 500, "y": 430}, "data": {"name": "Detalle", "attributes": [], "methods": []}})
        diagram["edges"][1]["data"]["associationClassId"] = "detalle"
        exported = generate_xmi_251(diagram, "Prueba")
        root = ET.fromstring(exported)
        ids = {el.get(f"{{{XMI}}}id") for el in root.iter() if el.get(f"{{{XMI}}}id")}
        for el in root.iter():
            if el.get("subject"):
                self.assertIn(el.get("subject"), ids)
        parsed = parse_xmi_preview(exported)
        by_name = {n["data"]["name"]: n for n in parsed["nodes"]}
        self.assertEqual(by_name["Estado"]["data"]["literals"], ["Nuevo", "Cerrado"])
        self.assertTrue(any(e["data"].get("associationClassId") == by_name["Detalle"]["id"] for e in parsed["edges"]))

    def test_namespace_241_y_layout_automatico(self):
        source = generate_xmi_251(sample_diagram(), "Prueba")
        source = source.replace("http://www.omg.org/spec/XMI/20131001", "http://www.omg.org/spec/XMI/20110701")
        source = source.replace("http://www.omg.org/spec/UML/20161101", "http://www.omg.org/spec/UML/20110701")
        root = ET.fromstring(source)
        for extension in list(root):
            if extension.tag.endswith("Extension"):
                root.remove(extension)
        parsed = parse_xmi_preview(ET.tostring(root))
        self.assertEqual(parsed["version"], "2.4.1")
        self.assertEqual(parsed["nodes"][0]["position"], {"x": 80, "y": 80})
        self.assertEqual(parsed["nodes"][1]["position"], {"x": 380, "y": 80})

    def test_estereotipo_y_relacion_de_clase_de_asociacion(self):
        diagram = sample_diagram()
        diagram["nodes"][0]["data"]["stereotype"] = "entity"
        diagram["edges"].append({"id": "assoc-class-visual", "source": "pedido", "target": "cliente", "type": "umlEdge", "data": {"relation_type": "association_class"}})
        parsed = parse_xmi_preview(generate_xmi_251(diagram, "Prueba"))
        self.assertEqual(parsed["nodes"][0]["data"]["stereotype"], "entity")
        self.assertTrue(any(edge["data"]["relation_type"] == "association_class" for edge in parsed["edges"]))

    def test_referencias_href_y_extremos_owned_attribute(self):
        source = b'''<?xml version="1.0"?>
        <xmi:XMI xmlns:xmi="http://www.omg.org/spec/XMI/20131001" xmlns:uml="http://www.omg.org/spec/UML/20161101">
          <uml:Model xmi:id="model" name="M"><packagedElement xmi:type="uml:Package" xmi:id="pkg" name="P">
            <packagedElement xmi:type="uml:Class" xmi:id="A" name="A">
              <ownedAttribute xmi:type="uml:Property" xmi:id="endA" association="assoc"><type href="other.uml#A"/></ownedAttribute>
            </packagedElement>
            <packagedElement xmi:type="uml:Class" xmi:id="B" name="B"/>
            <packagedElement xmi:type="uml:Association" xmi:id="assoc" memberEnd="endA endB">
              <ownedEnd xmi:type="uml:Property" xmi:id="endB" type="B"><lowerValue value="1"/><upperValue value="*"/></ownedEnd>
            </packagedElement>
          </packagedElement></uml:Model>
        </xmi:XMI>'''
        parsed = parse_xmi_preview(source)
        self.assertEqual(len(parsed["nodes"]), 2)
        self.assertEqual(len(parsed["edges"]), 1)
        self.assertEqual(parsed["edges"][0]["data"]["targetMultiplicity"], "1..*")

    def test_seguridad_y_desconocidos(self):
        with self.assertRaisesRegex(ValueError, "DOCTYPE"):
            parse_xmi_preview(b'<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><xmi:XMI/>')
        with self.assertRaisesRegex(ValueError, "5 MB"):
            parse_xmi_preview(b"x" * (5 * 1024 * 1024 + 1))
        source = generate_xmi_251(sample_diagram(), "Prueba")
        source = source.replace("</packagedElement>", '<packagedElement xmi:type="uml:Signal" xmi:id="extra" name="S" /></packagedElement>', 1)
        parsed = parse_xmi_preview(source)
        self.assertEqual(len(parsed["nodes"]), 4)
        self.assertTrue(any("Signal" in warning for warning in parsed["warnings"]))


class XMIPreviewAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com", username="owner", password="clave")
        self.viewer = User.objects.create_user(email="viewer@example.com", username="viewer", password="clave")
        self.outsider = User.objects.create_user(email="other@example.com", username="other", password="clave")
        self.project = Project.objects.create(name="Prueba", owner=self.owner, datos_diagrama=sample_diagram())
        ProjectCollaborator.objects.create(project=self.project, user=self.viewer, role="viewer")

    def test_preview_sin_guardar_y_permisos(self):
        data = generate_xmi_251(sample_diagram(), "Prueba").encode()
        url = f"/api/projects/{self.project.id}/xmi/preview/"
        self.client.force_authenticate(self.owner)
        result = self.client.post(url, {"file": SimpleUploadedFile("test.xmi", data)}, format="multipart")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["classes"], 4)
        self.project.refresh_from_db()
        self.assertEqual(self.project.datos_diagrama, sample_diagram())
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.post(url, {"file": SimpleUploadedFile("test.xmi", data)}, format="multipart").status_code, 403)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.post(url, {"file": SimpleUploadedFile("test.xmi", data)}, format="multipart").status_code, 403)

    def test_selector_de_version(self):
        self.client.force_authenticate(self.viewer)
        base = f"/api/projects/{self.project.id}/xmi/"
        self.assertIn("uml251.xmi", self.client.get(base)["Content-Disposition"])
        self.assertIn("uml21.xmi", self.client.get(base + "?version=2.1")["Content-Disposition"])

    def test_archivo_excesivo_y_doctype(self):
        self.client.force_authenticate(self.owner)
        url = f"/api/projects/{self.project.id}/xmi/preview/"
        huge = SimpleUploadedFile("huge.xmi", b"x" * (5 * 1024 * 1024 + 1))
        self.assertEqual(self.client.post(url, {"file": huge}, format="multipart").status_code, 400)
        hostile = SimpleUploadedFile("bad.xmi", b'<!DOCTYPE foo [<!ENTITY x "y">]><xmi:XMI/>')
        self.assertEqual(self.client.post(url, {"file": hostile}, format="multipart").status_code, 400)
