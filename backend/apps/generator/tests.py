import io
import re
import zipfile
from unittest.mock import patch

from django.test import SimpleTestCase

from .engine import SpringGenerator


def sample_diagram():
    classes = [
        ("persona", "Persona", [("ci", "int"), ("nombre", "String")]),
        ("cliente", "Cliente", [("correo", "String")]),
        ("pedido", "Pedido", [("fecha", "date")]),
        ("producto", "Producto", [("nombre", "String"), ("precio", "float")]),
        ("union", "pedido_producto", [("cantidad", "int")]),
    ]
    nodes = [
        {"id": node_id, "type": "classNode", "data": {
            "name": name,
            "attributes": [{"name": field, "data_type": field_type} for field, field_type in attrs],
            "methods": [],
        }}
        for node_id, name, attrs in classes
    ]
    edges = [
        {"id": "herencia", "source": "cliente", "target": "persona",
         "data": {"relation_type": "inheritance"}},
        {"id": "uno-a-muchos", "source": "cliente", "target": "pedido",
         "data": {"relation_type": "association", "sourceMultiplicity": "1", "targetMultiplicity": "*"}},
        {"id": "muchos-a-muchos", "source": "pedido", "target": "producto",
         "data": {"relation_type": "association", "sourceMultiplicity": "*", "targetMultiplicity": "*",
                  "associationClassId": "union"}},
    ]
    return {"nodes": nodes, "edges": edges}


def generated_files(diagram, **options):
    content = SpringGenerator(diagram, "Ejemplo", "com.example", "ejemplo", **options).generate_zip_bytes()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return {name: archive.read(name).decode("utf-8") for name in archive.namelist()}


class SpringGeneratorRegressionTests(SimpleTestCase):
    def test_inheritance_cardinalities_and_association_class(self):
        files = generated_files(sample_diagram())
        java = {path: content for path, content in files.items() if path.endswith(".java")}

        persona = next(content for path, content in java.items() if path.endswith("/entity/Persona.java"))
        cliente = next(content for path, content in java.items() if path.endswith("/entity/Cliente.java"))
        pedido = next(content for path, content in java.items() if path.endswith("/entity/Pedido.java"))
        producto = next(content for path, content in java.items() if path.endswith("/entity/Producto.java"))
        union = next(content for path, content in java.items() if path.endswith("/entity/PedidoProducto.java"))

        self.assertIn("@Inheritance(strategy = InheritanceType.JOINED)", persona)
        self.assertIn("class Cliente extends Persona", cliente)
        self.assertIn('mappedBy = "cliente"', cliente)
        self.assertIn("private List<Pedido> pedidos", cliente)
        self.assertIn('@JoinColumn(name = "cliente_id")', pedido)
        self.assertIn("private Cliente cliente", pedido)
        self.assertIn('@Table(name = "pedido_producto")', union)
        self.assertIn('@JoinColumn(name = "pedido_id")', union)
        self.assertIn('@JoinColumn(name = "producto_id")', union)
        self.assertIn("private Integer cantidad", union)
        self.assertNotIn("@ManyToMany", pedido)
        self.assertNotIn("@ManyToMany", producto)
        self.assertIn('"/api/pedido-productos"', next(
            content for path, content in java.items() if path.endswith("/controller/PedidoProductoController.java")))

        for path, content in java.items():
            if "/entity/" not in path:
                continue
            fields = re.findall(r"private\s+(?:List<\w+>|\w+)\s+(\w+)\s*[;=]", content)
            self.assertEqual(len(fields), len(set(fields)), path)

    def test_ambiguous_self_edges_are_reported_and_named_self_edges_are_unique(self):
        diagram = sample_diagram()
        diagram["edges"].append({"id": "sin-roles", "source": "producto", "target": "producto", "data": {}})
        diagram["edges"].extend([
            {"id": f"con-roles-{n}", "source": "persona", "target": "persona",
             "data": {"sourceRole": "padre", "targetRole": "hijo"}}
            for n in (1, 2)
        ])
        with self.assertLogs("apps.generator.engine", level="WARNING") as logs:
            files = generated_files(diagram)
        self.assertIn("sin-roles", logs.output[0])
        self.assertIn("sin-roles", files["ejemplo/README.md"])
        persona = next(content for path, content in files.items() if path.endswith("/entity/Persona.java"))
        self.assertIn("private Persona hijo;", persona)
        self.assertIn("private Persona hijo2;", persona)
        producto = next(content for path, content in files.items() if path.endswith("/entity/Producto.java"))
        self.assertNotIn("private Producto producto", producto)

    def test_parallel_relations_use_distinct_fields_and_columns(self):
        diagram = sample_diagram()
        diagram["edges"] = [
            {"id": f"paralela-{number}", "source": "pedido", "target": "producto",
             "data": {"relation_type": "association"}}
            for number in (1, 2)
        ]
        files = generated_files(diagram)
        pedido = next(content for path, content in files.items() if path.endswith("/entity/Pedido.java"))
        service = next(content for path, content in files.items() if path.endswith("/service/impl/PedidoServiceImpl.java"))
        self.assertIn("private Producto producto;", pedido)
        self.assertIn("private Producto producto2;", pedido)
        self.assertIn('@JoinColumn(name = "producto_id")', pedido)
        self.assertIn('@JoinColumn(name = "producto2_id")', pedido)
        self.assertIn("productoRepository", service)
        self.assertIn("producto2Repository", service)

    @patch("apps.projects.generators.ai_docs.generate_ai_docs_for_class")
    def test_optional_ai_documentation_is_preserved(self, generate_docs):
        generate_docs.return_value = {
            "class_javadoc": "/** JavaDoc IA */",
            "class_swagger": '@Tag(name = "IA")',
            "attributes_docs": {"ci": '/** Campo IA */\n    @Schema(description = "Documento")'},
        }
        files = generated_files(sample_diagram(), include_ai_docs=True)
        persona = next(content for path, content in files.items() if path.endswith("/entity/Persona.java"))
        controller = next(content for path, content in files.items() if path.endswith("/controller/PersonaController.java"))
        self.assertIn("/** JavaDoc IA */", persona)
        self.assertIn("@Schema", persona)
        self.assertIn('@Tag(name = "IA")', controller)
        self.assertIn("springdoc-openapi-starter-webmvc-ui", files["ejemplo/pom.xml"])
        self.assertEqual(generate_docs.call_count, 5)
