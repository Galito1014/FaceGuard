# Validación antes de publicar

Estado de las pruebas por plataforma. **Una plataforma solo se marca como validada cuando se probó en un equipo representativo, no solo en CI.**

## Qué se prueba automáticamente

| Prueba | Dónde | Qué cubre |
|---|---|---|
| Pruebas del núcleo (`pytest`, 140+) | CI: Ubuntu x64 (Python 3.11 y 3.13), Windows (3.12), Ubuntu ARM64 (3.11) | Autenticación y roles, personas, lista de alerta y alertas con el motor facial real, seguimiento, análisis, respaldos, retención, asistente inicial, restricción de redes, comprobación de versiones |
| Compilación del panel | CI | TypeScript y build de Vite |
| Autoprueba del paquete Desktop (`--self-test`) | CI Windows y Linux | El ejecutable arranca, sirve el panel, crea la base de datos y carga los modelos |
| Instalación silenciosa del `.exe` | CI Windows | Instalación por usuario y autoprueba del programa instalado |
| Instalación del `.deb` | CI Ubuntu 22.04 | Instalación con apt y autoprueba |
| Instalador de Raspberry Pi | CI Ubuntu 24.04 ARM64 | Instalación desde cero, servicio systemd habilitado (inicio automático), asistente pendiente con código, rechazo de un paquete modificado, recuperación tras matar el proceso, actualización con copia de la base de datos |
| Secretos | CI | Sin bases de datos, modelos, `.env`, claves ni secretos en el repositorio (Gitleaks) |

**Lo que CI no puede probar:** cámaras reales, GPIO, cámaras CSI, Raspberry Pi OS (CI usa Ubuntu ARM64), la ventana nativa (WebView2 / navegador en modo aplicación), SmartScreen y el rendimiento en una Raspberry Pi 4.

## Lista de validación manual

Marque cada casilla al probarla y anote equipo, sistema y fecha.

### Windows 10/11 — FaceGuard AI Desktop
- [ ] Descargar el `.exe` desde la página y comprobar `Get-FileHash` con `SHA256SUMS.txt`
- [ ] Instalar sin permisos de administrador; aparece en el menú Inicio
- [ ] Se abre como ventana (sin consola ni navegador)
- [ ] Asistente inicial completo; inicio de sesión posterior
- [ ] Webcam integrada y cámara USB detectadas y con imagen
- [ ] Registrar una persona (foto de prueba) y obtener una alerta frente a la cámara
- [ ] Revisar la alerta (confirmar / falso positivo); aparece en historial y auditoría
- [ ] Funciona sin conexión a Internet (Wi-Fi desactivado)
- [ ] Abrir dos veces: no se inicia una segunda copia
- [ ] Instalar la versión siguiente encima: los datos siguen ahí
- [ ] Desinstalar eligiendo conservar datos y luego eligiendo borrarlos
- [ ] Sesión de 8 h sin aumento sostenido de memoria

### Linux x86_64 — Desktop (.deb y AppImage)
- [ ] Ubuntu 22.04/24.04 o Debian 12: `sudo apt install ./….deb`, abre desde el menú
- [ ] AppImage en otra distribución (p. ej. Fedora)
- [ ] Ventana de aplicación con Chromium/Chrome; sin ellos, abre el navegador y la ventana de control
- [ ] Cámara USB detectada (usuario en el grupo `video`)
- [ ] Mismas pruebas funcionales que en Windows

### Raspberry Pi 4 (8 GB) — Raspberry Pi OS 64-bit
- [ ] Instalación con el comando de una línea desde una imagen limpia
- [ ] Código de configuración mostrado; asistente desde un teléfono en la misma red
- [ ] Panel no accesible desde una IP pública (p. ej. datos móviles con reenvío de puerto de prueba): 403
- [ ] Cámara USB; cámara CSI con `--csi`
- [ ] LED y buzzer en GPIO17/GPIO27
- [ ] Reinicio de la Pi: el servicio arranca solo
- [ ] Desconectar y reconectar la cámara: se recupera
- [ ] Prueba de 24 h: temperatura, CPU, memoria y latencia estables; reducción por temperatura si supera 75 °C
- [ ] Actualización a la versión siguiente conservando datos (copia en `/var/lib/faceguard/backups`)
- [ ] Instalación sin Internet con `--file`

## Resultados

| Plataforma | Estado | Equipo / sistema | Fecha | Notas |
|---|---|---|---|---|
| Linux x86_64 (paquetes `.deb`, AppImage, autoprueba) | Probado en contenedor, sin pantalla ni cámara | Linux x86_64 (entorno de desarrollo) | 2026-11-07 | El núcleo, el panel y los modelos arrancan desde los paquetes; ventana y cámara pendientes |
| Windows 10/11 | Pendiente | | | Lo compila y prueba CI; falta un equipo real |
| Raspberry Pi 4 | Pendiente | | | Instalador probado solo en CI ARM64 (Ubuntu) |
