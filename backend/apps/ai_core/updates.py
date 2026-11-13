"""Normalización y validación de propuestas contra el diagrama visible."""

import unicodedata

TIPOS = {"association", "directed_association", "dependency", "aggregation", "composition",
         "inheritance", "realization", "association_class"}
CAMPOS = {
    "add_class": ("name",), "delete_class": ("name",), "rename_class": ("name", "new_name"),
    "set_abstract": ("name",), "add_attribute": ("class_name", "attr_name"),
    "delete_attribute": ("class_name", "attr_name"), "update_attribute": ("class_name", "attr_name"),
    "reorder_attributes": ("class_name",), "add_method": ("class_name", "method_name"),
    "delete_method": ("class_name", "method_name"), "add_relation": ("source_class", "target_class"),
    "delete_relation": ("source_class", "target_class"),
    "update_relation_type": ("source_class", "target_class", "relation_type"),
    "set_multiplicity": ("source_class", "target_class", "source_multiplicity", "target_multiplicity"),
}


def _plain(value):
    return "".join(c for c in unicodedata.normalize("NFD", str(value or "").lower())
                   if unicodedata.category(c) != "Mn").strip()


def _relation_type(value):
    key = _plain(value).replace("_", " ").replace("-", " ")
    aliases = {
        "asociacion": "association", "association": "association", "relationship": "association",
        "asociacion dirigida": "directed_association", "dirigida": "directed_association",
        "directed": "directed_association", "directed association": "directed_association",
        "dependencia": "dependency", "depende": "dependency", "dependency": "dependency",
        "agregacion": "aggregation", "aggregation": "aggregation",
        "composicion": "composition", "composition": "composition",
        "herencia": "inheritance", "hereda": "inheritance", "generalizacion": "inheritance",
        "extiende": "inheritance", "extends": "inheritance", "inherits": "inheritance",
        "generalization": "inheritance", "inheritance": "inheritance",
        "realizacion": "realization", "implementa": "realization", "implements": "realization",
        "realization": "realization",
        "clase de asociacion": "association_class", "association class": "association_class",
    }
    return aliases.get(key, key.replace(" ", "_"))


def normalizar_updates(updates):
    """Acepta sinónimos del modelo y descompone listas de atributos."""
    result = []
    for original in updates if isinstance(updates, list) else []:
        if not isinstance(original, dict):
            result.append(original)
            continue
        update = dict(original)
        action = update.get("action")
        aliases = {"class": "class_name", "from": "source_class", "source": "source_class",
                   "to": "target_class", "target": "target_class",
                   "multiplicidad_origen": "source_multiplicity", "multiplicidad_destino": "target_multiplicity"}
        if action in ("add_attribute", "delete_attribute", "update_attribute"):
            aliases.update(attribute_name="attr_name", type="data_type")
            if "attr_name" not in update and "name" in update:
                aliases["name"] = "attr_name"
        for old, new in aliases.items():
            if old in update and new not in update:
                update[new] = update.pop(old)
        if action in ("add_relation", "update_relation_type"):
            update["relation_type"] = _relation_type(update.get("relation_type") or
                ("association" if action == "add_relation" else ""))
        if action == "set_abstract" and isinstance(update.get("is_abstract"), str):
            update["is_abstract"] = _plain(update["is_abstract"]) in ("true", "1", "si", "yes")
        if action == "add_attribute" and isinstance(update.get("attributes"), list):
            for attr in update["attributes"]:
                if isinstance(attr, dict):
                    result.append({**{k: v for k, v in update.items() if k != "attributes"},
                                   "attr_name": attr.get("attr_name") or attr.get("attribute_name") or attr.get("name"),
                                   "data_type": attr.get("data_type") or attr.get("type") or update.get("data_type", "String"),
                                   "visibility": attr.get("visibility", update.get("visibility", "-"))})
            continue
        if action == "add_attribute" and isinstance(update.get("attr_names"), list):
            for name in update["attr_names"]:
                result.append({**{k: v for k, v in update.items() if k != "attr_names"}, "attr_name": name})
            continue
        result.append(update)
    return result


