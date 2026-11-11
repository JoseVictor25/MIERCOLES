# UMLCraft: resumen del software implementado

## Propósito y arquitectura

UMLCraft es una aplicación web para crear diagramas de clases UML en equipo. El frontend es una SPA de React 19, Vite 8, `@xyflow/react`, Axios y Zustand. El backend usa Django 6.1, Django REST Framework, Simple JWT, Channels y Daphne. El servidor guarda el diagrama de cada proyecto como JSON (`nodes` y `edges`) en `Project.datos_diagrama`. SQLite es el motor por defecto; PostgreSQL es opcional.

La aplicación arranca en `backend/config/`. No hay configuración de AWS, Nginx ni systemd en este repositorio. Desplegarla en esa infraestructura es una propuesta, no una instalación comprobada aquí. El layer de Channels es `InMemoryChannelLayer`: la colaboración solo funciona entre conexiones del mismo proceso. Para varios procesos haría falta una capa compartida, por ejemplo Redis con `channels_redis`.

## Cuentas, proyectos y permisos

La API permite registrar usuarios, iniciar sesión con JWT, refrescar tokens y consultar el usuario actual. Un usuario puede crear proyectos, cambiar nombre y descripción y eliminar sus proyectos. Se pueden añadir colaboradores existentes por email o usuario. Los roles de colaborador son `editor` y `viewer`; el dueño se representa con `Project.owner`, no con un tercer rol. Los editores pueden guardar, importar y restaurar diagramas; los visualizadores pueden leer. Los administradores tienen acceso adicional en algunas vistas HTTP.

El backend mantiene snapshots manuales y automáticos. Al guardar un diagrama cambiado, guarda el estado anterior; esa ruta intenta conservar los últimos 20. Los snapshots manuales y los creados al restaurar o importar no aplican el mismo límite. El esquema se crea exclusivamente mediante migraciones Django (`python manage.py migrate`). `apps.diagrams` y sus migraciones siguen en el repositorio como legado no instalado; una SQLite local antigua puede conservar datos de esa app.

## Editor y colaboración

El editor muestra clases con nombre, estereotipo, visibilidad, atributos y métodos. Permite mover y redimensionar nodos, dibujar relaciones UML, ajustar multiplicidades, usar minimapa y controles, deshacer y rehacer, exportar el lienzo a PNG, y exportar o importar XMI. El código genera XMI 2.1 con extensiones de Enterprise Architect e interpreta varias estructuras XMI; la compatibilidad completa de ida y vuelta con herramientas externas requiere pruebas externas.

Cada cliente conectado a `/ws/diagram/<id>/` se une al grupo `diagram_<id>`. El backend difunde presencia, cursores y estados completos del diagrama. El frontend aplica debounce a los cambios y reconecta. Un colaborador `viewer` puede recibir eventos, pero el servidor ignora sus mensajes `diagram_update` y `cursor_move`. No hay resolución de conflictos entre ediciones simultáneas. El JWT del WebSocket viaja actualmente en `?token=...`; cambiar ese transporte está pendiente.

## Inteligencia artificial

El proyecto tiene un chat de equipo persistente en `apps.chat`. Los mensajes se guardan en `chat_mensaje` y se distribuyen por el WebSocket del diagrama a todos los miembros, incluido el autor. Dueño y editores pueden escribir; los visualizadores solo leen. `GET /api/projects/<id>/chat/` entrega las últimas 50 entradas, admite `before` para cargar anteriores y `after` para recuperar mensajes tras una reconexión. El panel del editor separa el chat de equipo del asistente IA privado.
La IA del equipo responde a mensajes con `@ia` escritos por el dueño o un editor. El dueño configura su disponibilidad, personalidad y modo en el panel o mediante `GET/PATCH /api/projects/<id>/ai-settings/`. En modo consejero responde sin acciones; en modo proponente puede publicar cambios pendientes que solo el solicitante aprueba o rechaza. El cliente aplica una propuesta aprobada y comunica el resultado al servidor. Las respuestas se guardan con `reply_to_user` para conservar el contexto individual de cada miembro. La cola local procesa una consulta a la vez y admite hasta cinco en espera por proceso. Tanto la cola de IA como `InMemoryChannelLayer` requieren un solo proceso; con varios procesos harían falta Redis para los canales y una cola compartida para la IA. El panel muestra a la IA en presencia, distingue mensajes dirigidos al usuario y presenta propuestas con acciones y resultados.

