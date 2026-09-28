
import xml.etree.ElementTree as ET
from xml.dom import minidom
import datetime
import hashlib

def make_ea_id(prefix: str, raw_id: str) -> str:
    """
    Genera un ID determinista y seguro de longitud fija (máx 26 caracteres).
    Evita el error de Microsoft Access DAO.Field [3163] (límite de 40 caracteres en columnas de EA).
    """
    h = hashlib.md5(str(raw_id).encode('utf-8')).hexdigest()[:16].upper()
    return f"{prefix}_{h}"

def generate_xmi(diagram_data: dict, project_name: str) -> str:
    """
    Convierte el diagrama JSON (ReactFlow) al estándar OMG UML 2.1 con la extensión nativa
    de Enterprise Architect (extenderID 6.5).
    
    Garantiza:
      1. El paquete con el nombre del proyecto aparece en el Browser de Enterprise Architect.
      2. El diagrama de clases aparece creado automáticamente DENTRO del paquete.
      3. Todas las clases aparecen con sus atributos, tipos de datos, visibilidad y métodos.
      4. Al abrir el diagrama, todas las cajas están colocadas en sus coordenadas exactas
         y todas las relaciones (asociaciones, herencias, dependencias) están conectadas con sus flechas.
      5. Compatibilidad total de ida y vuelta (round-trip) con nuestro software.
    """
    clean_name = project_name.strip() if project_name else "Modelo"
    pkg_id = make_ea_id("EAPK", clean_name)
    diag_id = make_ea_id("EAID_DIAG", clean_name)
    
    nodes = diagram_data.get("nodes", [])
    edges = diagram_data.get("edges", [])
    
    # 1. Normalizar coordenadas (mínimo 80px para márgenes limpios y siempre positivas)
    raw_coords = []
    for node in nodes:
        pos = node.get("position", {"x": 80, "y": 80})
        raw_coords.append((int(pos.get("x", 80)), int(pos.get("y", 80))))
        
    min_x = min(p[0] for p in raw_coords) if raw_coords else 0
    min_y = min(p[1] for p in raw_coords) if raw_coords else 0
    
    # Mapeo de IDs limpios para Enterprise Architect (máximo 26 caracteres)
    id_map = {}
    name_map = {}
    for node in nodes:
        raw_id = str(node.get("id"))
        data = node.get("data", {})
        c_name = str(data.get("name", "Class")).strip() or "Class"
        ea_id = make_ea_id("EAID", raw_id)
        id_map[raw_id] = ea_id
        name_map[raw_id] = c_name
        
    root = ET.Element("xmi:XMI", {
        "xmi:version": "2.1",
        "xmlns:uml": "http://schema.omg.org/spec/UML/2.1",
        "xmlns:xmi": "http://schema.omg.org/spec/XMI/2.1"
    })
    
    # Documentación estándar EA
    ET.SubElement(root, "xmi:Documentation", {
        "exporter": "Enterprise Architect",
        "exporterVersion": "6.5"
    })
    
    # Modelo UML
    uml_model = ET.SubElement(root, "uml:Model", {
        "xmi:type": "uml:Model",
        "name": "EA_Model",
        "visibility": "public"
    })
    
    # Paquete del proyecto dentro del modelo UML
    pkg_el = ET.SubElement(uml_model, "packagedElement", {
        "xmi:type": "uml:Package",
        "xmi:id": pkg_id,
        "name": clean_name,
        "visibility": "public"
    })
    
    # -------------------------------------------------------------------
    # Recolectar todos los tipos primitivos únicos usados en el diagrama
    # y definirlos como PrimitiveType dentro del paquete para que EA
    # los resuelva correctamente (evita que muestre {bag}).
    # -------------------------------------------------------------------
    primitive_type_map = {}  # nombre_tipo -> xmi:id del PrimitiveType
    for node in nodes:
        data = node.get("data", {})
        for attr in data.get("attributes", []):
            t = str(attr.get("data_type", "String") or "String").strip()
            if t and t not in primitive_type_map:
                pt_id = make_ea_id("EAPT", t)
                primitive_type_map[t] = pt_id
        for meth in data.get("methods", []):
            t = str(meth.get("return_type", "void") or "void").strip()
            if t and t not in primitive_type_map:
                pt_id = make_ea_id("EAPT", t)
                primitive_type_map[t] = pt_id

    # Declarar cada tipo primitivo como packagedElement uml:PrimitiveType
    for pt_name, pt_id in primitive_type_map.items():
        ET.SubElement(pkg_el, "packagedElement", {
            "xmi:type": "uml:PrimitiveType",
            "xmi:id": pt_id,
            "name": pt_name,
            "visibility": "public"
        })

    # Mapeo de herencias para asignarlas a las clases hijas
    inheritance_map = {}
    edge_ea_map = {}
    
    for edge in edges:
        edge_id = str(edge.get("id"))
        edge_ea_id = make_ea_id("EAID_CONN", edge_id)
        edge_ea_map[edge_id] = edge_ea_id
        
        src_raw = str(edge.get("source"))
        tgt_raw = str(edge.get("target"))
        if src_raw.endswith("-source"): src_raw = src_raw.split("-source")[0]
        if tgt_raw.endswith("-target"): tgt_raw = tgt_raw.split("-target")[0]
        
        src_ea = id_map.get(src_raw)
        tgt_ea = id_map.get(tgt_raw)
        if not src_ea or not tgt_ea:
            continue
            
        rel_type = edge.get("data", {}).get("relation_type", "association")
        if rel_type == "inheritance":
            if src_ea not in inheritance_map:
                inheritance_map[src_ea] = []
            inheritance_map[src_ea].append((edge_ea_id, tgt_ea))
            
    # 1. Clases con atributos, métodos y generalizaciones
    for node in nodes:
        raw_id = str(node.get("id"))
        ea_id = id_map[raw_id]
        data = node.get("data", {})
        c_name = name_map[raw_id]
        
        cls_el = ET.SubElement(pkg_el, "packagedElement", {
            "xmi:type": "uml:Class",
            "xmi:id": ea_id,
            "name": c_name,
            "visibility": "public"
        })
        
        # Generalizaciones hijas
        for edge_ea_id, parent_ea_id in inheritance_map.get(ea_id, []):
            ET.SubElement(cls_el, "generalization", {
                "xmi:type": "uml:Generalization",
                "xmi:id": edge_ea_id,
                "general": parent_ea_id
            })
            
        # Atributos
        for attr in data.get("attributes", []):
            a_name = attr.get("name", "")
            if not a_name:
                continue
            a_type_str = str(attr.get("data_type", "String") or "String").strip()
            a_vis = attr.get("visibility", "-")
            vis_str = "public" if a_vis == "+" else "protected" if a_vis == "#" else "private"
            
            # Referenciar el PrimitiveType por su ID para que EA lo resuelva correctamente
            a_type_id = primitive_type_map.get(a_type_str, make_ea_id("EAPT", a_type_str))
            attr_ea_id = f"{ea_id}_ATTR_{hashlib.md5(a_name.encode('utf-8')).hexdigest()[:8]}"
            attr_el = ET.SubElement(cls_el, "ownedAttribute", {
                "xmi:type": "uml:Property",
                "xmi:id": attr_ea_id,
                "name": a_name,
                "visibility": vis_str,
                # isUnique=true + isOrdered=false evita que EA muestre "{bag}"
                "isUnique": "true",
                "isOrdered": "false",
            })
            # Elemento <type> que referencia al PrimitiveType: formato estándar UML 2.1
            ET.SubElement(attr_el, "type", {
                "xmi:idref": a_type_id
            })
            # Multiplicidad 1..1 explícita: declara que el atributo es escalar (no colección)
            ET.SubElement(attr_el, "lowerValue", {
                "xmi:type": "uml:LiteralInteger",
                "xmi:id": f"{attr_ea_id}_lower",
                "value": "1"
            })
            ET.SubElement(attr_el, "upperValue", {
                "xmi:type": "uml:LiteralUnlimitedNatural",
                "xmi:id": f"{attr_ea_id}_upper",
                "value": "1"
            })
            
        # Métodos / Operaciones
        for meth in data.get("methods", []):
            m_name = meth.get("name", "")
            if not m_name:
                continue
            m_type_str = str(meth.get("return_type", "void") or "void").strip()
            m_vis = meth.get("visibility", "+")
            vis_str = "public" if m_vis == "+" else "protected" if m_vis == "#" else "private"
            
            m_type_id = primitive_type_map.get(m_type_str, make_ea_id("EAPT", m_type_str))
            op_el = ET.SubElement(cls_el, "ownedOperation", {
                "xmi:type": "uml:Operation",
                "xmi:id": f"{ea_id}_OP_{hashlib.md5(m_name.encode('utf-8')).hexdigest()[:8]}",
                "name": m_name,
                "visibility": vis_str
            })
            ret_el = ET.SubElement(op_el, "ownedParameter", {
                "xmi:type": "uml:Parameter",
                "xmi:id": f"{ea_id}_RET_{hashlib.md5(m_name.encode('utf-8')).hexdigest()[:8]}",
                "direction": "return",
            })
            ET.SubElement(ret_el, "type", {
                "xmi:idref": m_type_id
            })

    # 2. Relaciones UML a nivel paquete (Asociaciones, Dependencias, Realizaciones)
    for edge in edges:
        edge_id = str(edge.get("id"))
        edge_ea_id = edge_ea_map.get(edge_id)
        if not edge_ea_id:
            continue
            
        src_raw = str(edge.get("source"))
        tgt_raw = str(edge.get("target"))
        if src_raw.endswith("-source"): src_raw = src_raw.split("-source")[0]
        if tgt_raw.endswith("-target"): tgt_raw = tgt_raw.split("-target")[0]
        
        src_ea = id_map.get(src_raw)
        tgt_ea = id_map.get(tgt_raw)
        if not src_ea or not tgt_ea or src_ea == tgt_ea:
            continue
            
        rel_type = edge.get("data", {}).get("relation_type", "association")
        label = edge.get("data", {}).get("label", "")
        src_mult = edge.get("data", {}).get("sourceMultiplicity", "")
        tgt_mult = edge.get("data", {}).get("targetMultiplicity", "")
        
        if rel_type == "inheritance":
            continue # Se define dentro de la clase como generalization
            
        elif rel_type == "dependency":
            ET.SubElement(pkg_el, "packagedElement", {
                "xmi:type": "uml:Dependency",
                "xmi:id": edge_ea_id,
                "name": label,
                "client": src_ea,
                "supplier": tgt_ea
            })
        elif rel_type == "realization":
            ET.SubElement(pkg_el, "packagedElement", {
                "xmi:type": "uml:Realization",
                "xmi:id": edge_ea_id,
                "name": label,
                "client": src_ea,
                "supplier": tgt_ea
            })
        else:
            # Association, Composition, Aggregation, Directed
            assoc_el = ET.SubElement(pkg_el, "packagedElement", {
                "xmi:type": "uml:Association",
                "xmi:id": edge_ea_id,
                "name": label,
                "memberEnd": f"{edge_ea_id}_src {edge_ea_id}_dst"
            })
            
            src_agg = "composite" if rel_type == "composition" else "shared" if rel_type == "aggregation" else "none"
            
            end1 = ET.SubElement(assoc_el, "ownedEnd", {
                "xmi:type": "uml:Property",
                "xmi:id": f"{edge_ea_id}_src",
                "visibility": "public",
                "association": edge_ea_id,
                "type": src_ea,
                "aggregation": src_agg
            })
            if src_mult:
                parts = str(src_mult).split("..")
                l = parts[0] if parts[0] != "*" else "0"
                u = parts[1] if len(parts) > 1 else parts[0]
                ET.SubElement(end1, "lowerValue", {"xmi:type": "uml:LiteralInteger", "value": l})
                ET.SubElement(end1, "upperValue", {"xmi:type": "uml:LiteralUnlimitedNatural", "value": u})
                
            end2 = ET.SubElement(assoc_el, "ownedEnd", {
                "xmi:type": "uml:Property",
                "xmi:id": f"{edge_ea_id}_dst",
                "visibility": "public",
                "association": edge_ea_id,
                "type": tgt_ea,
                "aggregation": "none"
            })
            if tgt_mult:
                parts = str(tgt_mult).split("..")
                l = parts[0] if parts[0] != "*" else "0"
                u = parts[1] if len(parts) > 1 else parts[0]
                ET.SubElement(end2, "lowerValue", {"xmi:type": "uml:LiteralInteger", "value": l})
                ET.SubElement(end2, "upperValue", {"xmi:type": "uml:LiteralUnlimitedNatural", "value": u})

    # 3. Extensión nativa de Enterprise Architect 6.5
    ext = ET.SubElement(root, "xmi:Extension", {
        "extender": "Enterprise Architect",
        "extenderID": "6.5"
    })
    
    # 3a. Elements: Mapea cada elemento al paquete de EA correspondiente
    elems_ext = ET.SubElement(ext, "elements")
    
    # Elemento paquete
    pkg_meta = ET.SubElement(elems_ext, "element", {
        "xmi:idref": pkg_id,
        "xmi:type": "uml:Package",
        "name": clean_name,
        "scope": "public"
    })
    ET.SubElement(pkg_meta, "model", {
        "package2": pkg_id,
        "package": "EAPK_00000000",
        "tpos": "0",
        "ea_eleType": "package"
    })
    ET.SubElement(pkg_meta, "properties", {"isSpecification": "false", "sType": "Package", "nType": "0", "scope": "public"})
    ET.SubElement(pkg_meta, "extendedProperties", {"tagged": "0", "package_name": "Model"})
    
    # Cada clase en la extensión
    for node in nodes:
        raw_id = str(node.get("id"))
        ea_id = id_map[raw_id]
        c_name = name_map[raw_id]
        
        c_el = ET.SubElement(elems_ext, "element", {
            "xmi:idref": ea_id,
            "xmi:type": "uml:Class",
            "name": c_name,
            "scope": "public"
        })
        ET.SubElement(c_el, "model", {
            "package": pkg_id,
            "tpos": "0",
            "ea_eleType": "element"
        })
        ET.SubElement(c_el, "properties", {
            "isSpecification": "false",
            "sType": "Class",
            "nType": "0",
            "scope": "public"
        })
        ET.SubElement(c_el, "extendedProperties", {
            "tagged": "0",
            "package_name": clean_name
        })
        
        # Atributos en la extensión nativa de EA (garantiza tipo nativo, collection=false y duplicates=0 para suprimir {bag})
        data = node.get("data", {})
        attrs_list = data.get("attributes", [])
        if attrs_list:
            attrs_ext = ET.SubElement(c_el, "attributes")
            for a_idx, attr in enumerate(attrs_list):
                a_name = attr.get("name", "")
                if not a_name:
                    continue
                a_type_str = str(attr.get("data_type", "String") or "String").strip()
                a_vis = attr.get("visibility", "-")
                scope_str = "Public" if a_vis == "+" else "Protected" if a_vis == "#" else "Private"
                attr_ea_id = f"{ea_id}_ATTR_{hashlib.md5(a_name.encode('utf-8')).hexdigest()[:8]}"
                
                a_sub = ET.SubElement(attrs_ext, "attribute", {
                    "xmi:idref": attr_ea_id,
                    "name": a_name,
                    "scope": scope_str
                })
                ET.SubElement(a_sub, "initial")
                ET.SubElement(a_sub, "documentation")
                ET.SubElement(a_sub, "model", {
                    "ea_localid": str(a_idx + 1),
                    "type": a_type_str,
                    "name": a_name
                })
                ET.SubElement(a_sub, "properties", {
                    "type": a_type_str,
                    "collection": "false",
                    "duplicates": "0",
                    "changeability": "changeable"
                })
                ET.SubElement(a_sub, "coords", {"ordered": "0"})
                ET.SubElement(a_sub, "containment", {"containment": "Not Specified", "position": str(a_idx)})
                ET.SubElement(a_sub, "style")
                ET.SubElement(a_sub, "styleex", {"value": "volatile=0;"})
                ET.SubElement(a_sub, "tags")
                ET.SubElement(a_sub, "xrefs")

        # Operaciones en la extensión nativa de EA
        meths_list = data.get("methods", [])
        if meths_list:
            ops_ext = ET.SubElement(c_el, "operations")
            for m_idx, meth in enumerate(meths_list):
                m_name = meth.get("name", "")
                if not m_name:
                    continue
                m_type_str = str(meth.get("return_type", "void") or "void").strip()
                m_vis = meth.get("visibility", "+")
                scope_str = "Public" if m_vis == "+" else "Protected" if m_vis == "#" else "Private"
                op_ea_id = f"{ea_id}_OP_{hashlib.md5(m_name.encode('utf-8')).hexdigest()[:8]}"
                
                op_sub = ET.SubElement(ops_ext, "operation", {
                    "xmi:idref": op_ea_id,
                    "name": m_name,
                    "scope": scope_str
                })
                ET.SubElement(op_sub, "properties", {
                    "type": m_type_str,
                    "ea_type": m_type_str,
                    "position": str(m_idx)
                })
                ET.SubElement(op_sub, "model", {
                    "ea_localid": str(m_idx + 1),
                    "type": m_type_str,
                    "name": m_name
                })
                ET.SubElement(op_sub, "type", {
                    "type": m_type_str,
                    "returnarray": "0",
                    "pure": "0"
                })
        
    # 3b. Connectors en la extensión (Garantiza nombres, tipos y multiplicidades en EA)
    conns_ext = ET.SubElement(ext, "connectors")
    for edge in edges:
        edge_id = str(edge.get("id"))
        edge_ea_id = edge_ea_map.get(edge_id)
        if not edge_ea_id:
            continue
            
        src_raw = str(edge.get("source"))
        tgt_raw = str(edge.get("target"))
        if src_raw.endswith("-source"): src_raw = src_raw.split("-source")[0]
        if tgt_raw.endswith("-target"): tgt_raw = tgt_raw.split("-target")[0]
        src_ea = id_map.get(src_raw)
        tgt_ea = id_map.get(tgt_raw)
        if not src_ea or not tgt_ea or src_ea == tgt_ea:
            continue
            
        rel_type = edge.get("data", {}).get("relation_type", "association")
        label = edge.get("data", {}).get("label", "")
        src_mult = edge.get("data", {}).get("sourceMultiplicity", "")
        tgt_mult = edge.get("data", {}).get("targetMultiplicity", "")
        
        ea_type = "Association"
        src_agg = "none"
        direction = "Unspecified"
        if rel_type == "inheritance":
            ea_type = "Generalization"
            direction = "Source -> Destination"
        elif rel_type == "dependency":
            ea_type = "Dependency"
            direction = "Source -> Destination"
        elif rel_type == "realization":
            ea_type = "Realisation"
            direction = "Source -> Destination"
        elif rel_type == "composition":
            ea_type = "Aggregation"
            src_agg = "composite"
        elif rel_type == "aggregation":
            ea_type = "Aggregation"
            src_agg = "shared"
        elif rel_type == "directed_association":
            direction = "Source -> Destination"
            
        conn = ET.SubElement(conns_ext, "connector", {"xmi:idref": edge_ea_id})
        source_sub = ET.SubElement(conn, "source", {"xmi:idref": src_ea})
        ET.SubElement(source_sub, "model", {"name": name_map.get(src_raw, ""), "type": "Class"})
        ET.SubElement(source_sub, "type", {"aggregation": src_agg, "multiplicity": str(src_mult)})
        
        target_sub = ET.SubElement(conn, "target", {"xmi:idref": tgt_ea})
        ET.SubElement(target_sub, "model", {"name": name_map.get(tgt_raw, ""), "type": "Class"})
        ET.SubElement(target_sub, "type", {"aggregation": "none", "multiplicity": str(tgt_mult)})
        
        ET.SubElement(conn, "properties", {"name": label, "ea_type": ea_type, "direction": direction})

    # 3c. Diagrams: Crea el diagrama nativo dentro del paquete con los elementos y conectores ubicados
    diags_ext = ET.SubElement(ext, "diagrams")
    diag_el = ET.SubElement(diags_ext, "diagram", {"xmi:id": diag_id})
    ET.SubElement(diag_el, "model", {"package": pkg_id, "localID": "1", "owner": pkg_id})
    ET.SubElement(diag_el, "properties", {"name": clean_name, "type": "Logical"})
    now_str = datetime.date.today().isoformat()
    ET.SubElement(diag_el, "project", {"author": "User", "version": "1.0", "created": now_str, "modified": now_str})
    
    diag_elems = ET.SubElement(diag_el, "elements")
    # Cajas de clases en el diagrama con sus geometrías
    for node in nodes:
        raw_id = str(node.get("id"))
        ea_id = id_map[raw_id]
        pos = node.get("position", {"x": 80, "y": 80})
        x = int(pos.get("x", 80)) - min_x + 80
        y = int(pos.get("y", 80)) - min_y + 80
        geom = f"Left={x};Top={y};Right={x + 160};Bottom={y + 100};"
        ET.SubElement(diag_elems, "element", {
            "geometry": geom,
            "subject": ea_id
        })
        
    # Conectores en el diagrama para que se dibujen automáticamente las flechas
    for edge in edges:
        edge_id = str(edge.get("id"))
        edge_ea_id = edge_ea_map.get(edge_id)
        if not edge_ea_id:
            continue
        ET.SubElement(diag_elems, "element", {
            "geometry": "SX=0;SY=0;EX=0;EY=0;Path=;",
            "subject": edge_ea_id,
            "style": ";Hidden=0;"
        })

    xml_bytes = ET.tostring(root, encoding="utf-8")
    parsed = minidom.parseString(xml_bytes)
    return parsed.toprettyxml(indent="  ")
