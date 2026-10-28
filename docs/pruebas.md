# Evidencia de pruebas — FaceGuard AI

Este documento reúne las pruebas realizadas, con el **resultado esperado**, el **resultado obtenido** y los **ajustes** que se hicieron a partir de cada una. Se dividen en tres grupos:

1. **Pruebas automáticas del software** (16 pruebas con `pytest`).
2. **Pruebas funcionales de punta a punta** con una fuente de video controlada.
3. **Pruebas físicas en la Raspberry Pi**: el grupo debe completar la sección 3 durante la demostración con el hardware real.

> Para las pruebas de reconocimiento se usó la fotografía *Astronaut* de la NASA (Eileen Collins, dominio público, incluida en `scikit-image`) como “persona registrada”, y dos imágenes de prueba estándar de OpenCV como “otras personas”. **No se usaron fotos de personas sin su consentimiento.** Las imágenes de prueba no se incluyen en el repositorio.

---

## 1. Pruebas automáticas (`backend/tests/`)

Ejecución: `cd backend && pip install -r requirements-dev.txt scikit-image && pytest -v`
Resultado completo: [`evidencias/pytest-resultados.txt`](evidencias/pytest-resultados.txt) → **16 de 16 aprobadas**.

| # | Prueba | Qué verifica | Resultado |
|---|--------|--------------|-----------|
| 1 | `test_login_incorrecto_intentos_ilimitados` / `test_bloqueo_opcional` | Credenciales erróneas → 401 sin bloqueo (intentos ilimitados por defecto); con `FACEGUARD_LOGIN_MAX_ATTEMPTS=5`, al 6.º intento → 429 | ✅ |
| 2 | `test_rutas_privadas_sin_sesion` | Dashboard, lista, eventos, usuarios y video exigen sesión | ✅ |
| 3 | `test_contrasena_debil_rechazada` | Contraseñas de menos de 10 caracteres o sin letras+números se rechazan | ✅ |
| 4 | `test_cambio_obligatorio_de_contrasena` | Un usuario nuevo no accede a nada hasta cambiar la contraseña temporal | ✅ |
| 5 | `test_permisos_por_rol` | Auditor: solo consulta. Operador: monitoreo y alertas, sin lista ni configuración | ✅ |
| 6 | `test_no_eliminar_ultimo_superadmin` | No se puede dejar el sistema sin superadministrador | ✅ |
| 7 | `test_auditoria_registra_acciones` | Inicios de sesión exitosos y fallidos quedan auditados | ✅ |
| 8 | `test_rechaza_archivo_que_no_es_imagen` | Un archivo que no es JPG/PNG → 415 | ✅ |
| 9 | `test_rechaza_foto_sin_rostro` | Imagen sin rostro → informe de calidad “no apta” | ✅ |
| 10 | `test_registro_cifrado_y_reconocimiento` | Foto guardada **cifrada** en disco; plantilla reconoce la imagen espejada (sim > 0,6); historial “creado → modificado”; eliminación vacía la galería | ✅ |
| 11 | `test_alerta_simulada_revision_y_deduplicacion` | Confirmar sin observaciones → 422; revisión registrada; **dos coincidencias seguidas generan una sola alerta** | ✅ |
| 12 | `test_exportacion_csv_pdf` | Exportaciones CSV y PDF válidas | ✅ |
| 13 | `test_modo_demo_cargar_y_limpiar` | Datos ficticios marcados como simulados y eliminables sin tocar datos reales | ✅ |
| 14 | `test_actividad_y_resumen` | Gráficas de 24 h (24 puntos) y 7 días (7 puntos) | ✅ |
| 15 | `test_configuracion_valida_e_invalida` | Umbral fuera de rango, LED y buzzer en el mismo pin, o parámetro desconocido → 422 | ✅ |
| 16 | `test_retencion_borra_eventos_y_vence_registros` | Eventos viejos se borran, **alertas pendientes se conservan**, registros vencidos pasan a “vencido” | ✅ |

---

## 2. Pruebas funcionales de punta a punta

Se ejecutó el backend completo con una fuente de video de prueba (`FACEGUARD_CAMERA_SOURCE=video.avi`), que reemplaza a la cámara USB y permite repetir exactamente las mismas condiciones.

### Prueba A — Persona NO registrada frente a la cámara

| | |
|---|---|
| **Entrada** | Video con un rostro que no está en la lista de alerta |
| **Resultado esperado** | Recuadro verde “sin coincidencia”, evento “Detección” **sin imagen**, ninguna alerta, LED y buzzer apagados |
| **Resultado obtenido** | Recuadro verde con similitud −0,05. Se registró 1 evento de detección agrupado (no uno por fotograma). No se guardó ninguna imagen. 0 alertas. |
| **Ajuste realizado** | Al principio el evento de detección guardaba “similitud 0,00” cuando la lista estaba vacía, lo que confundía en el historial. Ahora se guarda “—” si no hay plantillas con las cuales comparar. |

### Prueba B — Persona registrada frente a la cámara

