# UMLCraft

Editor colaborativo de diagramas de clases UML con backend Django/Channels y frontend React/Vite. El diagrama se guarda como JSON en cada proyecto. Puede exportarse a XMI o descargarse como un backend Java/Spring Boot en ZIP.

## Requisitos

- Python compatible con Django 6.1 (probado con Python 3.13)
- Node.js y npm compatibles con Vite 8
- PostgreSQL es opcional; SQLite funciona sin servidor adicional

## Backend

Desde `backend/`, crea un entorno virtual, instálalo y migra:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\daphne.exe -b 127.0.0.1 -p 8000 config.asgi:application
```

En Linux o macOS usa `source venv/bin/activate`, `cp .env.example .env`, `python manage.py migrate` y `daphne -b 127.0.0.1 -p 8000 config.asgi:application`.

`backend/.env.example` habilita desarrollo con `DEBUG=True` y una clave de ejemplo: reemplázala. Si `DEBUG=False`, `SECRET_KEY` es obligatoria. El esquema se crea con `manage.py migrate`; no se usa un script SQL manual. La IA usa un servidor local compatible con OpenAI.

### PostgreSQL opcional

Define `DB_ENGINE=django.db.backends.postgresql` y `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` en `backend/.env`. Crea primero la base de datos y ejecuta `python manage.py migrate`. La configuración SQLite usa `backend/db.sqlite3` y es la opción por defecto.

## Frontend

Desde `frontend/`:

```powershell
npm install
Copy-Item .env.example .env
npm run dev
```

Abre la URL que muestre Vite, habitualmente `http://localhost:5173`. Para verificar la compilación: `npm run build`. `VITE_API_URL` y `VITE_WS_URL` son opcionales; los valores locales por defecto son `http://localhost:8000/api/` y `ws://localhost:8000`. Ajusta `CORS_ALLOWED_ORIGINS` si Vite usa otro origen. En un host remoto, el cliente puede usar `/api/` y el origen WebSocket del navegador si un proxy los encamina.

## Comprobaciones

```powershell
# backend/
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
# frontend/
npm run build
```

El generador Spring Boot usa `backend/apps/generator/engine.py` con plantillas Jinja2. Genera herencia JOINED, relaciones 1..N con clave foránea en el lado muchos y N..M con entidad de asociación cuando el diagrama enlaza `associationClassId`. Conserva los atributos de esa clase. Las autorrelaciones ambiguas se omiten con avisos en el log y en el README del ZIP; para generarlas se requieren `sourceRole` y `targetRole`. El editor avisa si se intenta conectar una clase consigo misma. Si falla el JavaDoc asistido, el ZIP se genera con un aviso.

Antes de generar desde el modal, el editor guarda el estado visible. Si ese guardado falla, no solicita el ZIP. La colaboración usa una capa de canales en memoria y requiere un solo proceso. Lee `RESUMEN_GENERAL_SOFTWARE.md` para los demás permisos y límites actuales.

## IA local

En LM Studio, descarga o importa los modelos de texto y visi?n, activa el servidor local en el puerto 1235 y habilita la carga bajo demanda. Consulta `http://localhost:1235/v1/models` y copia los identificadores reales en `backend/.env`. El primer pedido puede tardar mientras se carga el modelo (GPU de 4 GB).

```dotenv
LLM_BASE_URL=http://localhost:1235/v1
LLM_TEXT_MODEL=qwen2.5-3b-instruct
LLM_VISION_MODEL=qwen2.5-vl-3b-instruct
LLM_API_KEY=lm-studio
LLM_TIMEOUT=180
```

Reinicia Django después de cambiar variables. Para Ollama usa `LLM_BASE_URL=http://localhost:11434/v1` y los nombres que entregue `GET /v1/models`; vLLM usa su URL compatible. `GET /api/ai/diagnose/` requiere autenticación y muestra la disponibilidad del servidor y modelos.


## Intercambio XMI/XML

El menú Archivo exporta XMI UML 2.5.1 por defecto (namespaces OMG XMI 20131001 y UML 20161101). La opción XMI 2.1 conserva el exportador anterior. La importación muestra una vista previa sin guardar; dueño y editores pueden agregar el contenido al diagrama actual o reemplazarlo. Al agregar, los nombres duplicados reciben un sufijo y los nodos se desplazan. El resultado se guarda y se difunde por la sincronización habitual.

En Enterprise Architect, crea o abre un proyecto y usa **Publish > Model Exchange > Import > XMI File** para elegir el archivo `_uml251.xmi`. El paquete contiene clases, relaciones y un diagrama; la extensión de UMLCraft conserva coordenadas exactas para volver a importar aquí. EA puede ignorar esa extensión y usar su propia disposición. Se aceptan XMI UML 2.5.1, 2.4.1 y 2.1 de herramientas como EA, StarUML y Papyrus cuando usan referencias UML estándar. Los perfiles y elementos propietarios no reconocidos se omiten con advertencias. La vista previa limita cada archivo a 5 MB y rechaza DTD y entidades XML.

La documentación de EA enumera oficialmente XMI 2.1 para UML 2.x; si tu versión no acepta el archivo 2.5.1, usa **Exportar XMI 2.1 (compatibilidad)**. Al importar, activa **Import Diagrams** para incluir el diagrama. La compatibilidad del archivo 2.5.1 con una instalación concreta de EA requiere verificación en esa versión.