def validar_updates(diagram, updates):
    """Acepta acciones secuenciales y explica cada descarte sin perder las válidas."""
    nodes = diagram.get("nodes", []) if isinstance(diagram, dict) else []
    edges = diagram.get("edges", []) if isinstance(diagram, dict) else []
    names = {n.get("data", {}).get("name", "").casefold(): n.get("data", {}).get("name", "") for n in nodes}
    ids = {str(n.get("id")): n.get("data", {}).get("name", "").casefold() for n in nodes}
    relations = {frozenset((ids.get(str(e.get("source"))), ids.get(str(e.get("target")))))
                 for e in edges if ids.get(str(e.get("source"))) and ids.get(str(e.get("target")))}
    attrs = {n.get("data", {}).get("name", "").casefold():
             [a.get("name", "") for a in n.get("data", {}).get("attributes", [])] for n in nodes}
    methods = {n.get("data", {}).get("name", "").casefold():
               [m.get("name", "") for m in n.get("data", {}).get("methods", [])] for n in nodes}
    abstract = {n.get("data", {}).get("name", "").casefold(): bool(n.get("data", {}).get("is_abstract")) for n in nodes}
    valid, rejected = [], []
    for update in normalizar_updates(updates):
        reason = code = None
        if not isinstance(update, dict) or update.get("action") not in CAMPOS:
            reason = "Acción desconocida."
        else:
            action = update["action"]
            missing = [field for field in CAMPOS[action]
                       if not isinstance(update.get(field), str) or not update[field].strip()]
            if missing:
                reason = f"Faltan campos: {', '.join(missing)}."
            else:
                name = str(update.get("name", "")).casefold()
                cls = str(update.get("class_name", "")).casefold()
                src = str(update.get("source_class", "")).casefold()
                tgt = str(update.get("target_class", "")).casefold()
                pair = frozenset((src, tgt))
                attr_name = str(update.get("attr_name", "")).casefold()
                method_name = str(update.get("method_name", "")).casefold()
                if action == "add_class":
                    if name in names:
                        reason = f"La clase {update['name']} ya existe."
                    else:
                        names[name] = update["name"]
                        attrs[name], methods[name], abstract[name] = [], [], False
                elif action in ("delete_class", "rename_class", "set_abstract"):
                    if name not in names:
                        reason = f"La clase {update['name']} no existe."
                    elif action == "delete_class":
                        del names[name]
                        attrs.pop(name, None)
                        methods.pop(name, None)
                        abstract.pop(name, None)
                        relations = {r for r in relations if name not in r}
                    elif action == "rename_class":
                        new = update["new_name"].casefold()
                        if new in names:
                            reason = f"La clase {update['new_name']} ya existe."
                        else:
                            names[new] = update["new_name"]
                            del names[name]
                            attrs[new] = attrs.pop(name, [])
                            methods[new] = methods.pop(name, [])
                            abstract[new] = abstract.pop(name, False)
                            relations = {frozenset(new if part == name else part for part in r) for r in relations}
                    elif not isinstance(update.get("is_abstract"), bool):
                        reason = "is_abstract debe ser verdadero o falso."
                    elif abstract[name] == update["is_abstract"]:
                        reason = "La clase ya tiene ese estado abstracto."
                    else:
                        abstract[name] = update["is_abstract"]
                elif action in ("add_attribute", "delete_attribute", "update_attribute", "reorder_attributes"):
                    if cls not in names:
                        reason = f"La clase {update['class_name']} no existe."
                    elif action == "reorder_attributes":
                        order = update.get("order")
                        if not isinstance(order, list) or not any(isinstance(item, str) and item.strip() for item in order):
                            reason = "Indica el orden de los atributos."
                        else:
                            existing = attrs[cls]
                            by_name = {item.casefold(): item for item in existing}
                            requested = []
                            for item in order:
                                key = str(item).casefold()
                                if key in by_name and key not in requested:
                                    requested.append(key)
                            final = [by_name[key] for key in requested]
                            final += [item for item in existing if item.casefold() not in requested]
                            if final == existing:
                                reason = "Los atributos ya están en ese orden."
                            else:
                                update["order"] = final
                                attrs[cls] = final
                    elif attr_name == "multiplicidad":
                        reason = "La multiplicidad pertenece a una relación, no a un atributo."
                    elif action == "add_attribute" and attr_name in {a.casefold() for a in attrs[cls]}:
                        reason = f"Ya existía: {update['attr_name']} en {update['class_name']}."
                        code = "duplicate_attribute"
                    elif action == "delete_attribute" and attr_name not in {a.casefold() for a in attrs[cls]}:
                        reason = f"El atributo {update['attr_name']} no existe en {update['class_name']}."
                    elif action == "add_attribute":
                        attrs[cls].append(update["attr_name"])
                    elif action == "delete_attribute":
                        attrs[cls] = [a for a in attrs[cls] if a.casefold() != attr_name]
                    elif action == "update_attribute":
                        if attr_name not in {a.casefold() for a in attrs[cls]}:
                            reason = f"El atributo {update['attr_name']} no existe en {update['class_name']}."
                        elif not any(update.get(field) for field in ("new_name", "data_type", "visibility")):
                            reason = "Indica qué propiedad del atributo cambiar."
                        elif update.get("new_name") and update["new_name"].casefold() in {a.casefold() for a in attrs[cls] if a.casefold() != attr_name}:
                            reason = f"El atributo {update['new_name']} ya existe."
                        elif update.get("visibility") and update["visibility"] not in ("+", "-", "#", "~"):
                            reason = "Visibilidad de atributo no válida."
                        elif update.get("new_name"):
                            attrs[cls] = [update["new_name"] if a.casefold() == attr_name else a for a in attrs[cls]]
                elif action in ("add_method", "delete_method"):
                    if cls not in names:
                        reason = f"La clase {update['class_name']} no existe."
                    elif action == "add_method" and method_name in {m.casefold() for m in methods[cls]}:
                        reason = f"El método {update['method_name']} ya existe."
                    elif action == "delete_method" and method_name not in {m.casefold() for m in methods[cls]}:
                        reason = f"El método {update['method_name']} no existe."
                    elif action == "add_method":
                        methods[cls].append(update["method_name"])
                    else:
                        methods[cls] = [m for m in methods[cls] if m.casefold() != method_name]
                else:
                    if src not in names or tgt not in names:
                        reason = "Una clase de la relación no existe en el diagrama."
                    elif src == tgt:
                        reason = "La relación necesita dos clases distintas."
                    elif action in ("add_relation", "update_relation_type") and update["relation_type"] not in TIPOS:
                        reason = "Tipo de relación no admitido."
                    elif action == "add_relation" and pair in relations:
                        reason = "La relación ya existe."
                    elif action != "add_relation" and pair not in relations:
                        reason = "La relación entre esas clases no existe."
                    elif action == "add_relation":
                        relations.add(pair)
                    elif action == "delete_relation":
                        relations.remove(pair)
        if reason:
            item = {"update": update, "reason": reason}
            if code:
                item["code"] = code
            rejected.append(item)
        else:
            valid.append(update)
    return valid, rejected


