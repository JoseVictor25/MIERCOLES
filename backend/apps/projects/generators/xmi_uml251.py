"""Intercambio UML 2.5.1 en XMI, sin modificar el exportador 2.1 heredado."""

import hashlib
import xml.etree.ElementTree as ET

XMI = "http://www.omg.org/spec/XMI/20131001"
UML = "http://www.omg.org/spec/UML/20161101"
ET.register_namespace("xmi", XMI)
ET.register_namespace("uml", UML)
XI = lambda name: f"{{{XMI}}}{name}"


def _id(prefix, value):
    texto = str(value)
    return f"{prefix}_{hashlib.sha1(texto.encode('utf-8')).hexdigest()[:16]}"


def _vis(value):
    return {"+": "public", "-": "private", "#": "protected", "~": "package"}.get(value, value if value in {"public", "private", "protected", "package"} else "public")


def _multiplicidad(parent, value, id_base):
    if value in (None, ""):
        return
    partes = str(value).replace("-1", "*").split("..")
    inferior, superior = (partes[0], partes[0]) if len(partes) == 1 else (partes[0], partes[1])
    if inferior == "*":
        inferior = "0"
    ET.SubElement(parent, "lowerValue", {XI("type"): "uml:LiteralInteger", XI("id"): f"{id_base}_lower", "value": inferior})
    ET.SubElement(parent, "upperValue", {XI("type"): "uml:LiteralUnlimitedNatural", XI("id"): f"{id_base}_upper", "value": superior})


