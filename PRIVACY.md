# Política de privacidad de FaceGuard AI

FaceGuard AI es software que usted instala y administra. **El proyecto FaceGuard AI no recibe, ve ni almacena ningún dato de su instalación.** Quien instala el software (usted) es el responsable del tratamiento de los datos que procesa.

## Qué datos procesa el software

| Dato | Dónde se guarda | Cuánto tiempo |
|---|---|---|
| Fotografías de personas registradas | En el equipo, cifradas (Fernet) | Hasta que se eliminan o vence el registro |
| Plantillas biométricas (vectores faciales) | En el equipo, cifradas | Igual que la fotografía |
| Capturas de las alertas | En el equipo, cifradas | 15 días por defecto (configurable) |
| Historial de eventos y alertas | Base de datos SQLite local | 30 días por defecto (configurable) |
| Registro de auditoría (acciones de los usuarios) | Base de datos SQLite local | 365 días por defecto (configurable) |
| Usuarios del panel | Base de datos local; contraseñas con hash scrypt | Hasta que se eliminan |

Las imágenes de la cámara se analizan en memoria. **No se guardan imágenes de las personas que no coinciden con la lista de alerta.**

Ubicación de los datos:

- Windows: `%LOCALAPPDATA%\FaceGuard AI`
- Linux (Desktop): `~/.local/share/faceguard-ai`
- Raspberry Pi: `/var/lib/faceguard`

## Conexiones a Internet

FaceGuard AI funciona sin Internet. Solo se conecta en estos casos:

- **Buscar actualizaciones** (desactivado por defecto): consulta a `api.github.com` el número de la última versión publicada. No envía imágenes, datos biométricos, nombres ni identificadores de la instalación. GitHub puede registrar la dirección IP de la consulta según su propia política.
- **Instalación en la Raspberry Pi:** el instalador descarga el paquete de GitHub y los paquetes del sistema de los repositorios de Raspberry Pi OS.

FaceGuard AI **nunca** envía imágenes ni datos biométricos a servicios externos. No contiene telemetría, analítica ni publicidad.

## Sus obligaciones como responsable

Al usar FaceGuard AI con personas reales, usted debe cumplir las leyes de protección de datos y de videovigilancia aplicables. Como mínimo:

1. Tener una base legal para tratar datos biométricos y, cuando la ley lo exija, el **consentimiento** informado y por escrito de las personas registradas.
2. Colocar **avisos visibles** de videovigilancia y reconocimiento facial.
3. Registrar en la lista de alerta solo a personas con un **motivo documentado**.
4. Atender los derechos de las personas: acceso, rectificación y **eliminación** de sus datos (Personas → Eliminar borra la foto, la plantilla y los archivos).
5. Limitar el acceso al panel y revisar la auditoría.
6. **Revisar cada alerta**: una coincidencia no es una identificación. No use una alerta como única base para impedir el acceso a nadie.

Lea la [guía legal por jurisdicción](docs/legal.md). No es asesoría legal: consulte a un abogado antes de usar el sistema en un lugar real.

## Eliminación de datos

- **Una persona:** Personas → seleccionar → Eliminar (borra foto, plantilla y archivos).
- **Automática:** Configuración → Conservación.
- **Todo:** desinstale y borre la carpeta de datos (el desinstalador de Windows lo pregunta). En la Raspberry Pi: `sudo systemctl disable --now faceguard && sudo rm -rf /var/lib/faceguard /etc/faceguard /opt/faceguard-ai`.

En tarjetas SD y discos SSD la sobrescritura no garantiza el borrado físico; por eso los archivos ya se guardan cifrados.

## Contacto

Preguntas sobre esta política: abra un issue en [GitHub](https://github.com/Galito1014/FaceGuard/issues). Para datos de una instalación concreta, contacte con quien la administra.
