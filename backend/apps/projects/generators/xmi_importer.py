"""Lectura tolerante de XMI UML 2.1, 2.4.1 y 2.5.1."""

import re
import uuid
import xml.etree.ElementTree as ET

MAX_XMI_BYTES = 5 * 1024 * 1024


def _local(tag):
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _attr(el, name, default=None):
    return next((v for k, v in el.attrib.items() if _local(k) == name), default)


def _kind(el):
    return (_attr(el, "type") if _local(el.tag) in ("packagedElement", "ownedAttribute", "ownedOperation") else None) or _local(el.tag)


def _ref(value):
    return str(value or "").split("#")[-1]


def _reference(el, name="type"):
    value = el.get(name)
    if value:
        return _ref(value)
    for child in el:
        if _local(child.tag) == name:
            return _ref(_attr(child, "idref") or child.get("href") or child.text)
    return ""


def _multiplicity(el):
    value = el.get("multiplicity")
    if value:
        return value.replace("-1", "*")
    lower = upper = None
    for child in el:
        tag = _local(child.tag)
        if tag == "lowerValue":
            lower = child.get("value", child.text or "0")
        elif tag == "upperValue":
            upper = child.get("value", child.text or "*")
    if lower is None and upper is None:
        return ""
    lower, upper = lower or "0", (upper or "*").replace("-1", "*")
    return lower if lower == upper else f"{lower}..{upper}"


def _visibility(value):
    return {"public": "+", "private": "-", "protected": "#", "package": "~"}.get(str(value or "").lower(), "+")


def _position(el):
    try:
        return {"x": float(el.get("x")), "y": float(el.get("y"))}
    except (TypeError, ValueError):
        return None


