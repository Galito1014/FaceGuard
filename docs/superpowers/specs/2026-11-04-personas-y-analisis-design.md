# Personas, muestras faciales y análisis de fotografías — diseño

Fecha: 2026-11-04. Origen: especificación de ampliación entregada por Andrés.

## Decisiones

- `blacklist` pasa a `persons`, con clasificación `autorizada` o `no_autorizada`. Fotos y plantillas pasan a `face_samples`.
- `events` y `audit_log` cumplen el papel de `alerts` y `audit_logs`. No se renombran para no añadir riesgo.
- `falso_positivo` se muestra como "Descartada". El valor guardado no cambia.
- Una coincidencia con la blacklist sobre el umbral tiene prioridad sobre una autorizada más parecida.
- El paso de una persona autorizada no se registra. Solo se indica en vivo.
- Una persona autorizada exige consentimiento y vencimiento. Una no autorizada exige motivo, base legal, nivel y vencimiento.
- La similitud se muestra como valor coseno, nunca como porcentaje.
- El análisis de fotografías no guarda la imagen. Una posible coincidencia con la blacklist conserva solo el recorte en una alerta pendiente.
- Los respaldos no incluyen la clave de cifrado por defecto.

## Fuera de alcance

- Filtro de calidad en video en vivo y reconocimiento con la imagen original (mejoras de precisión pendientes).
- Modelo propio entrenado con revisiones (fase 3).
- Cifrado completo de la base de datos: se documenta la protección actual.
