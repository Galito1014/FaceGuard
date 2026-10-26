# Seguridad y privacidad — FaceGuard AI

Los datos biométricos (fotografías y plantillas faciales) son **datos personales sensibles**. Un error del sistema puede afectar a una persona inocente. Por eso el diseño parte de tres principios:

1. **El sistema solo sugiere y una persona decide.** Toda coincidencia es preliminar y queda “Pendiente de revisión”. FaceGuard no bloquea puertas ni toma acciones contra nadie.
2. **Mínimo de datos.** No se guardan fotos de quienes no coinciden con la lista. Todo vence y se borra automáticamente.
3. **Todo queda registrado.** Cada acción administrativa queda en la auditoría.

## Riesgos identificados y cómo se reducen

| Riesgo | Impacto | Medidas implementadas |
|---|---|---|
| **Falso positivo**: el sistema confunde a un residente o visitante con alguien de la lista | Trato injusto o discriminatorio | Umbral configurable (por defecto 0,42, más estricto que el recomendado); confirmación en N fotogramas seguidos; tamaño mínimo de rostro; revisión humana obligatoria con observaciones; estado “Falso positivo” para medir la tasa de error; pantalla de revisión con la imagen detectada y la registrada lado a lado |
| **Registro sin base legal o por motivos discriminatorios** | Vigilancia abusiva | Campos obligatorios de “motivo documentado” y “base legal”; casilla de confirmación de autorización; solo administradores registran; historial de cambios por registro; vencimiento obligatorio |
| **Robo de la tarjeta SD o copia de archivos** | Filtración de biometría | Fotos, plantillas y capturas cifradas con Fernet (AES-128 + HMAC); clave en `secret/fernet.key` con permisos 600; carpeta de datos 700; servicio con usuario sin privilegios |
| **Acceso no autorizado al panel** | Consulta o manipulación de la lista | Contraseñas con scrypt; mínimo 10 caracteres; cambio obligatorio de la contraseña temporal; bloqueo tras 5 intentos fallidos; sesiones de 8 h en cookie `httpOnly` y `SameSite=Strict`; cierre de las demás sesiones al cambiar la contraseña; 4 roles con permisos mínimos |
| **Abuso por parte de un usuario autorizado** | Uso indebido de imágenes | Las imágenes no se muestran automáticamente (se hace clic en “Mostrar imagen”); cada visualización de una imagen de alerta queda auditada; el auditor no ve fotos; las exportaciones quedan auditadas y el PDF se marca como confidencial |
| **Conservación excesiva** | Vigilancia permanente | Eventos: 30 días; imágenes de alertas: 15 días; auditoría: 365 días (todo configurable). Los registros de la lista vencen y se desactivan solos. Borrado con sobrescritura de archivos |
| **Interceptación en la red** | Robo de la sesión o del video | El sistema funciona sin Internet, solo en la red local. Recomendado: red Wi-Fi exclusiva para seguridad o cable Ethernet y, si se publica fuera, un proxy HTTPS (`FACEGUARD_SECURE_COOKIES=1`) |
| **Ataques web (XSS, clickjacking)** | Robo de la sesión | Cabeceras CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`; React escapa el contenido; consultas SQL parametrizadas |
| **Falla del equipo** | Pérdida de vigilancia | Reconexión automática de la cámara; reinicio automático del servicio (systemd `Restart=always`); monitoreo de temperatura; los errores de procesamiento no detienen el hilo |
| **Confundir datos de demostración con reales** | Decisiones sobre datos falsos | Todo lo simulado tiene la etiqueta SIMULADO, una franja morada en el panel y una marca en el video; los registros ficticios no tienen plantilla biométrica |

## Limitaciones conocidas (honestidad técnica)

- **Sesgo de los modelos:** los modelos faciales pueden tener tasas de error distintas según el tono de piel, la edad o el género. SFace se entrenó con conjuntos de datos públicos que no representan necesariamente a la población boliviana. Por eso la revisión humana no es opcional.
- **Fotos o pantallas:** el sistema no detecta si alguien muestra una foto (no tiene “prueba de vida”). Para una lista de alerta esto importa poco (nadie quiere hacerse pasar por alguien de la lista), pero significa que **no debe usarse para abrir puertas**.
- **Borrado en tarjeta SD:** por el nivelado de desgaste de la memoria flash, la sobrescritura no garantiza el borrado físico. Por eso los archivos ya están cifrados.
- **La clave de cifrado está en el mismo dispositivo.** Protege contra la copia de archivos sueltos, pero no contra alguien que se lleve la tarjeta SD completa. Mejora posible: cifrado de disco completo (LUKS) o un elemento seguro (por ejemplo, ATECC608).

## Aspectos legales (Bolivia)

> Esto no es asesoría legal; el condominio debe consultarlo con un abogado.

- La Constitución Política del Estado reconoce el derecho a la intimidad (art. 21) y la acción de protección de privacidad (arts. 130–131). A la fecha de este proyecto Bolivia **no tiene una ley general de protección de datos personales** (el proyecto de ley PL 538/2025–2026 sigue en tratamiento), por lo que se siguieron buenas prácticas internacionales: minimización, finalidad, conservación limitada y transparencia.
- **Requisitos mínimos de uso propuestos:**
  1. Aprobación del sistema en la asamblea de copropietarios, con un reglamento escrito.
  2. Un letrero visible en el ingreso: *“Área con videovigilancia y reconocimiento facial”*.
  3. Solo se registra a personas con un documento que lo justifique (orden judicial, resolución de la asamblea o denuncia formal).
  4. Toda persona registrada puede pedir revisión y eliminación de su registro.
  5. Un protocolo claro para el guardia: verificar en persona y avisar a la administración; **nunca** actuar solo por la alerta.
