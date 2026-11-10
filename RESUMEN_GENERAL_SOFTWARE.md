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

`apps.ai_core` implementa sugerencias sobre el diagrama, chat de ayuda, extracción de clases desde una imagen y diagnóstico de la conexión con Gemini. Son funciones opcionales y requieren `GEMINI_API_KEY`. Los identificadores de modelos usados están definidos en `config/settings.py`: una lista de cuatro modelos para chat/visión, uno para diagnóstico y otro para JavaDoc. Su disponibilidad depende del proveedor y de la clave configurada. Groq y Ollama no se usan.

## Generación de código

`POST /api/projects/<id>/generate/spring-boot/` usa `apps.generator.engine.SpringGenerator` y descarga un ZIP con un proyecto Java/Spring Boot. Por cada clase genera entidad, DTOs de entrada y salida, mapper, repositorio, servicio y controlador, además de `pom.xml`, `application.properties` y un README. La opción `include_ai_docs` intenta añadir JavaDoc y anotaciones Swagger mediante Gemini. No genera proyectos Python, TypeScript ni SQL DDL independiente.

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
    ai_core/              endpoints Gemini
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
