# Historial de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versiones según [SemVer](https://semver.org/lang/es/).

## [1.1.0] - sin publicar

Primera versión preparada para distribución pública.

### Añadido
- **FaceGuard AI Desktop** para Windows 10/11 (instalador `.exe`) y Linux x86_64 (`.deb` y AppImage): se abre como un programa normal, sin Python ni terminal. Los datos se guardan en la carpeta del usuario y se conservan al actualizar.
- **Instalador automático para Raspberry Pi** con verificación SHA-256, instalación sin Internet (`--file`), actualización que conserva datos y guarda una copia de la base de datos.
- Soporte opcional de **cámaras CSI** en Raspberry Pi mediante picamera2 (`--csi`).
- **Asistente de configuración inicial**: cuenta administradora, cámara, reconocimiento, conservación de datos, alertas y aviso de privacidad. En la Raspberry Pi se protege con un código de un solo uso.
- **Restricción del panel a la red local**: las conexiones desde IP públicas reciben 403 (`FACEGUARD_ALLOWED_NETWORKS`).
- **Comprobación de actualizaciones** opcional (desactivada por defecto) desde GitHub Releases.
- Reducción automática de la frecuencia de análisis cuando la CPU se calienta (75 °C / 80 °C).
- GitHub Actions: pruebas en Linux, Windows y ARM64; compilación de instaladores; prueba de instalación del servicio en ARM64; borrador de versión con `SHA256SUMS.txt`.
- Página de descargas en GitHub Pages.
- Licencia Apache 2.0, `SECURITY.md`, `PRIVACY.md`, `CONTRIBUTING.md`, guía legal y guía de desarrollo.

### Cambiado
- El bloqueo por intentos fallidos de inicio de sesión viene activado por defecto (5 intentos, 5 minutos).
- Sin `FACEGUARD_ADMIN_PASSWORD`, ya no se crea un usuario `admin` con contraseña aleatoria: se usa el asistente.

## [1.0.0] - 2026-11

- Versión académica inicial: reconocimiento con YuNet + SFace, lista de alerta con revisión humana, panel web, auditoría, retención, respaldos, GPIO y servicio systemd.