def generate_xmi_251(diagram_data, project_name):
    """Exporta los elementos visibles y sus coordenadas originales."""
    nodes = diagram_data.get("nodes", [])
    edges = diagram_data.get("edges", [])
    root = ET.Element(XI("XMI"), {XI("version"): "2.5.1"})
    ET.SubElement(root, XI("Documentation"), {"exporter": "UMLCraft", "exporterVersion": "2.5.1"})
    model = ET.SubElement(root, f"{{{UML}}}Model", {XI("id"): _id("model", project_name), "name": "UMLCraft"})
    package = ET.SubElement(model, "packagedElement", {XI("type"): "uml:Package", XI("id"): _id("package", project_name), "name": project_name or "Modelo"})
    node_ids = {str(n.get("id")): _id("node", n.get("id")) for n in nodes}
    names = {str(n.get("data", {}).get("name", "")): node_ids[str(n.get("id"))] for n in nodes}
    assoc_class = {str(e.get("data", {}).get("associationClassId")): e for e in edges if e.get("data", {}).get("associationClassId")}
    edge_subject = {str(e.get("id")): node_ids.get(str(e.get("data", {}).get("associationClassId"))) or _id("edge", e.get("id")) for e in edges}
    primitive = {}
    for n in nodes:
        data = n.get("data", {})
        for item in data.get("attributes", []):
            tipo = item.get("data_type")
            if tipo and tipo not in names:
                primitive[str(tipo)] = _id("type", tipo)
        for item in data.get("methods", []):
            for tipo in [item.get("return_type"), *[p.get("data_type") or p.get("type") for p in item.get("parameters", [])]]:
                if tipo and tipo not in names and tipo != "void":
                    primitive[str(tipo)] = _id("type", tipo)
    for name, ref in primitive.items():
        ET.SubElement(package, "packagedElement", {XI("type"): "uml:PrimitiveType", XI("id"): ref, "name": name})

    def tipo_ref(tipo):
        return names.get(str(tipo)) or primitive.get(str(tipo))

    for n in nodes:
        raw = str(n.get("id"))
        data = n.get("data", {})
        kind = "uml:AssociationClass" if raw in assoc_class else "uml:Enumeration" if data.get("is_enum") or data.get("type") in ("enum", "enumeration") else "uml:Interface" if data.get("is_interface") or data.get("type") == "interface" else "uml:Class"
        attrs = {XI("type"): kind, XI("id"): node_ids[raw], "name": str(data.get("name") or "Clase"), "visibility": _vis(data.get("visibility", "+"))}
        if kind in ("uml:Class", "uml:AssociationClass") and data.get("is_abstract"):
            attrs["isAbstract"] = "true"
        element = ET.SubElement(package, "packagedElement", attrs)
        if kind == "uml:AssociationClass":
            assoc_edge = assoc_class[raw]
            eid = _id("edge", assoc_edge.get("id"))
            element.set("memberEnd", f"{eid}_source {eid}_target")
        for j, literal in enumerate(data.get("literals", [])):
            ET.SubElement(element, "ownedLiteral", {XI("type"): "uml:EnumerationLiteral", XI("id"): _id("literal", f"{raw}:{j}"), "name": str(literal.get("name") if isinstance(literal, dict) else literal)})
        for j, attr in enumerate(data.get("attributes", [])):
            aid = _id("attribute", f"{raw}:{attr.get('id', j)}")
            props = {XI("type"): "uml:Property", XI("id"): aid, "name": str(attr.get("name", "")), "visibility": _vis(attr.get("visibility", "-"))}
            item = ET.SubElement(element, "ownedAttribute", props)
            if tipo_ref(attr.get("data_type")):
                ET.SubElement(item, "type", {XI("idref"): tipo_ref(attr.get("data_type"))})
            _multiplicidad(item, attr.get("multiplicity", "1"), aid)
            default = attr.get("default_value", attr.get("defaultValue"))
            if default is not None:
                ET.SubElement(item, "defaultValue", {XI("type"): "uml:LiteralString", XI("id"): f"{aid}_default", "value": str(default)})
        for j, method in enumerate(data.get("methods", [])):
            mid = _id("operation", f"{raw}:{method.get('id', j)}")
            op = ET.SubElement(element, "ownedOperation", {XI("type"): "uml:Operation", XI("id"): mid, "name": str(method.get("name", "")), "visibility": _vis(method.get("visibility", "+"))})
            for k, p in enumerate(method.get("parameters", [])):
                par = {XI("type"): "uml:Parameter", XI("id"): f"{mid}_param_{k}", "name": str(p.get("name", "")), "direction": str(p.get("direction", "in"))}
                ref = tipo_ref(p.get("data_type") or p.get("type"))
                parameter = ET.SubElement(op, "ownedParameter", par)
                if ref:
                    ET.SubElement(parameter, "type", {XI("idref"): ref})
            ret = method.get("return_type")
            if ret and ret != "void":
                parameter = ET.SubElement(op, "ownedParameter", {XI("type"): "uml:Parameter", XI("id"): f"{mid}_return", "direction": "return"})
                ET.SubElement(parameter, "type", {XI("idref"): tipo_ref(ret)})
        for e in edges:
            if e.get("data", {}).get("relation_type") == "inheritance" and str(e.get("source")) == raw and str(e.get("target")) in node_ids:
                ET.SubElement(element, "generalization", {XI("type"): "uml:Generalization", XI("id"): _id("edge", e.get("id")), "general": node_ids[str(e["target"])]})

    for e in edges:
        src, tgt = node_ids.get(str(e.get("source"))), node_ids.get(str(e.get("target")))
        if not src or not tgt:
            continue
        data = e.get("data", {})
        rel = data.get("relation_type", "association")
        eid = _id("edge", e.get("id"))
        if rel == "inheritance":
            continue
        if rel in ("dependency", "realization"):
            kind = "uml:InterfaceRealization" if rel == "realization" and next((n for n in nodes if node_ids[str(n.get("id"))] == tgt), {}).get("data", {}).get("is_interface") else "uml:Realization" if rel == "realization" else "uml:Dependency"
            ET.SubElement(package, "packagedElement", {XI("type"): kind, XI("id"): eid, "name": str(data.get("label", "")), "client": src, "supplier": tgt})
            continue
        if rel not in ("association", "directed_association", "aggregation", "composition", "association_class"):
            continue
        assoc = next((n for n in nodes if str(n.get("id")) == str(data.get("associationClassId"))), None)
        parent = next((p for p in package if p.get(XI("id")) == node_ids.get(str(assoc.get("id")))), None) if assoc else None
        if parent is None:
            parent = ET.SubElement(package, "packagedElement", {XI("type"): "uml:Association", XI("id"): eid, "name": str(data.get("label", ""))})
        parent.set("memberEnd", f"{eid}_source {eid}_target")
        for side, ref, mult in (("source", src, data.get("sourceMultiplicity", "")), ("target", tgt, data.get("targetMultiplicity", ""))):
            prop = {XI("type"): "uml:Property", XI("id"): f"{eid}_{side}", "type": ref, "association": parent.get(XI("id"))}
            if side == "source" and rel in ("aggregation", "composition"):
                prop["aggregation"] = "shared" if rel == "aggregation" else "composite"
            end = ET.SubElement(parent, "ownedEnd", prop)
            _multiplicidad(end, mult, f"{eid}_{side}")
        if rel == "directed_association":
            parent.set("navigableOwnedEnd", f"{eid}_target")

    ext = ET.SubElement(root, XI("Extension"), {"extender": "UMLCraft"})
    layout = ET.SubElement(ext, "diagram")
    for n in nodes:
        pos = n.get("position", {})
        attrs = {"subject": node_ids[str(n.get("id"))], "rawId": str(n.get("id")), "x": str(pos.get("x", 80)), "y": str(pos.get("y", 80))}
        if n.get("width") is not None:
            attrs["width"] = str(n["width"])
        if n.get("height") is not None:
            attrs["height"] = str(n["height"])
        if n.get("data", {}).get("stereotype"):
            attrs["stereotype"] = str(n["data"]["stereotype"])
        ET.SubElement(layout, "node", attrs)
    for e in edges:
        ET.SubElement(layout, "edge", {"subject": edge_subject[str(e.get("id"))], "rawId": str(e.get("id")), "relationType": str(e.get("data", {}).get("relation_type", "association"))})
    # Extensión de diagramas de EA: permite abrir el diagrama ya dispuesto en el Browser.
    ea = ET.SubElement(root, XI("Extension"), {"extender": "Enterprise Architect", "extenderID": "6.5"})
    ea_elements = ET.SubElement(ea, "elements")
    package_meta = ET.SubElement(ea_elements, "element", {XI("idref"): package.get(XI("id")), XI("type"): "uml:Package", "name": project_name or "Modelo", "scope": "public"})
    ET.SubElement(package_meta, "model", {"package2": package.get(XI("id")), "package": model.get(XI("id")), "ea_eleType": "package"})
    ET.SubElement(package_meta, "properties", {"sType": "Package", "scope": "public"})
    for n in nodes:
        raw = str(n.get("id"))
        kind = "Interface" if n.get("data", {}).get("is_interface") else "Enumeration" if n.get("data", {}).get("is_enum") else "AssociationClass" if raw in assoc_class else "Class"
        element = ET.SubElement(ea_elements, "element", {XI("idref"): node_ids[raw], XI("type"): f"uml:{kind}", "name": str(n.get("data", {}).get("name", "")), "scope": "public"})
        ET.SubElement(element, "model", {"package": package.get(XI("id")), "ea_eleType": "element"})
        properties = {"sType": kind, "scope": "public"}
        if n.get("data", {}).get("is_abstract"):
            properties["isAbstract"] = "true"
        ET.SubElement(element, "properties", properties)
        ET.SubElement(element, "extendedProperties", {"package_name": project_name or "Modelo"})
    connectors = ET.SubElement(ea, "connectors")
    for e in edges:
        src, tgt = node_ids.get(str(e.get("source"))), node_ids.get(str(e.get("target")))
        if not src or not tgt:
            continue
        rel = e.get("data", {}).get("relation_type", "association")
        conn = ET.SubElement(connectors, "connector", {XI("idref"): edge_subject[str(e.get("id"))]})
        for side, ref, mult in (("source", src, e.get("data", {}).get("sourceMultiplicity", "")), ("target", tgt, e.get("data", {}).get("targetMultiplicity", ""))):
            endpoint = ET.SubElement(conn, side, {XI("idref"): ref})
            ET.SubElement(endpoint, "type", {"aggregation": ("shared" if rel == "aggregation" else "composite" if rel == "composition" else "none") if side == "source" else "none", "multiplicity": str(mult)})
        ea_type = {"inheritance": "Generalization", "dependency": "Dependency", "realization": "Realisation", "aggregation": "Aggregation", "composition": "Aggregation"}.get(rel, "Association")
        ET.SubElement(conn, "properties", {"ea_type": ea_type, "name": str(e.get("data", {}).get("label", "")), "direction": "Source -> Destination" if rel in ("inheritance", "dependency", "realization", "directed_association") else "Unspecified"})
    diagrams = ET.SubElement(ea, "diagrams")
    diagram = ET.SubElement(diagrams, "diagram", {XI("id"): _id("diagram", project_name)})
    ET.SubElement(diagram, "model", {"package": package.get(XI("id")), "owner": package.get(XI("id"))})
    ET.SubElement(diagram, "properties", {"name": project_name or "Modelo", "type": "Logical"})
    placed = ET.SubElement(diagram, "elements")
    for n in nodes:
        pos = n.get("position", {})
        x, y = int(float(pos.get("x", 80))), int(float(pos.get("y", 80)))
        w, h = int(float(n.get("width") or 180)), int(float(n.get("height") or 100))
        ET.SubElement(placed, "element", {"subject": node_ids[str(n.get("id"))], "geometry": f"Left={x};Top={y};Right={x+w};Bottom={y+h};"})
    for e in edges:
        ET.SubElement(placed, "element", {"subject": edge_subject[str(e.get("id"))], "geometry": "SX=0;SY=0;EX=0;EY=0;Path=;"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