def parse_xmi_preview(raw):
    """Devuelve diagrama y advertencias; nunca persiste cambios."""
    if not isinstance(raw, (bytes, str)):
        raise ValueError("No se recibió un archivo XML válido.")
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(data) > MAX_XMI_BYTES:
        raise ValueError("El archivo XMI supera el límite de 5 MB.")
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.IGNORECASE):
        raise ValueError("El archivo contiene DOCTYPE o ENTITY; no se permiten entidades XML.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"XML mal formado: {exc}") from exc
    if _local(root.tag) != "XMI" or not any(_local(el.tag) == "Model" for el in root.iter()):
        raise ValueError("El archivo no es un XMI UML válido.")
    warnings = []
    namespace = root.tag.split("}")[0][1:] if "}" in root.tag else ""
    version = {
        "http://www.omg.org/spec/XMI/20131001": "2.5.1",
        "http://www.omg.org/spec/XMI/20110701": "2.4.1",
        "http://schema.omg.org/spec/XMI/2.1": "2.1",
    }.get(namespace, _attr(root, "version") or "desconocida")
    if version not in ("2.5.1", "2.4.1", "2.1"):
        warnings.append(f"Namespace XMI no reconocido ({namespace or 'sin namespace'}); se leyó el contenido UML disponible.")
    all_by_id = {_attr(el, "id"): el for el in root.iter() if _attr(el, "id")}
    classifiers = {}
    types = {}
    for el in root.iter():
        kind = _kind(el).rsplit(":", 1)[-1]
        eid = _attr(el, "id")
        if eid and kind in ("Class", "Interface", "Enumeration", "AssociationClass"):
            classifiers[eid] = (el, kind)
            types[eid] = el.get("name", eid)
        elif eid and kind in ("PrimitiveType", "DataType"):
            types[eid] = el.get("name", eid)
    if not classifiers:
        raise ValueError("El XMI no contiene clases, interfaces ni enumeraciones.")

    layouts = {}
    raw_ids = {}
    sizes = {}
    edge_raw_ids = {}
    edge_types = {}
    stereotypes = {}
    ea_abstract = {}
    for ext in root.iter():
        if _local(ext.tag) != "Extension" or ext.get("extender") != "UMLCraft":
            continue
        for item in ext.iter():
            if _local(item.tag) == "node" and item.get("subject"):
                layouts[item.get("subject")] = _position(item)
                raw_ids[item.get("subject")] = item.get("rawId")
                if item.get("stereotype"):
                    stereotypes[item.get("subject")] = item.get("stereotype")
                try:
                    sizes[item.get("subject")] = {k: float(item.get(k)) for k in ("width", "height") if item.get(k)}
                except ValueError:
                    pass
            elif _local(item.tag) == "edge" and item.get("subject"):
                edge_raw_ids[item.get("subject")] = item.get("rawId")
                edge_types[item.get("subject")] = item.get("relationType")
    for ext in root.iter():
        if _local(ext.tag) != "Extension" or ext.get("extender") != "Enterprise Architect":
            continue
        for item in ext.iter():
            if _local(item.tag) == "element" and _attr(item, "idref"):
                properties = next((child for child in item if _local(child.tag) == "properties"), None)
                if properties is not None:
                    ea_abstract[_attr(item, "idref")] = properties.get("isAbstract")
    # Las extensiones de EA/Papyrus pueden incluir geometría sin la extensión propia.
    for item in root.iter():
        subject, geometry = item.get("subject"), item.get("geometry", "")
        if subject and subject not in layouts and "Left=" in geometry:
            match_x = re.search(r"Left=(-?\d+)", geometry)
            match_y = re.search(r"Top=(-?\d+)", geometry)
            if match_x and match_y:
                layouts[subject] = {"x": abs(int(match_x.group(1))), "y": abs(int(match_y.group(1)))}

    nodes = []
    mapped = {}
    for index, (eid, (el, kind)) in enumerate(classifiers.items()):
        raw_id = raw_ids.get(eid) or f"class-{uuid.uuid4().hex[:10]}"
        mapped[eid] = raw_id
        abstract_value = el.get("isAbstract") or ea_abstract.get(eid) or "false"
        data_node = {"id": raw_id, "name": el.get("name") or f"Clase{index + 1}", "is_abstract": str(abstract_value).lower() in ("true", "1"), "is_interface": kind == "Interface", "attributes": [], "methods": []}
        if kind == "Enumeration":
            data_node["is_enum"] = True
            data_node["literals"] = [c.get("name", "") for c in el if _local(c.tag) == "ownedLiteral"]
        if eid in stereotypes:
            data_node["stereotype"] = stereotypes[eid]
        for child in el:
            child_kind = _local(child.tag)
            if child_kind == "ownedAttribute" and not child.get("association"):
                ref = _reference(child)
                attr = {"id": f"attr-{uuid.uuid4().hex[:8]}", "name": child.get("name", ""), "visibility": _visibility(child.get("visibility", "private")), "data_type": types.get(ref, ref or "String")}
                mult = _multiplicity(child)
                if mult:
                    attr["multiplicity"] = mult
                default = next((x.get("value", x.text) for x in child if _local(x.tag) == "defaultValue"), None)
                if default is not None:
                    attr["default_value"] = default
                data_node["attributes"].append(attr)
            elif child_kind == "ownedOperation":
                method = {"id": f"method-{uuid.uuid4().hex[:8]}", "name": child.get("name", ""), "visibility": _visibility(child.get("visibility", "public")), "return_type": "void", "parameters": []}
                for par in child:
                    if _local(par.tag) != "ownedParameter":
                        continue
                    ref = _reference(par)
                    if par.get("direction") == "return":
                        method["return_type"] = types.get(ref, ref or "void")
                    else:
                        method["parameters"].append({"name": par.get("name", ""), "direction": par.get("direction", "in"), "data_type": types.get(ref, ref or "String")})
                data_node["methods"].append(method)
        pos = layouts.get(eid) or {"x": 80 + index % 3 * 300, "y": 80 + index // 3 * 240}
        node = {"id": raw_id, "type": "classNode", "position": pos, "data": data_node}
        node.update(sizes.get(eid, {}))
        nodes.append(node)

    edges = []
    used_pairs = set()

    def add_edge(source, target, relation, eid=None, label="", source_mult="", target_mult="", assoc_class=None):
        relation = edge_types.get(eid) or relation
        source, target = mapped.get(_ref(source)), mapped.get(_ref(target))
        if not source or not target:
            warnings.append(f"Se omitió una relación {relation} con un extremo desconocido.")
            return
        if source == target:
            return
        pair = (source, target, relation)
        if pair in used_pairs:
            return
        used_pairs.add(pair)
        edge = {"id": edge_raw_ids.get(eid) or f"edge-{uuid.uuid4().hex[:10]}", "type": "umlEdge", "source": source, "target": target, "data": {"relation_type": relation, "label": label or "", "sourceMultiplicity": source_mult, "targetMultiplicity": target_mult}}
        if assoc_class:
            edge["data"]["associationClassId"] = assoc_class
        edges.append(edge)

    def association(el, kind):
        eid = _attr(el, "id")
        end_ids = (el.get("memberEnd") or "").split()
        ends = [all_by_id.get(ref) for ref in end_ids if all_by_id.get(ref) is not None]
        if len(ends) < 2:
            ends = [all_by_id.get(_ref(_attr(c, "idref") or c.get("href"))) for c in el if _local(c.tag) == "memberEnd"]
            ends = [end for end in ends if end is not None]
        if len(ends) < 2:
            ends = [c for c in el if _local(c.tag) in ("ownedEnd", "memberEnd")]
        if len(ends) < 2:
            warnings.append(f"Se omitió una asociación sin dos extremos: {el.get('name') or eid or 'sin nombre'}.")
            return
        ends = ends[:2]
        refs = [_reference(end) for end in ends]
        mults = [_multiplicity(end) for end in ends]
        aggs = [end.get("aggregation", "none") for end in ends]
        relation = "composition" if "composite" in aggs else "aggregation" if "shared" in aggs else "directed_association" if el.get("navigableOwnedEnd") else "association"
        if aggs[1] in ("composite", "shared"):
            refs.reverse()
            mults.reverse()
        assoc_id = mapped.get(eid) if kind == "AssociationClass" else None
        add_edge(refs[0], refs[1], relation, eid, el.get("name", ""), mults[0], mults[1], assoc_id)

    known = {"Model", "Package", "Class", "Interface", "Enumeration", "AssociationClass", "PrimitiveType", "DataType", "Association", "Dependency", "Realization", "InterfaceRealization", "Abstraction", "Comment", "EnumerationLiteral", "Constraint"}
    for el in root.iter():
        kind = _kind(el).rsplit(":", 1)[-1]
        if kind in ("Association", "AssociationClass"):
            if kind == "Association" or el.get("memberEnd") or any(_local(c.tag) == "ownedEnd" for c in el):
                association(el, kind)
        elif kind in ("Dependency", "Realization", "InterfaceRealization"):
            relation = "dependency" if kind == "Dependency" else "realization"
            add_edge(_reference(el, "client"), _reference(el, "supplier"), relation, _attr(el, "id"), el.get("name", ""))
        elif kind == "Generalization" and el.get("specific"):
            add_edge(_reference(el, "specific"), _reference(el, "general"), "inheritance", _attr(el, "id"))
        elif kind not in known and _local(el.tag) in ("packagedElement", "ownedMember"):
            warnings.append(f"Elemento UML no reconocido: {kind}.")
    for eid, (el, _) in classifiers.items():
        for gen in el:
            if _local(gen.tag) == "generalization":
                add_edge(eid, _reference(gen, "general"), "inheritance", _attr(gen, "id"))
    return {"nodes": nodes, "edges": edges, "warnings": warnings, "version": version}
