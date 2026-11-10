# Modelo de datos actual

El modelo persistido se define en `backend/apps/accounts/models.py` y
`backend/apps/projects/models.py`. Django crea y actualiza el esquema mediante
`python manage.py migrate`; este documento no sustituye las migraciones.

| Modelo | Tabla | Campos propios principales |
| --- | --- | --- |
| `User` | `usuario` | Campos de `AbstractUser`, `email` único, `avatar`, `created_at` |
| `Project` | `proyecto` | `name`, `description`, `owner`, `datos_diagrama` (JSON), `created_at`, `updated_at` |
| `ProjectCollaborator` | `detalle_proyecto` | `project`, `user`, `role` (`editor` o `viewer`), `joined_at` |
| `DiagramSnapshot` | `diagrama_snapshot` | `project`, `saved_by`, `diagram_data` (JSON), `label`, `created_at` |

El dueño está representado por `Project.owner`; no existe un rol de colaborador
`owner`. Cada pareja proyecto-usuario puede aparecer una sola vez en
`ProjectCollaborator`. Las clases y relaciones del lienzo se guardan dentro de
`Project.datos_diagrama` como `nodes` y `edges`.

El diagrama PlantUML equivalente está en `class_diagram.puml`.
