# Fase 1: seguimiento de rostros — diseño

Fecha: 2026-11-04. Estado: aprobado; actualizado tras la revisión independiente.

## Contexto

Esta es la primera de tres fases para mejorar FaceGuard AI con machine learning:

1. **Más rápido** (este documento): seguimiento de rostros y corrección de la racha.
2. **Más preciso:** filtro de calidad, mejor fotograma, varias plantillas e imagen original.
3. **Modelo propio:** modelo pequeño entrenado con las revisiones de los guardias. Decisión ya
   tomada: solo ordena y etiqueta las alertas; nunca las silencia.

Cada fase tiene su propio diseño, plan y PR.

## Problema

- `Pipeline._process_real` ejecuta SFace para cada rostro en cada ciclo (hasta 4 veces por segundo
  con la configuración actual), aunque sea la misma persona frente a la cámara. SFace es el paso
  más costoso, y esto pesa sobre todo en la Raspberry Pi.
- `_streak` se indexa por persona de la lista (`entry_id`), no por rostro. Si dos rostros del mismo
  fotograma se parecen a la misma persona, la racha sube dos veces, y con `confirm_frames=2` un
  solo fotograma dispara la alerta.

## Objetivos

- Reducir las llamadas a SFace sin perder alertas.
- Corregir la racha: cada rostro acumula la suya.
- Medir el ahorro con un video real antes de afirmar una cifra.

## Fuera de alcance

- Filtro de calidad, varias plantillas y otros cambios de precisión (fase 2).
- Modelo entrenado (fase 3).
- Dependencias nuevas, cambios de frontend y cambios de base de datos.
- El modo demostración (`_process_demo`), que no ejecuta SFace.

## Diseño

### Unidad nueva: `backend/app/services/tracker.py`

Lógica pura: sin cámara, sin OpenCV y sin acceso a la base de datos. Recibe cajas y el instante
actual como parámetro, lo que permite probarla sin hardware y procesar videos con su propio reloj.

`Track` guarda: `id`, `box`, `last_seen`, `first_seen`, `last_embed_at`, `meta`, `sim`, `streak` y
`confirmed`.

`FaceTracker` ofrece:

- `update(boxes, now) -> list[Track]`: devuelve un track por caja, en el mismo orden.
  - Asocia cada caja con un track existente por IoU, de mayor a menor, con un mínimo de 0.3.
  - Cada track se asocia con una sola caja por ciclo.
  - Una caja sin track crea uno nuevo.
  - Se elimina el track que lleve más de 1 s sin verse (`TRACK_TTL_SECONDS`).
- `needs_embedding(track, now, recheck_s) -> bool`: verdadero si se cumple alguna condición:
  - el track es nuevo o lleva menos de 2 s en cuadro (`FULL_CHECK_SECONDS`);
  - está en verificación (`streak > 0` y sin confirmar);
  - pasaron `recheck_s` o más desde `last_embed_at`.
- `record_result(track, meta, sim, threshold, confirm_frames, now)`: aplica el resultado de SFace.
  - Si `sim >= threshold` y es la misma persona, suma 1 a la racha.
  - Si es otra persona de la lista, la racha vuelve a 1.
  - Si no supera el umbral, la racha vuelve a 0 y se quita `confirmed`.
  - `confirmed` se activa cuando la racha del rostro o la de la persona llega a `confirm_frames`.
  - La racha de la persona cuenta ciclos consecutivos con coincidencia y sube como máximo una vez
    por ciclo. Así, dos rostros en un fotograma no confirman, pero sí se confirma alguien cuyo
    rostro no se puede asociar entre ciclos.
- `reset()`: borra todos los tracks.

`reset()` y `update()` se protegen con un lock, porque `reset_tracking` se llama desde otro hilo.

### Cambios en `pipeline.py`

En `_process_real`, para cada rostro detectado:

1. Obtiene su track con `update`.
2. Si `needs_embedding` es verdadero, ejecuta SFace, llama a `gallery.best_match` y a `record_result`.
3. Si no, reutiliza `sim` y `meta` del track.
4. Si el track está confirmado, llama a `_maybe_alert` en cada ciclo.