`apps.ai_core` ofrece sugerencias, ayuda, extracción UML desde imágenes y diagnóstico mediante una API local compatible con OpenAI. `backend/apps/ai_core/llm.py` centraliza el acceso. Inicia el servidor local de LM Studio en el puerto 1235, consulta `GET http://localhost:1235/v1/models` y configura en `backend/.env` los identificadores `LLM_TEXT_MODEL` y `LLM_VISION_MODEL`, junto a `LLM_BASE_URL`, `LLM_API_KEY` y `LLM_TIMEOUT`. Para Ollama cambia la URL a `http://localhost:11434/v1`; vLLM también funciona con su URL compatible. La primera respuesta puede tardar mientras se carga el modelo.

## Generación de código

`POST /api/projects/<id>/generate/spring-boot/` usa `apps.generator.engine.SpringGenerator` y descarga un ZIP con un proyecto Java/Spring Boot. Por cada clase genera entidad, DTOs de entrada y salida, mapper, repositorio, servicio y controlador, además de `pom.xml`, `application.properties` y un README. La opción `include_ai_docs` intenta añadir JavaDoc y anotaciones Swagger mediante la IA local; si falla, el ZIP se genera con un aviso. No genera proyectos Python, TypeScript ni SQL DDL independiente.

El generador interpreta herencia con `extends` y `@Inheritance(JOINED)`; en 1..N coloca la clave foránea en el lado muchos. En N..M sin clase de asociación usa `@ManyToMany`. Si la arista apunta a una clase de asociación mediante `associationClassId`, genera esa clase como entidad con referencias a los dos extremos y sus atributos propios, sin crear una segunda tabla de unión. Las autorrelaciones con `sourceRole` y `targetRole` explícitos reciben nombres de campo únicos; las ambiguas se omiten con un aviso en el log y en el README del ZIP.

## Estructura principal

```text
backend/
  config/                 settings, URLs, ASGI y WSGI activos
  apps/
    accounts/             usuarios y autenticación
    projects/             proyectos, snapshots, permisos, XMI y JavaDoc IA
      generators/          JavaDoc IA y XMI
    realtime/             consumidor y rutas WebSocket
    ai_core/              endpoints de IA local
    generator/            motor Spring Boot, plantillas Jinja2 y pruebas
    diagrams/             legado no instalado; conservado por sus datos históricos
  manage.py
  requirements.txt
  .env.example
frontend/
  src/api/                cliente Axios
  src/components/         interfaz del editor y modales
  src/hooks/              colaboración WebSocket
  src/pages/              registro, acceso, proyectos y diagrama
  src/store/              estado de usuario y proyecto
  package.json
  .env.example
class_diagram.md / class_diagram.puml
README.md
RESUMEN_GENERAL_SOFTWARE.md
```

## Limitaciones y riesgos pendientes

- El WebSocket no revalida membresía ni rol después de conectar; cambios de permiso requieren reconexión.
- El guardado HTTP no valida la estructura interna de `nodes` y `edges` antes de almacenarla.
- Los endpoints de IA admiten contenido del cliente sin asociarlo a un proyecto; el endpoint de imagen lee el archivo completo en memoria.
- La aplicación guarda JWT en `localStorage` y envía el token de acceso en la URL del WebSocket. Cookies de sesión con validación de origen o tickets de corta duración son alternativas propuestas, no implementadas.
- La capa en memoria y el límite desigual de snapshots requieren trabajo adicional antes de afirmar escalabilidad. La generación de relaciones con semántica UML ambigua necesita roles explícitos y debe revisarse antes de usar el ZIP en producción.
