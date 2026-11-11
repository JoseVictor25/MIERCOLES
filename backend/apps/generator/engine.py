"""
SpringGenerator — Motor de generación de código Spring Boot en 5 capas.
Traduce el modelo conceptual del diagrama UML a código Java/Spring Boot empaquetado en .zip.
"""

import io
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Dict, Any, List
import jinja2

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
logger = logging.getLogger(__name__)


def to_pascal_case(text: str) -> str:
    """Convierte texto a PascalCase válido para nombres de clases Java."""
    if not text:
        return "ClaseSinNombre"
    # Reemplazar caracteres no alfanuméricos
    cleaned = re.sub(r"[^a-zA-Z0-9_]", " ", str(text).strip()).replace("_", " ")
    words = cleaned.split()
    if not words:
        return "ClaseGenerada"
    result = "".join(w[:1].upper() + w[1:] for w in words)
    # Si empieza con número, anteponer 'C'
    if result[0].isdigit():
        result = "C" + result
    return result


def to_camel_case(text: str) -> str:
    """Convierte texto a camelCase válido para nombres de atributos/métodos Java."""
    pascal = to_pascal_case(text)
    if not pascal:
        return "atributo"
    return pascal[:1].lower() + pascal[1:]


def to_snake_case(text: str) -> str:
    """Convierte texto a snake_case para nombres de tablas y columnas de base de datos."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", text)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    s3 = re.sub(r"[^a-zA-Z0-9_]", "_", s2)
    return re.sub(r"_+", "_", s3).strip("_").lower()


def to_plural_slug(text: str) -> str:
    """Genera la ruta plural para el endpoint REST (ej. Cliente -> clientes)."""
    parts = to_snake_case(text).split("_")
    last = parts[-1]
    parts[-1] = last + ("es" if last.endswith(("s", "x", "z")) else "s")
    return "-".join(parts)


def map_java_type(uml_type: str) -> str:
    """Mapea tipos UML a tipos de datos estándar de Java."""
    if not uml_type:
        return "String"
    t = uml_type.strip().lower()

    if t in ("string", "str", "texto", "varchar", "char", "text"):
        return "String"
    elif t in ("int", "integer", "entero"):
        return "Integer"
    elif t in ("long", "bigint"):
        return "Long"
    elif t in ("double", "float", "decimal", "real", "float8"):
        return "Double"
    elif t in ("boolean", "bool", "booleano"):
        return "Boolean"
    elif t in ("date", "fecha", "localdate"):
        return "LocalDate"
    elif t in ("datetime", "timestamp", "localdatetime", "fechahora"):
        return "LocalDateTime"
    elif t in ("bigdecimal", "dinero", "money", "precio"):
        return "BigDecimal"
    elif t in ("void", "vacio"):
        return "void"
    else:
        # Si es un nombre de clase existente en PascalCase, conservarlo
        return to_pascal_case(uml_type)


class SpringGenerator:
    """
    Parsea `datos_diagrama` y genera un proyecto Spring Boot empaquetado en .zip.
    """

    def __init__(self, datos_diagrama: Dict[str, Any], project_name: str,
                 group_id: str = "com.example", artifact_id: str = "backend",
                 include_ai_docs: bool = False):
        self.raw_nodes = datos_diagrama.get("nodes", []) if datos_diagrama else []
        self.raw_edges = datos_diagrama.get("edges", []) if datos_diagrama else []
        self.project_name = project_name or "ProyectoUML"
        self.group_id = re.sub(r"[^a-z0-9_.]", "", group_id.lower().strip()) or "com.example"
        self.artifact_id = to_snake_case(artifact_id) or "backend"
        self.base_package = f"{self.group_id}.{self.artifact_id.replace('-', '_')}"
        self.database_name = f"{self.artifact_id}_db"
        self.include_ai_docs = include_ai_docs
        self.warnings = []

        # Inicializar Jinja2
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def parse_model(self) -> List[Dict[str, Any]]:
        """
        Interpreta los nodos y aristas para construir la estructura de entidades.
        """
        entities_by_id = {}
        entities_by_name = {}

        # 1. Procesar clases (nodos)
        for node in self.raw_nodes:
            node_id = str(node.get("id"))
            data = node.get("data", {})
            raw_name = data.get("name") or f"Clase_{len(entities_by_id) + 1}"
            class_name = to_pascal_case(raw_name)

            # Evitar nombres duplicados
            base_name = class_name
            counter = 2
            while class_name in entities_by_name:
                class_name = f"{base_name}{counter}"
                counter += 1

            raw_attributes = data.get("attributes", [])
            attributes = []
            used_fields = {"id"}
            has_custom_id = False
            has_dates = False
            has_datetimes = False
            has_bigdecimals = False

            for attr in raw_attributes:
                attr_name_raw = attr.get("name") or "campo"
                attr_field = to_camel_case(attr_name_raw)
                attr_type_raw = attr.get("data_type") or "String"
                java_type = map_java_type(attr_type_raw)

                if java_type == "LocalDate":
                    has_dates = True
                elif java_type == "LocalDateTime":
                    has_datetimes = True
                elif java_type == "BigDecimal":
                    has_bigdecimals = True

                is_id = attr_field.lower() in ("id", "codigo", f"id{class_name.lower()}")
                if is_id:
                    # Marcar que el modelo define un ID pero NO incluirlo en los atributos:
                    # el template siempre genera un @Id Long id auto-incremental.
                    # Incluirlo aquí causaría un campo duplicado en la entidad generada.
                    has_custom_id = True
                    continue

                base_field = attr_field
                suffix = 2
                while attr_field in used_fields:
                    attr_field = f"{base_field}{suffix}"
                    suffix += 1
                used_fields.add(attr_field)

                is_bool = java_type == "Boolean"
                getter_prefix = "is" if is_bool and not attr_field.startswith("is") else "get"
                capitalized_field = attr_field[:1].upper() + attr_field[1:]

                attributes.append({
                    "name": attr_name_raw,
                    "field_name": attr_field,
                    "java_type": java_type,
                    "column_name": to_snake_case(attr_field),
                    "getter_name": f"{getter_prefix}{capitalized_field}",
                    "setter_name": f"set{capitalized_field}",
                    "is_id": is_id,
                    "is_generated": is_id and java_type in ("Long", "Integer"),
                })

            entity = {
                "id": node_id,
                "name": class_name,
                "table_name": to_snake_case(class_name),
                "url_path": to_plural_slug(class_name),
                "attributes": attributes,
                "relationships": [],
                "parent_class": None,
                "is_parent_in_inheritance": False,
                "has_custom_id": has_custom_id,
                "has_dates": has_dates,
                "has_datetimes": has_datetimes,
                "has_bigdecimals": has_bigdecimals,
                "has_collections": False,
                "used_fields": used_fields,
            }

            entities_by_id[node_id] = entity
            entities_by_name[class_name] = entity

        def unique_field(entity, base, reserve_fk=False):
            base = to_camel_case(base)
            name, number = base, 2
            while name in entity["used_fields"] or (reserve_fk and (
                f"{name}Id" in entity["used_fields"] or f"{name}Nombre" in entity["used_fields"]
            )):
                name, number = f"{base}{number}", number + 1
            entity["used_fields"].add(name)
            if reserve_fk:
                entity["used_fields"].update((f"{name}Id", f"{name}Nombre"))
            return name

        def plural_field(name):
            base = to_camel_case(name)
            return base + ("es" if base.endswith(("s", "x", "z")) else "s")

        def add_to_one(owner, target, base=None):
            field = unique_field(owner, base or target["name"], reserve_fk=True)
            cap = field[:1].upper() + field[1:]
            owner["relationships"].append({
                "type": "ManyToOne", "target_class": target["name"],
                "field_name": field, "repo_field": f"{field}Repository",
                "join_column": f"{to_snake_case(field)}_id",
                "fk_id_field": f"{field}Id", "fk_label_field": f"{field}Nombre",
                "fk_getter_name": f"get{cap}Id", "fk_setter_name": f"set{cap}Id",
                "fk_label_setter_name": f"set{cap}Nombre",
                "is_collection": False, "getter_name": f"get{cap}", "setter_name": f"set{cap}",
            })
            return field

        def add_to_many(owner, target, mapped_by, base=None):
            field = unique_field(owner, base or plural_field(target["name"]))
            cap = field[:1].upper() + field[1:]
            owner["relationships"].append({
                "type": "OneToMany", "target_class": target["name"],
                "field_name": field, "mapped_by": mapped_by, "is_collection": True,
                "getter_name": f"get{cap}", "setter_name": f"set{cap}",
            })
            owner["has_collections"] = True

        self.warnings = []
        for edge in self.raw_edges:
            source_id, target_id = str(edge.get("source")), str(edge.get("target"))
            if source_id not in entities_by_id or target_id not in entities_by_id:
                continue
            source, target = entities_by_id[source_id], entities_by_id[target_id]
            data = edge.get("data") or {}
            rel_type = (data.get("relation_type") or "association").lower()
            source_role, target_role = data.get("sourceRole"), data.get("targetRole")
            if source_id == target_id and (rel_type == "inheritance" or not (source_role and target_role)):
                warning = f"Arista {edge.get('id', '?')}: autorrelacion de {source['name']} omitida; indique sourceRole y targetRole."
                self.warnings.append(warning)
                logger.warning(warning)
                continue

            if rel_type == "inheritance":
                source["parent_class"] = target["name"]
                target["is_parent_in_inheritance"] = True
                continue

            assoc_id = str(data.get("associationClassId") or "")
            assoc = entities_by_id.get(assoc_id)
            if assoc and assoc_id not in (source_id, target_id):
                add_to_one(assoc, source, source_role)
                add_to_one(assoc, target, target_role)
                continue

            source_many = "*" in str(data.get("sourceMultiplicity") or "")
            target_many = "*" in str(data.get("targetMultiplicity") or "")
            if source_many and target_many:
                field = unique_field(source, target_role or plural_field(target["name"]))
                cap = field[:1].upper() + field[1:]
                source["relationships"].append({
                    "type": "ManyToMany", "target_class": target["name"],
                    "field_name": field, "join_table": f"{source['table_name']}_{target['table_name']}",
                    "join_column": f"{source['table_name']}_id",
                    "inverse_join_column": f"{target['table_name']}_id",
                    "is_collection": True, "getter_name": f"get{cap}", "setter_name": f"set{cap}",
                })
                source["has_collections"] = True
            elif target_many or rel_type in ("composition", "aggregation"):
                many_field = add_to_one(target, source, source_role)
                add_to_many(source, target, many_field, target_role)
            elif source_many:
                many_field = add_to_one(source, target, target_role)
                add_to_many(target, source, many_field, source_role)
            else:
                add_to_one(source, target, target_role)

        def resolve_attributes(entity, visiting=None):
            """Reúne atributos de toda la herencia; la clase hija prevalece si repite un nombre."""
            visiting = set() if visiting is None else visiting
            if entity["name"] in visiting:
                return list(entity["attributes"])
            parent = entities_by_name.get(entity["parent_class"])
            inherited = resolve_attributes(parent, visiting | {entity["name"]}) if parent else []
            fields = {attr["field_name"]: attr for attr in inherited}
            fields.update((attr["field_name"], attr) for attr in entity["attributes"])
            return list(fields.values())

        for entity in entities_by_id.values():
            entity["all_attributes"] = resolve_attributes(entity)
            for java_type, flag in (("LocalDate", "has_dates"),
                                    ("LocalDateTime", "has_datetimes"),
                                    ("BigDecimal", "has_bigdecimals")):
                entity[flag] = any(attr["java_type"] == java_type
                                   for attr in entity["all_attributes"])
        for entity in entities_by_id.values():
            for rel in entity["relationships"]:
                if rel["type"] not in ("ManyToOne", "OneToOne"):
                    continue
                target = entities_by_name[rel["target_class"]]
                label = next((attr for attr in target["all_attributes"]
                              if attr["field_name"].lower() == "nombre"), None)
                rel["fk_label_getter_name"] = label["getter_name"] if label else None

        return list(entities_by_id.values())

    def generate_zip_bytes(self) -> bytes:
        """
        Ejecuta la generación de plantillas y retorna los bytes del archivo .zip.
        """
        entities = self.parse_model()

        if self.include_ai_docs:
            from apps.projects.generators.ai_docs import generate_ai_docs_for_class
            raw_by_id = {str(node.get("id")): node.get("data") or {} for node in self.raw_nodes}
            for entity in entities:
                raw = raw_by_id.get(entity["id"], {})
                attrs = [{"name": a.get("name"), "type": a.get("data_type")} for a in raw.get("attributes", [])]
                methods = [{"name": m.get("name"), "return_type": m.get("return_type")} for m in raw.get("methods", [])]
                try:
                    entity["ai_docs"] = generate_ai_docs_for_class(entity["name"], attrs, methods, self.project_name)
                except Exception as exc:
                    entity["ai_docs"] = {}
                    self.warnings.append(f"JavaDoc asistido omitido para {entity['name']}: {exc}")
                if not entity["ai_docs"] and not any("JavaDoc asistido omitido" in warning and entity["name"] in warning for warning in self.warnings):
                    self.warnings.append(f"JavaDoc asistido omitido para {entity['name']}: la IA local no respondió o devolvió datos inválidos.")

        # Si el modelo no tiene clases, crear una clase de ejemplo
        if not entities:
            entities = [{
                "id": "sample-1",
                "name": "Ejemplo",
                "table_name": "ejemplo",
                "url_path": "ejemplos",
                "attributes": [
                    {
                        "name": "nombre",
                        "field_name": "nombre",
                        "java_type": "String",
                        "column_name": "nombre",
                        "getter_name": "getNombre",
                        "setter_name": "setNombre",
                        "is_id": False,
                        "is_generated": False,
                    }
                ],
                "all_attributes": [],
                "relationships": [],
                "parent_class": None,
                "is_parent_in_inheritance": False,
                "has_custom_id": False,
                "has_dates": False,
                "has_datetimes": False,
                "has_bigdecimals": False,
                "has_collections": False,
                "ai_docs": {},
            }]
            entities[0]["all_attributes"] = entities[0]["attributes"]

        package_path = self.base_package.replace(".", "/")
        root_dir = f"{self.artifact_id}"

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            context_common = {
                "group_id": self.group_id,
                "artifact_id": self.artifact_id,
                "project_name": self.project_name,
                "base_package": self.base_package,
                "database_name": self.database_name,
                "entities": entities,
                "warnings": self.warnings,
                "include_ai_docs": self.include_ai_docs,
            }

            # 1. pom.xml
            pom_content = self.jinja_env.get_template("pom.xml.j2").render(context_common)
            zf.writestr(f"{root_dir}/pom.xml", pom_content)

            # 2. application.properties
            app_props = self.jinja_env.get_template("application.properties.j2").render(context_common)
            zf.writestr(f"{root_dir}/src/main/resources/application.properties", app_props)

            # 3. Application.java
            main_app = self.jinja_env.get_template("Application.java.j2").render(context_common)
            zf.writestr(f"{root_dir}/src/main/java/{package_path}/Application.java", main_app)

            # 4. README.md
            readme = self.jinja_env.get_template("README.md.j2").render(context_common)
            zf.writestr(f"{root_dir}/README.md", readme)

            # 5. Capas para cada entidad
            for entity in entities:
                ctx_entity = {**context_common, "entity": entity}

                # Capa 1: Entity
                entity_src = self.jinja_env.get_template("entity.java.j2").render(ctx_entity)
                zf.writestr(f"{root_dir}/src/main/java/{package_path}/entity/{entity['name']}.java", entity_src)

                # Capa 2: DTOs (Request y Response)
                dto_req = self.jinja_env.get_template("dto_request.java.j2").render(ctx_entity)
                zf.writestr(f"{root_dir}/src/main/java/{package_path}/dto/{entity['name']}RequestDTO.java", dto_req)

                dto_res = self.jinja_env.get_template("dto_response.java.j2").render(ctx_entity)
                zf.writestr(f"{root_dir}/src/main/java/{package_path}/dto/{entity['name']}ResponseDTO.java", dto_res)

                # Capa 3: Mapper
                mapper_src = self.jinja_env.get_template("mapper.java.j2").render(ctx_entity)
                zf.writestr(f"{root_dir}/src/main/java/{package_path}/mapper/{entity['name']}Mapper.java", mapper_src)

                # Capa 4: Repository
                repo_src = self.jinja_env.get_template("repository.java.j2").render(ctx_entity)
                zf.writestr(f"{root_dir}/src/main/java/{package_path}/repository/{entity['name']}Repository.java", repo_src)

                # Capa 5: Service e Implementación
                service_src = self.jinja_env.get_template("service.java.j2").render(ctx_entity)
                zf.writestr(f"{root_dir}/src/main/java/{package_path}/service/{entity['name']}Service.java", service_src)

                impl_src = self.jinja_env.get_template("service_impl.java.j2").render(ctx_entity)
                zf.writestr(f"{root_dir}/src/main/java/{package_path}/service/impl/{entity['name']}ServiceImpl.java", impl_src)

                # Capa 6: Controller
                ctrl_src = self.jinja_env.get_template("controller.java.j2").render(ctx_entity)
                zf.writestr(f"{root_dir}/src/main/java/{package_path}/controller/{entity['name']}Controller.java", ctrl_src)

        return zip_buffer.getvalue()