El paso 4 conserva el comportamiento actual: `dedup_seconds` evita las repeticiones, y una persona
que siga frente a la cámara vuelve a generar una alerta al terminar ese periodo. La alerta usa la
similitud más reciente del track y el fotograma actual.

Se eliminan `_streak` y la limpieza de `seen`. Los rótulos y los colores del panel no cambian.

`Face.embedding` puede ser `None` en un ciclo sin reconocimiento. `_log_detection` sigue usando
`best_score` y `match`, que se rellenan desde el track.

### Reinicio del seguimiento

- `reset_tracking()` también llama a `tracker.reset()`. Ya se ejecuta al cambiar `match_threshold`
  o `confirm_frames`.
- `Gallery` gana un contador `version` que sube en cada `load()`. Si `_process_real` detecta otra
  versión, reinicia solo los tracks y conserva `_last_alert`. Así, alguien recién añadido se
  reconoce aunque ya esté frente a la cámara, sin repetir alertas recientes.

### Configuración

Nueva clave `recheck_interval_ms` en `settings_store.py`: valor 1000, rango de 0 a 10000 (entero).

Con `0`, se reconoce cada rostro en cada ciclo, como hoy, y se mantiene la corrección de la racha.
Sirve de vuelta atrás sin tocar el código
y de referencia para la medición. No tiene control en el panel en esta fase.

### Métricas

`Pipeline` cuenta `embeds_computed` y `embeds_skipped`, y `status()` los incluye.

### Medición

`scripts/benchmark_engine.py` gana `--video ruta.mp4`, con la foto de referencia como galería.
Procesa el video dos veces a 4 análisis por segundo de video, según su propio reloj:

- `recheck_interval_ms=0` (referencia);
- `recheck_interval_ms=1000` (seguimiento).

Imprime por cada pasada las llamadas a SFace, el tiempo total y por fotograma, y cuántos fotogramas
quedan confirmados. El modo actual con fotografías no cambia.

## Riesgos

| Riesgo | Efecto | Mitigación |
|---|---|---|
| Dos personas se cruzan después de 2 s en cuadro y el track cambia de rostro | Alerta hasta 1 s más tarde | Revisión periódica |
| Rostro que cruza tan rápido que no se asocia entre ciclos | Se pierde el ahorro | La racha de la persona confirma en ciclos seguidos |
| Primer fotograma malo (borroso o al borde del encuadre) | Sin retraso | Reconocimiento en cada ciclo durante los primeros 2 s |
| Falsa racha por track mal asociado | Alerta dudosa | Toda alerta sigue pendiente de revisión humana |
| Ciclos más lentos que 1 s (`process_interval_ms` alto) | Los tracks expiran y no hay ahorro | La racha de la persona confirma como hoy |
| Una persona de la lista en un track con más de 2 s y ya descartado | Alerta hasta 1 s más tarde | Intervalo configurable; `0` lo desactiva |

## Pruebas

Pruebas nuevas en `backend/tests/test_tracker.py`, sin cámara:

- Una misma caja que se mueve conserva su track; una caja lejana crea otro.
- Un track expira tras `TRACK_TTL_SECONDS`.
- `needs_embedding` en cada caso: nuevo, reciente, en verificación, descartado antes y después del
  intervalo, e intervalo 0.
- Generan alerta un rostro que cruza rápido, los ciclos más lentos que 1 s y un primer fotograma malo.
- Dos rostros que se parecen a la misma persona en un solo fotograma no confirman con
  `confirm_frames=2`.
- La racha se reinicia al bajar del umbral y al cambiar de persona.
- `reset()` borra los tracks, y una nueva versión de la galería fuerza otro reconocimiento.
- La nueva clave respeta su rango en la validación de configuración.

Las 24 pruebas actuales deben seguir pasando.

## Criterios de aceptación

- Pruebas nuevas y actuales aprobadas.
- Con una persona quieta frente a la cámara, pasados los primeros 2 s, SFace se ejecuta alrededor
  de una vez por segundo.
- Un solo fotograma ya no puede confirmar una coincidencia con `confirm_frames=2`.
- El ahorro se reporta con la medición del video; hasta entonces no se publica ninguna cifra.