def resumen(valid, rejected, consejo=""):
    nombres = {"add_class": "agregar clase", "delete_class": "eliminar clase", "rename_class": "renombrar clase",
               "add_attribute": "agregar atributo", "delete_attribute": "eliminar atributo",
               "update_attribute": "modificar atributo", "reorder_attributes": "ordenar atributos de",
               "add_method": "agregar método", "delete_method": "eliminar método", "set_abstract": "cambiar abstracción de",
               "add_relation": "agregar relación", "delete_relation": "eliminar relación",
               "update_relation_type": "cambiar tipo de relación", "set_multiplicity": "fijar multiplicidades"}
    parts = [f"{nombres[u['action']]} {u.get('name') or u.get('attr_name') or u.get('method_name') or u.get('class_name') or (u.get('source_class', '') + '-' + u.get('target_class', ''))}" for u in valid]
    omitted = [item for item in rejected if item.get("code") == "duplicate_attribute"]
    other = [item for item in rejected if item.get("code") != "duplicate_attribute"]
    if parts:
        reply = "Propongo: " + "; ".join(parts) + "."
        if omitted:
            reply += " Atributos omitidos (ya existían): " + ", ".join(item["update"]["attr_name"] for item in omitted) + "."
        if other:
            reply += " No pude hacer: " + "; ".join(item["reason"] for item in other)
        return reply
    if rejected:
        return "No pude proponer cambios: " + "; ".join(item["reason"] for item in rejected)
    return consejo or "No propongo cambios."