| | |
|---|---|
| **Entrada** | 1) Registro de la foto de referencia desde el panel (nivel *alto*). 2) Video donde aparece la misma persona durante varios segundos (el video se repite en bucle). |
| **Resultado esperado** | Validación de calidad “apta”; recuadro ámbar “verificando” y luego rojo “POSIBLE COINCIDENCIA”; **una sola** alerta “Pendiente de revisión” aunque la persona siga en cuadro; notificación emergente en el panel; activación del LED y el buzzer; recorte del rostro guardado cifrado |
| **Resultado obtenido** | Similitud 0,95. Se generó **1 alerta** en 25 s, aunque el video se repitió 2 veces (la deduplicación de 60 s funcionó). Notificación en tiempo real recibida por WebSocket. GPIO en modo simulado: *“Alarma nivel alto: LED=sí, buzzer=sí”*. Se marcó la alerta como “Falso positivo” con observaciones y quedó registrada con el nombre del revisor. |
| **Ajuste realizado** | En el primer video el rostro medía ≈ 40 px en la imagen analizada y el filtro de tamaño mínimo (60 px) lo descartaba: **no hubo alerta**. Se documentó que la cámara debe ubicarse a 1–2 m de la puerta (rostro ≥ 80 px) y se hizo configurable el “tamaño mínimo de rostro” en *Configuración → Reconocimiento*. |

Captura de la prueba B: [`img/07-revision-alerta.png`](img/07-revision-alerta.png)

### Prueba C — Robustez del reconocimiento (misma persona en distintas condiciones)

Resultado completo: [`evidencias/motor-facial-similitud.txt`](evidencias/motor-facial-similitud.txt) · umbral 0,42.

| Variante de la imagen | Similitud | Resultado |
|---|---:|---|
| Espejo horizontal | 0,946 | coincide ✅ |
| Más oscura | 0,923 | coincide ✅ |
| Más clara | 0,834 | coincide ✅ |
| Media resolución | 0,925 | coincide ✅ |
| Rotada 10° | 0,958 | coincide ✅ |
| Desenfocada | 0,856 | coincide ✅ |
| Con ruido | 0,876 | coincide ✅ |
| **Otra persona 1** | **−0,048** | no coincide ✅ |
| **Otra persona 2** | **0,134** | no coincide ✅ |

**Conclusión:** hay un margen amplio entre la misma persona (≥ 0,83) y otras personas (≤ 0,14). Por eso el umbral por defecto es 0,42, algo más estricto que el valor 0,363 que recomienda OpenCV, para reducir falsos positivos. Esta prueba usa variaciones de una sola foto; con personas reales, ángulos y gafas las similitudes serán menores, por lo que **el umbral debe calibrarse en la Pi** (sección 3).

### Prueba D — Desconexión de la cámara

| | |
|---|---|
| **Entrada** | Arrancar sin cámara disponible (`/dev/video0` inexistente) |
| **Resultado esperado** | La aplicación no se cae; el panel muestra “Sin señal” y reintenta |
| **Resultado obtenido** | El hilo de captura reintentó con espera progresiva (1 s → 10 s), el panel mostró “No se pudo abrir la cámara /dev/video0 (reintentos: N)” y el resto del sistema siguió funcionando |
| **Ajuste realizado** | Se agregó un evento de sistema (máx. 1 cada 30 s) para que la desconexión quede en el historial sin llenarlo de eventos repetidos |

### Prueba E — Interfaz

Se recorrieron todas las pantallas con un navegador automatizado (Playwright/Chromium) en escritorio (1440×900) y móvil (390×844). Capturas en [`img/`](img/).

| Ajuste detectado | Corrección |
|---|---|
| Las gráficas no cargaban (error 500): el parámetro `range` ocultaba la función `range()` de Python | Se renombró el parámetro interno |
| Las fuentes no cargaban por la política de seguridad de contenido (CSP) | Se agregó `font-src 'self' data:` y se desactivó la incrustación de recursos en la compilación |
| En el móvil, los títulos de las tarjetas se cortaban | Ahora el texto pasa a la línea siguiente |
| El texto superpuesto en el video se veía duplicado | Se reemplazó por una franja oscura semitransparente |

---

## 3. Pruebas físicas en la Raspberry Pi (completar en la demostración)

> Usen **solo voluntarios del grupo que den su consentimiento** y bórrenlos de la lista al terminar.
> Herramienta de apoyo: `python -m scripts.benchmark_engine referencia.jpg prueba1.jpg …`

| # | Situación | Resultado esperado | Resultado obtenido | Ajuste |
|---|-----------|--------------------|--------------------|--------|
| F1 | Integrante **no registrado** pasa frente a la cámara a 1,5 m | Recuadro verde, sin alerta, LED/buzzer apagados | | |
| F2 | Integrante **registrado** (nivel alto) pasa frente a la cámara | Alerta en < 2 s, LED parpadea, buzzer suena, notificación en el panel | | |
| F3 | El registrado permanece 2 minutos | Solo 1 alerta por cada 60 s (deduplicación) | | |
| F4 | Registrado con gorra o lentes | Anotar similitud; ¿se mantiene sobre el umbral? | | |
| F5 | Desconectar el cable USB 10 s y reconectar | “Sin señal” → se recupera solo | | |
| F6 | Reiniciar la Raspberry Pi | El servicio arranca solo (systemd) | | |
| F7 | 30 min de monitoreo continuo | Temperatura < 70 °C (con disipador o ventilador); FPS de análisis estable | | |

Rendimiento medido en la Pi (copiar de *Configuración → Sistema* y *Monitoreo*):

| Métrica | Valor |
|---|---|
| FPS de análisis | |
| Latencia por fotograma (ms) | |
| CPU (%) | |
| RAM usada (MB) | |
| Temperatura tras 30 min (°C) | |
