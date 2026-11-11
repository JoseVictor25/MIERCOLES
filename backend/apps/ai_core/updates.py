"""Validación de propuestas del asistente contra el diagrama visible."""

TIPOS = {"association", "dependency", "inheritance", "aggregation", "composition", "association_class"}
CAMPOS = {
    "add_class": ("name",), "delete_class": ("name",),
    "rename_class": ("name", "new_name"),
    "add_attribute": ("class_name", "attr_name"),
    "delete_attribute": ("class_name", "attr_name"),
    "add_relation": ("source_class", "target_class", "relation_type"),
    "delete_relation": ("source_class", "target_class"),
    "update_relation_type": ("source_class", "target_class", "relation_type"),
    "set_multiplicity": ("source_class", "target_class", "source_multiplicity", "target_multiplicity"),
}


def validar_updates(diagram, updates):
    """Acepta acciones secuenciales y explica cada descarte."""
    nodes = diagram.get("nodes", []) if isinstance(diagram, dict) else []
    edges = diagram.get("edges", []) if isinstance(diagram, dict) else []
    names = {n.get("data", {}).get("name", "").casefold(): n.get("data", {}).get("name", "") for n in nodes}
    ids = {str(n.get("id")): n.get("data", {}).get("name", "").casefold() for n in nodes}
    relations = {frozenset((ids.get(str(e.get("source"))), ids.get(str(e.get("target")))))
                 for e in edges if ids.get(str(e.get("source"))) and ids.get(str(e.get("target")))}
    attrs = {n.get("data", {}).get("name", "").casefold():
             {a.get("name", "").casefold() for a in n.get("data", {}).get("attributes", [])}
             for n in nodes}
    valid, rejected = [], []
    for update in updates:
        reason = None
        if not isinstance(update, dict) or update.get("action") not in CAMPOS:
            reason = "Acción desconocida."
        else:
            action = update["action"]
            missing = [field for field in CAMPOS[action] if not isinstance(update.get(field), str) or not update[field].strip()]
            if missing:
                reason = f"Faltan campos: {', '.join(missing)}."
            else:
                name = str(update.get("name", "")).casefold()
                cls = str(update.get("class_name", "")).casefold()
                src = str(update.get("source_class", "")).casefold()
                tgt = str(update.get("target_class", "")).casefold()
                pair = frozenset((src, tgt))
                if action == "add_class":
                    if name in names:
                        reason = f"La clase {update['name']} ya existe."
                    else:
                        names[name] = update["name"]
                        attrs[name] = set()
                elif action in {"delete_class", "rename_class"}:
                    if name not in names:
                        reason = f"La clase {update['name']} no existe."
                    elif action == "rename_class" and update["new_name"].casefold() in names:
                        reason = f"La clase {update['new_name']} ya existe."
                    elif action == "delete_class":
                        del names[name]
                        attrs.pop(name, None)
                        relations = {r for r in relations if name not in r}
                    else:
                        new = update["new_name"].casefold()
                        names[new] = update["new_name"]
                        del names[name]
                        attrs[new] = attrs.pop(name, set())
                        relations = {frozenset(new if part == name else part for part in r) for r in relations}
                elif action in {"add_attribute", "delete_attribute"}:
                    if cls not in names:
                        reason = f"La clase {update['class_name']} no existe."
                    elif update["attr_name"].casefold() == "multiplicidad":
                        reason = "La multiplicidad pertenece a una relación, no a un atributo."
                    elif action == "delete_attribute" and update["attr_name"].casefold() not in attrs.get(cls, set()):
                        reason = f"El atributo {update['attr_name']} no existe en {update['class_name']}."
                    elif action == "add_attribute" and update["attr_name"].casefold() in attrs.get(cls, set()):
                        reason = f"El atributo {update['attr_name']} ya existe."
                    elif action == "add_attribute":
                        attrs[cls].add(update["attr_name"].casefold())
                    else:
                        attrs[cls].remove(update["attr_name"].casefold())
                else:
                    if src not in names or tgt not in names:
                        reason = "Una clase de la relación no existe en el diagrama."
                    elif src == tgt:
                        reason = "La relación necesita dos clases distintas."
                    elif action in {"add_relation", "update_relation_type"} and update["relation_type"] not in TIPOS:
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
            rejected.append({"update": update, "reason": reason})
        else:
            valid.append(update)
    return valid, rejected


def resumen(valid, rejected, consejo=""):
    nombres = {"add_class": "agregar clase", "delete_class": "eliminar clase", "rename_class": "renombrar clase",
               "add_attribute": "agregar atributo", "delete_attribute": "eliminar atributo",
               "add_relation": "agregar relación", "delete_relation": "eliminar relación",
               "update_relation_type": "cambiar tipo de relación", "set_multiplicity": "fijar multiplicidades"}
    partes = [f"{nombres[u['action']]} {u.get('name') or u.get('attr_name') or (u.get('source_class', '') + '-' + u.get('target_class', ''))}" for u in valid]
    reply = "Propongo: " + "; ".join(partes) + "." if partes else ("No se aplicaron cambios." if rejected else (consejo or "No propongo cambios."))
    if rejected:
        reply += " No pude hacer: " + "; ".join(item["reason"] for item in rejected)
    return reply
