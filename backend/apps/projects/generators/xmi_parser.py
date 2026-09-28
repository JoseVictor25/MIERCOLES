import xml.etree.ElementTree as ET
import uuid
import random

def get_id(el):
    """Obtiene el ID de definición del elemento XML."""
    if el is None:
        return None
    for k, v in el.attrib.items():
        if k.endswith('}id') or k in ['id', 'xmi:id', 'xmi.id']:
            return v
    return None

def get_idref(el):
    """Obtiene una referencia por ID (idref o subject)."""
    if el is None:
        return None
    for k, v in el.attrib.items():
        if k.endswith('}idref') or k in ['idref', 'xmi:idref', 'xmi.idref', 'subject']:
            return v
    return None

def get_type_attr(el):
    """Obtiene el tipo XMI o UML de un elemento."""
    if el is None:
        return ""
    for k, v in el.attrib.items():
        if k.endswith('}type') or k in ['type', 'xmi:type']:
            return v
    return el.attrib.get("xmi:type") or el.attrib.get("{http://schema.omg.org/spec/XMI/2.1}type") or ""

def get_local_name(tag):
    """Extrae el nombre local de una etiqueta sin namespaces."""
    if not tag:
        return ""
    return tag.split('}')[-1].split(':')[-1]

def parse_xmi(xmi_data) -> dict:
    """
    Parsea una cadena o bytes XMI/XML (Enterprise Architect, StarUML, MagicDraw, etc.)
    y extrae Clases, Atributos, Métodos y Relaciones en formato React Flow.
    """
    root = None
    if isinstance(xmi_data, bytes):
        try:
            root = ET.fromstring(xmi_data)
        except ET.ParseError:
            for enc in ['utf-8', 'utf-8-sig', 'utf-16', 'windows-1252', 'latin-1']:
                try:
                    s = xmi_data.decode(enc)
                    root = ET.fromstring(s)
                    break
                except Exception:
                    pass
    elif isinstance(xmi_data, str):
        try:
            root = ET.fromstring(xmi_data)
        except ET.ParseError:
            try:
                root = ET.fromstring(xmi_data.encode('utf-8'))
            except Exception:
                pass
    else:
        raise ValueError("Formato de archivo o datos no soportado.")

    if root is None:
        raise ValueError("El archivo subido no es un XML válido o tiene una codificación incompatible.")

    # 1. Mapeo de tipos de datos primitivos
    datatypes = {}
    for el in root.iter():
        lname = get_local_name(el.tag)
        # Capturar tanto DataType/PrimitiveType independientes
        # como packagedElement xmi:type="uml:PrimitiveType" / "uml:DataType" (generados por exportadores)
        if lname in ['DataType', 'PrimitiveType', 'datatype', 'primitivetype']:
            dt_id = get_id(el)
            dt_name = el.attrib.get("name")
            if dt_id and dt_name:
                datatypes[dt_id] = dt_name
        elif lname == 'packagedElement':
            t = get_type_attr(el)
            if t in ['uml:PrimitiveType', 'PrimitiveType', 'uml:DataType', 'DataType']:
                dt_id = get_id(el)
                dt_name = el.attrib.get("name")
                if dt_id and dt_name:
                    datatypes[dt_id] = dt_name

    # 2. Parseo de posiciones del diagrama (Enterprise Architect <element geometry="..."/> y StarUML <DiagramElement>)
    diagram_elements = {}
    for el in root.iter():
        lname = get_local_name(el.tag)
        if lname in ['DiagramElement', 'element', 'diagramElement']:
            subj = el.attrib.get('subject') or get_idref(el)
            geom = el.attrib.get('geometry')
            if subj and geom:
                try:
                    parts = dict(p.split('=') for p in geom.split(';') if '=' in p)
                    left = int(parts.get("Left", parts.get("left", 0)))
                    top = int(parts.get("Top", parts.get("top", 0)))
                    # En Enterprise Architect, las coordenadas Y suelen ser negativas hacia abajo (ej. Top=-80)
                    y_pos = abs(top) if top != 0 else 0
                    x_pos = abs(left) if left != 0 else 0
                    diagram_elements[subj] = {"x": x_pos, "y": y_pos}
                except (ValueError, Exception):
                    pass

    # Normalizar posiciones relativas con un margen inicial limpio
    if diagram_elements:
        min_x = min(p["x"] for p in diagram_elements.values())
        min_y = min(p["y"] for p in diagram_elements.values())
        for subj in diagram_elements:
            diagram_elements[subj]["x"] = diagram_elements[subj]["x"] - min_x + 80
            diagram_elements[subj]["y"] = diagram_elements[subj]["y"] - min_y + 80

    # 3. Cache de nombres y atributos en extensiones de Enterprise Architect (<elements><element><attributes>...)
    ea_extension_attrs = {}
    ea_extension_names = {}
    for el in root.iter():
        lname = get_local_name(el.tag)
        if lname == 'element':
            ref_id = get_idref(el) or get_id(el)
            name_val = el.attrib.get('name')
            if ref_id and name_val:
                ea_extension_names[ref_id] = name_val

            t = get_type_attr(el) or el.attrib.get('ea_eleType', '')
            if ref_id and ('Class' in t or t == 'element'):
                attrs_for_el = []
                for child in el.iter():
                    if get_local_name(child.tag) == 'attribute':
                        a_name = child.attrib.get('name')
                        if not a_name:
                            continue
                        # Buscar tipo en atributo, o en subelementos <properties type="..."> o <model type="...">
                        a_type = child.attrib.get('type')
                        if not a_type:
                            for sub in child.iter():
                                sname = get_local_name(sub.tag)
                                if sname in ['properties', 'model']:
                                    cand = sub.attrib.get('type') or sub.attrib.get('ea_type')
                                    if cand and cand.strip():
                                        a_type = cand.strip()
                                        break
                        scope = child.attrib.get('scope', 'public').lower()
                        vis = '-' if 'priv' in scope else '+' if 'pub' in scope else '#'
                        attrs_for_el.append({
                            'name': a_name,
                            'data_type': a_type,
                            'visibility': vis
                        })
                if attrs_for_el:
                    ea_extension_attrs[ref_id] = attrs_for_el

    # 4. Encontrar clases legítimas (definiciones reales con ID propio)
    classes = []
    seen_class_ids = set()

    for el in root.iter():
        lname = get_local_name(el.tag)
        t = get_type_attr(el)

        is_cls = False
        if lname in ['Class', 'Interface', 'AssociationClass']:
            is_cls = True
        elif t in ['uml:Class', 'Class', 'uml:Interface', 'Interface', 'uml:AssociationClass']:
            is_cls = True

        if is_cls:
            c_id = get_id(el)
            # REGLA CRÍTICA: solo aceptar definiciones con un ID real (xmi.id o id).
            # Los elementos que sólo tienen idref/xmi.idref son referencias secundarias (ej. participantes de relaciones)
            if not c_id:
                continue
            if c_id not in seen_class_ids:
                seen_class_ids.add(c_id)
                classes.append(el)

    nodes = []
    class_id_map = {}
    class_name_map = {}

    for idx, cls in enumerate(classes):
        raw_id = get_id(cls)
        c_name = cls.attrib.get("name") or ea_extension_names.get(raw_id)
        if not c_name:
            for ch in cls:
                if get_local_name(ch.tag) in ['name', 'Name'] and ch.text:
                    c_name = ch.text.strip()
                    break
        if not c_name:
            c_name = f"Class_{idx+1}"

        reactflow_id = f"class-{uuid.uuid4().hex[:6]}"
        class_id_map[raw_id] = reactflow_id
        class_name_map[c_name] = reactflow_id

        # Atributos de la clase
        attributes = []
        for child in cls.iter():
            clname = get_local_name(child.tag)
            if clname in ['ownedAttribute', 'Attribute', 'attribute']:
                a_name = child.attrib.get("name", "")
                if not a_name:
                    continue

                visibility = child.attrib.get("visibility", "private").lower()
                vis_char = "+" if "pub" in visibility else "-" if "priv" in visibility else "#"

                # Detección del tipo de dato
                a_type = child.attrib.get("type")
                # Si el tipo viene como atributo pero es un ID conocido, resolverlo
                if a_type and a_type in datatypes:
                    a_type = datatypes[a_type]
                elif a_type and (a_type.startswith("EAJava_") or a_type.startswith("EAC_") or a_type.startswith("EACsharp_")):
                    a_type = a_type.split("_", 1)[1]
                elif a_type and a_type.startswith("uml:"):
                    a_type = a_type.split(":")[-1]
                elif a_type and a_type.startswith("eaxmiid"):
                    a_type = None

                if not a_type:
                    # 1. Revisar TaggedValue (típico en Enterprise Architect: <TaggedValue tag="type" value="int"/>)
                    for tv in child.iter():
                        if get_local_name(tv.tag) in ['TaggedValue', 'taggedValue']:
                            tag_name = tv.attrib.get("tag", "").lower()
                            if tag_name in ['type', 'ea_type', 'datatype']:
                                a_type = tv.attrib.get("value")
                                break

                    # 2. Revisar si tiene subelementos <properties> o <model> directamente
                    if not a_type:
                        for prop in child.iter():
                            if get_local_name(prop.tag) in ['properties', 'model']:
                                cand = prop.attrib.get("type") or prop.attrib.get("ea_type")
                                if cand and cand.strip():
                                    a_type = cand.strip()
                                    break

                    # 3. Revisar elemento hijo <type> o <Classifier>
                    if not a_type:
                        for g_child in child.iter():
                            glname = get_local_name(g_child.tag)
                            if glname in ['type', 'Classifier', 'classifier'] or g_child.tag.endswith('}type'):
                                idref_val = get_idref(g_child)
                                if idref_val:
                                    if idref_val in datatypes:
                                        a_type = datatypes[idref_val]
                                        break
                                    elif idref_val.startswith("EAJava_") or idref_val.startswith("EAC_") or idref_val.startswith("EACsharp_"):
                                        a_type = idref_val.split("_", 1)[1]
                                        break
                                    elif idref_val in ea_extension_names:
                                        a_type = ea_extension_names[idref_val]
                                        break
                                t_name = g_child.attrib.get("name")
                                if t_name and t_name.strip():
                                    a_type = t_name.strip()
                                    break
                                href = g_child.attrib.get("href", "")
                                if href:
                                    a_type = href.split("#")[-1]
                                    break

                # 4. Enriquecer con tipo de extensión de EA si no se tiene o era String pero EA tiene algo más específico
                if raw_id in ea_extension_attrs:
                    ea_attrs_dict = {a['name']: a['data_type'] for a in ea_extension_attrs[raw_id] if a.get('data_type')}
                    if a_name in ea_attrs_dict:
                        ea_cand = ea_attrs_dict[a_name]
                        if not a_type or (a_type == 'String' and ea_cand != 'String'):
                            a_type = ea_cand

                if not a_type:
                    a_type = "String"

                attributes.append({
                    "id": uuid.uuid4().hex[:8],
                    "name": a_name,
                    "visibility": vis_char,
                    "data_type": a_type
                })

        # Si no había atributos en el modelo UML o faltaban tipos, enriquecer desde la extensión de EA
        if not attributes and raw_id in ea_extension_attrs:
            for ea_attr in ea_extension_attrs[raw_id]:
                attributes.append({
                    "id": uuid.uuid4().hex[:8],
                    "name": ea_attr['name'],
                    "visibility": ea_attr['visibility'],
                    "data_type": ea_attr['data_type'] or "String"
                })
        elif attributes and raw_id in ea_extension_attrs:
            ea_types = {a['name']: a['data_type'] for a in ea_extension_attrs[raw_id] if a.get('data_type')}
            for a in attributes:
                if (a['data_type'] == 'String' or not a['data_type']) and a['name'] in ea_types:
                    a['data_type'] = ea_types[a['name']]

        # Métodos / Operaciones
        methods = []
        for child in cls.iter():
            clname = get_local_name(child.tag)
            if clname in ['ownedOperation', 'Operation', 'operation']:
                m_name = child.attrib.get("name", "")
                if not m_name:
                    continue
                visibility = child.attrib.get("visibility", "public").lower()
                vis_char = "+" if "pub" in visibility else "-" if "priv" in visibility else "#"
                m_type = "void"
                for g_child in child.iter():
                    if get_local_name(g_child.tag) in ['ownedParameter', 'Parameter', 'parameter']:
                        if g_child.attrib.get("direction") == "return":
                            m_type = g_child.attrib.get("type", "void")
                            for gg_child in g_child.iter():
                                href = gg_child.attrib.get("href", "")
                                if href:
                                    m_type = href.split("#")[-1]
                methods.append({
                    "id": uuid.uuid4().hex[:8],
                    "name": m_name,
                    "visibility": vis_char,
                    "return_type": m_type
                })

        # Posicionamiento: usar diagrama si existe, o cuadrícula ordenada
        pos = diagram_elements.get(raw_id)
        if not pos:
            col = idx % 3
            row = idx // 3
            pos = {"x": col * 280 + 80, "y": row * 240 + 80}

        nodes.append({
            "id": reactflow_id,
            "type": "classNode",
            "position": pos,
            "data": {
                "id": reactflow_id,
                "name": c_name,
                "attributes": attributes,
                "methods": methods
            }
        })

    # 5. Parseo de Relaciones
    edges = []
    seen_edges = set()

    def add_edge(src_raw, tgt_raw, rel_type="association", label="", src_mult="", tgt_mult=""):
        src = class_id_map.get(src_raw) or class_name_map.get(src_raw)
        tgt = class_id_map.get(tgt_raw) or class_name_map.get(tgt_raw)
        if not src:
            for k, v in class_name_map.items():
                if str(k).strip().lower() == str(src_raw).strip().lower():
                    src = v
                    break
        if not tgt:
            for k, v in class_name_map.items():
                if str(k).strip().lower() == str(tgt_raw).strip().lower():
                    tgt = v
                    break

        if not src or not tgt or src == tgt:
            return
        edge_key = (src, tgt, rel_type, label)
        if edge_key in seen_edges:
            return
        seen_edges.add(edge_key)
        edges.append({
            "id": f"edge-{uuid.uuid4().hex[:8]}",
            "source": src,
            "target": tgt,
            "type": "umlEdge",
            "data": {
                "relation_type": rel_type,
                "label": label,
                "sourceMultiplicity": str(src_mult).replace("-1", "*") if src_mult else "",
                "targetMultiplicity": str(tgt_mult).replace("-1", "*") if tgt_mult else ""
            }
        })

    # 5a. Extensión de conectores de Enterprise Architect (<connectors><connector>)
    for el in root.iter():
        if get_local_name(el.tag) == 'connector':
            src_el = None
            tgt_el = None
            props_el = None
            for child in el:
                c_lname = get_local_name(child.tag)
                if c_lname == 'source': src_el = child
                elif c_lname == 'target': tgt_el = child
                elif c_lname == 'properties': props_el = child

            if src_el is not None and tgt_el is not None:
                src_id = get_idref(src_el) or get_id(src_el)
                tgt_id = get_idref(tgt_el) or get_id(tgt_el)

                if not src_id:
                    for sc in src_el.iter():
                        cand = get_idref(sc) or get_id(sc) or sc.attrib.get('name')
                        if cand and (cand in class_id_map or cand in class_name_map):
                            src_id = cand
                            break
                    if not src_id:
                        m_el = src_el.find('model')
                        if m_el is not None:
                            src_id = m_el.attrib.get('name')

                if not tgt_id:
                    for tc in tgt_el.iter():
                        cand = get_idref(tc) or get_id(tc) or tc.attrib.get('name')
                        if cand and (cand in class_id_map or cand in class_name_map):
                            tgt_id = cand
                            break
                    if not tgt_id:
                        m_el = tgt_el.find('model')
                        if m_el is not None:
                            tgt_id = m_el.attrib.get('name')

                src_mult = ""
                tgt_mult = ""
                src_agg = "none"
                tgt_agg = "none"

                for sc in src_el.iter():
                    if get_local_name(sc.tag) == 'type':
                        src_mult = sc.attrib.get('multiplicity', '')
                        src_agg = sc.attrib.get('aggregation', 'none')
                for tc in tgt_el.iter():
                    if get_local_name(tc.tag) == 'type':
                        tgt_mult = tc.attrib.get('multiplicity', '')
                        tgt_agg = tc.attrib.get('aggregation', 'none')

                ea_type = "Association"
                direction = "Unspecified"
                rel_label = el.attrib.get('name', '')
                if props_el is not None:
                    ea_type = props_el.attrib.get('ea_type', 'Association')
                    direction = props_el.attrib.get('direction', 'Unspecified')
                    if not rel_label:
                        rel_label = props_el.attrib.get('name', '')

                r_type = "association"
                if ea_type in ['Generalization', 'Inheritance']:
                    r_type = "inheritance"
                elif ea_type in ['Realisation', 'Realization']:
                    r_type = "realization"
                elif ea_type == 'Dependency':
                    r_type = "dependency"
                elif ea_type in ['Aggregation', 'Association']:
                    if src_agg == 'composite' or tgt_agg == 'composite':
                        r_type = "composition"
                    elif src_agg == 'shared' or tgt_agg == 'shared':
                        r_type = "aggregation"
                    elif direction in ['Source -> Destination', 'Directed']:
                        r_type = "directed_association"
                    else:
                        r_type = "association"

                # En composición y agregación, el rombo pertenece al todo (origen).
                # Si EA lo definió en el target, invertimos para que el rombo quede en el origen.
                if tgt_agg in ['composite', 'shared'] and src_agg == 'none':
                    src_id, tgt_id = tgt_id, src_id
                    src_mult, tgt_mult = tgt_mult, src_mult

                add_edge(src_id, tgt_id, rel_type=r_type, label=rel_label, src_mult=src_mult, tgt_mult=tgt_mult)

    # 5b. Relaciones UML Estándar (<UML:Association>, <UML:Generalization>, <UML:Dependency>)
    for el in root.iter():
        lname = get_local_name(el.tag)
        t = get_type_attr(el)

        # Generalización
        if lname in ['Generalization', 'generalization']:
            sub = el.attrib.get("subtype") or el.attrib.get("client") or el.attrib.get("specific") or el.attrib.get("child")
            sup = el.attrib.get("supertype") or el.attrib.get("supplier") or el.attrib.get("general") or el.attrib.get("parent")
            if sub and sup:
                add_edge(sub, sup, rel_type="inheritance")

        # Dependencia
        elif lname in ['Dependency', 'dependency'] or t in ['uml:Dependency', 'Dependency']:
            sub = el.attrib.get("client")
            sup = el.attrib.get("supplier")
            rel_label = el.attrib.get("name", "")
            if sub and sup:
                add_edge(sub, sup, rel_type="dependency", label=rel_label)

        # Asociaciones estándar
        elif lname in ['Association', 'association'] or t in ['uml:Association', 'Association']:
            ends = []
            for child in el.iter():
                clname = get_local_name(child.tag)
                if clname in ['ownedEnd', 'AssociationEnd', 'memberEnd']:
                    ends.append(child)

            if len(ends) >= 2:
                def get_participant(end_node):
                    p = end_node.attrib.get("type") or end_node.attrib.get("participant")
                    if p and (p in class_id_map or p in class_name_map):
                        return p
                    # Buscar en cualquier descendiente con idref o xmi.idref
                    for desc in end_node.iter():
                        ref = get_idref(desc)
                        if ref and (ref in class_id_map or ref in class_name_map):
                            return ref
                    return p

                src = get_participant(ends[0])
                tgt = get_participant(ends[1])

                def get_mult(end_node):
                    m = end_node.attrib.get("multiplicity")
                    if m: return m.replace("-1", "*")
                    lower = None
                    upper = None
                    for c in end_node.iter():
                        cl = get_local_name(c.tag)
                        if cl == 'lowerValue': lower = c.attrib.get("value", "0")
                        elif cl == 'upperValue': upper = c.attrib.get("value", "*")
                        elif cl == 'MultiplicityRange':
                            lower = c.attrib.get("lower", "")
                            upper = c.attrib.get("upper", "")
                    if lower is None and upper is None: return ""
                    if lower == upper and lower != "": return lower
                    l_val = lower if lower is not None else ""
                    u_val = upper if upper is not None else ""
                    if u_val == "-1": u_val = "*"
                    if l_val == "-1": l_val = "*"
                    if l_val == "1" and u_val == "*": return "1..*"
                    if l_val == "0" and u_val == "*": return "0..*"
                    if l_val == "0" and u_val == "1": return "0..1"
                    if l_val and u_val: return f"{l_val}..{u_val}"
                    return u_val or l_val or ""

                src_mult = get_mult(ends[0])
                tgt_mult = get_mult(ends[1])

                agg0 = ends[0].attrib.get("aggregation", "none")
                agg1 = ends[1].attrib.get("aggregation", "none")
                r_type = "association"
                if agg0 == "composite" or agg1 == "composite":
                    r_type = "composition"
                elif agg0 == "shared" or agg1 == "shared":
                    r_type = "aggregation"

                if agg1 in ["shared", "composite"] and agg0 == "none":
                    src, tgt = tgt, src
                    src_mult, tgt_mult = tgt_mult, src_mult

                rel_label = el.attrib.get("name", "")
                if src and tgt:
                    add_edge(src, tgt, rel_type=r_type, label=rel_label, src_mult=src_mult, tgt_mult=tgt_mult)

    # 5c. Generalizaciones anidadas dentro de clases (<generalization general="..."/>)
    for cls in classes:
        cls_id = get_id(cls)
        for g in cls.iter():
            if get_local_name(g.tag) in ['generalization', 'Generalization']:
                gen = g.attrib.get("general") or get_idref(g)
                if gen:
                    add_edge(cls_id, gen, rel_type="inheritance")

    # 6. Calcular handles óptimos para los bordes
    node_positions = {n["id"]: n["position"] for n in nodes}
    for e in edges:
        s_id = e.get("source")
        t_id = e.get("target")
        s_pos = node_positions.get(s_id, {"x": 0, "y": 0})
        t_pos = node_positions.get(t_id, {"x": 0, "y": 0})

        sx = s_pos["x"] + 80
        sy = s_pos["y"] + 50
        tx = t_pos["x"] + 80
        ty = t_pos["y"] + 50

        dx = tx - sx
        dy = ty - sy

        if abs(dx) >= abs(dy):
            if dx > 0:
                e["sourceHandle"] = "right-source"
                e["targetHandle"] = "left-target"
            else:
                e["sourceHandle"] = "left-source"
                e["targetHandle"] = "right-target"
        else:
            if dy > 0:
                e["sourceHandle"] = "bottom-source"
                e["targetHandle"] = "top-target"
            else:
                e["sourceHandle"] = "top-source"
                e["targetHandle"] = "bottom-target"

    return {"nodes": nodes, "edges": edges}
