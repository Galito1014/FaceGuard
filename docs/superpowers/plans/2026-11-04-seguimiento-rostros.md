# Seguimiento de rostros: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reducir las llamadas a SFace con seguimiento de rostros y dar a cada rostro su propia racha.

**Architecture:** Un `FaceTracker` puro (sin OpenCV ni base de datos) asocia las cajas de YuNet entre ciclos y decide cuándo ejecutar SFace. `Pipeline._process_real` lo usa en lugar de `_streak`. `recheck_interval_ms=0` restaura el comportamiento actual.

**Tech Stack:** Python 3.11–3.13, OpenCV, NumPy, pytest. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-11-04-seguimiento-rostros-design.md`

> **Nota:** la revisión final cambió este plan. Se añadieron la racha por persona y `FULL_CHECK_SECONDS`; el diseño describe el resultado definitivo.

## Global Constraints

- Rama: `fase1-seguimiento-rostros`. Un solo código para Windows y Raspberry Pi.
- Sin dependencias nuevas, sin cambios de frontend y sin migraciones.
- `recheck_interval_ms`: valor 1000, entero, rango 0–10000.
- IoU mínimo 0.3. `TRACK_TTL_SECONDS = 1.0`.
- Código, comentarios y mensajes en español.
- Comandos desde `backend/`. Las 24 pruebas actuales deben seguir pasando.
- No publicar ninguna cifra de ahorro sin medirla con video.

## Review Focus

1. Dos personas se cruzan y el track cambia de rostro: la revisión periódica corrige la identidad.
2. YuNet pierde un rostro durante un ciclo: el track sobrevive menos de 1 s y conserva la racha.
3. La cámara se detiene más de 1 s: los tracks antiguos expiran y el rostro se reconoce de nuevo.
4. La galería está vacía (`meta=None`, `sim=0.0`): sin errores, sin candidatos y sin alertas.
5. Se quita a alguien de la lista mientras su track está confirmado: la nueva versión de la galería evita más alertas.

---

### Task 1: `FaceTracker`

**Files:**
- Create: `backend/app/services/tracker.py`
- Test: `backend/tests/test_tracker.py`

**Interfaces:**
- Produces:
  - `TRACK_TTL_SECONDS = 1.0`, `MIN_IOU = 0.3`
  - `iou(a: Box, b: Box) -> float`, con `Box = tuple[int, int, int, int]` (x, y, w, h)
  - dataclass `Track`: `id: int`, `box: Box`, `last_seen: float`, `last_embed_at: float | None = None`, `meta: dict | None = None`, `sim: float = 0.0`, `streak: int = 0`, `confirmed: bool = False`
  - `FaceTracker.update(boxes: list[Box], now: float) -> list[Track]`
  - `FaceTracker.needs_embedding(track: Track, now: float, recheck_s: float) -> bool`
  - `FaceTracker.record_result(track, meta, sim, threshold: float, confirm_frames: int, now: float) -> None`
  - `FaceTracker.reset() -> None`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `backend/tests/test_tracker.py` con estas pruebas. `META_A = {"entry_id": 1}` y `META_B = {"entry_id": 2}`:

```python
def test_caja_que_se_mueve_conserva_track():
    t = FaceTracker()
    a = t.update([(100, 100, 80, 80)], 0.0)[0]
    b = t.update([(105, 102, 80, 80)], 0.25)[0]
    assert a.id == b.id

def test_caja_lejana_crea_otro_track():
    t = FaceTracker()
    a = t.update([(0, 0, 80, 80)], 0.0)[0]
    b = t.update([(300, 300, 80, 80)], 0.25)[0]
    assert a.id != b.id

def test_track_no_se_asocia_dos_veces_en_un_ciclo():
    t = FaceTracker()
    t.update([(100, 100, 80, 80)], 0.0)
    a, b = t.update([(100, 100, 80, 80), (102, 100, 80, 80)], 0.25)
    assert a.id != b.id

def test_rostro_perdido_un_ciclo_conserva_racha():
    t = FaceTracker()
    tr = t.update([(100, 100, 80, 80)], 0.0)[0]
    t.record_result(tr, META_A, 0.6, 0.42, 3, 0.0)
    t.update([], 0.25)
    assert t.update([(100, 100, 80, 80)], 0.5)[0].streak == 1

def test_track_expira_tras_el_ttl():
    t = FaceTracker()
    a = t.update([(100, 100, 80, 80)], 0.0)[0]
    b = t.update([(100, 100, 80, 80)], TRACK_TTL_SECONDS + 0.01)[0]
    assert a.id != b.id

def test_needs_embedding_por_estado():
    t = FaceTracker()
    tr = t.update([(100, 100, 80, 80)], 0.0)[0]
    assert t.needs_embedding(tr, 0.0, 1.0)                 # nuevo
    t.record_result(tr, None, 0.1, 0.42, 2, 0.0)
    assert not t.needs_embedding(tr, 0.5, 1.0)             # descartado, antes del intervalo
    assert t.needs_embedding(tr, 1.0, 1.0)                 # descartado, tras el intervalo
    assert t.needs_embedding(tr, 0.1, 0.0)                 # intervalo 0: siempre
    t.record_result(tr, META_A, 0.6, 0.42, 2, 1.0)
    assert t.needs_embedding(tr, 1.1, 1.0)                 # en verificación
    t.record_result(tr, META_A, 0.6, 0.42, 2, 1.1)
    assert tr.confirmed and not t.needs_embedding(tr, 1.2, 1.0)

def test_dos_rostros_iguales_a_una_persona_no_confirman_en_un_fotograma():
    t = FaceTracker()
    a, b = t.update([(0, 0, 80, 80), (300, 0, 80, 80)], 0.0)
    t.record_result(a, META_A, 0.6, 0.42, 2, 0.0)
    t.record_result(b, META_A, 0.6, 0.42, 2, 0.0)
    assert not a.confirmed and not b.confirmed

def test_racha_se_reinicia_bajo_el_umbral_y_con_otra_persona():
    t = FaceTracker()
    tr = t.update([(0, 0, 80, 80)], 0.0)[0]
    t.record_result(tr, META_A, 0.6, 0.42, 2, 0.0)
    t.record_result(tr, META_B, 0.6, 0.42, 2, 0.1)
    assert tr.streak == 1 and not tr.confirmed
    t.record_result(tr, META_B, 0.6, 0.42, 2, 0.2)
    assert tr.confirmed
    t.record_result(tr, META_B, 0.3, 0.42, 2, 0.3)
    assert tr.streak == 0 and not tr.confirmed

def test_confirm_frames_1_confirma_de_inmediato():
    t = FaceTracker()
    tr = t.update([(0, 0, 80, 80)], 0.0)[0]
    t.record_result(tr, META_A, 0.6, 0.42, 1, 0.0)
    assert tr.confirmed

def test_galeria_vacia_no_genera_candidato():
    t = FaceTracker()
    tr = t.update([(0, 0, 80, 80)], 0.0)[0]
    t.record_result(tr, None, 0.0, 0.42, 1, 0.0)
    assert tr.streak == 0 and not tr.confirmed and tr.meta is None

def test_reset_borra_los_tracks():
    t = FaceTracker()
    a = t.update([(0, 0, 80, 80)], 0.0)[0]
    t.reset()
    assert t.update([(0, 0, 80, 80)], 0.1)[0].id != a.id
```

- [ ] **Step 2: Ejecutar y comprobar que fallan**

Run: `pytest tests/test_tracker.py -v`
Expected: error de importación de `app.services.tracker`.

- [ ] **Step 3: Implementar `tracker.py`**

`update` elimina primero los tracks con `now - last_seen > TRACK_TTL_SECONDS`, calcula el IoU de cada par y asocia de mayor a menor con `MIN_IOU` como mínimo. `id` crece con cada track nuevo y nunca se reutiliza, ni tras `reset()`. Un lock protege `update` y `reset`. En `record_result`, una persona distinta se compara por `entry_id`; siempre se actualizan `sim` y `last_embed_at`, y `meta` queda en `None` si no supera el umbral.

- [ ] **Step 4: Ejecutar y comprobar que pasan**

Run: `pytest tests/test_tracker.py -v`
Expected: 11 pruebas aprobadas.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tracker.py backend/tests/test_tracker.py
git commit -m "feat: seguimiento de rostros con racha por rostro"
```

### Task 2: integración en el pipeline

**Files:**
- Modify: `backend/app/services/pipeline.py` (`__init__`, `reset_tracking`, `_process_real`, `status`)
- Modify: `backend/app/services/face_engine.py` (`Gallery`)
- Modify: `backend/app/services/settings_store.py` (`DEFAULTS`, `RULES`)
- Test: `backend/tests/test_pipeline_tracking.py`, `backend/tests/test_settings_retention.py`

**Interfaces:**
- Consumes: `FaceTracker`, `Track` de la Task 1.
- Produces: `Gallery.version: int`; `Pipeline.embeds_computed: int`; `Pipeline.embeds_skipped: int`; ambos contadores en `status()`; `Pipeline._process_real(frame, cfg, now: float | None = None)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `backend/tests/test_pipeline_tracking.py` con una fixture que parchee, con `monkeypatch`:
- `engine.ready = True`
- `engine.detect` → `(faces, frame, 1.0)`, con cada `Face` creado desde `box` y `raw=np.zeros(15)`
- `engine.embed` → cuenta llamadas y devuelve `np.ones(128)`
- `gallery.best_match` → valor configurable por prueba
- `pipeline._maybe_alert` → guarda cada llamada
- `pipeline._log_detection` → no hace nada

La fixture llama a `pipeline.reset_tracking()`. Cada prueba pasa `cfg = {**settings.all(), "confirm_frames": 2, "recheck_interval_ms": 1000}`.

```python
def test_rostro_quieto_se_reconoce_una_vez_por_segundo(env):
    env.best_match = (None, 0.1)
    for i in range(8):                       # 2 s a 4 ciclos por segundo
        pipeline._process_real(env.frame, env.cfg, now=i * 0.25)
    assert env.embed_calls == 2

def test_intervalo_0_reconoce_en_cada_ciclo(env):
    env.best_match = (None, 0.1)
    cfg = {**env.cfg, "recheck_interval_ms": 0}
    for i in range(8):
        pipeline._process_real(env.frame, cfg, now=i * 0.25)
    assert env.embed_calls == 8

def test_un_fotograma_no_dispara_alerta_con_dos_rostros(env):
    env.boxes = [(0, 0, 80, 80), (300, 0, 80, 80)]
    env.best_match = (META, 0.6)
    pipeline._process_real(env.frame, env.cfg, now=0.0)
    assert env.alerts == []

def test_coincidencia_se_confirma_en_dos_ciclos_y_sigue_alertando(env):
    env.best_match = (META, 0.6)
    for i in range(3):
        pipeline._process_real(env.frame, env.cfg, now=i * 0.25)
    assert len(env.alerts) == 2              # dedup_seconds decide en _maybe_alert

def test_nueva_version_de_galeria_fuerza_reconocimiento(env):
    env.best_match = (None, 0.1)
    pipeline._process_real(env.frame, env.cfg, now=0.0)
    gallery.version += 1
    pipeline._process_real(env.frame, env.cfg, now=0.25)
    assert env.embed_calls == 2

def test_persona_quitada_de_la_lista_deja_de_alertar(env):
    env.best_match = (META, 0.6)
    pipeline._process_real(env.frame, env.cfg, now=0.0)
    pipeline._process_real(env.frame, env.cfg, now=0.25)
    env.alerts.clear()
    gallery.version += 1
    env.best_match = (None, 0.0)
    pipeline._process_real(env.frame, env.cfg, now=0.5)
    assert env.alerts == []

def test_reconocimiento_periodico_corrige_identidad_tras_un_cruce(env):
    env.best_match = (None, 0.1)
    pipeline._process_real(env.frame, env.cfg, now=0.0)
    env.best_match = (META, 0.6)             # la caja ahora es otra persona
    pipeline._process_real(env.frame, env.cfg, now=1.0)
    pipeline._process_real(env.frame, env.cfg, now=1.25)
    assert len(env.alerts) == 1

def test_cuenta_reconocimientos_hechos_y_evitados(env):
    env.best_match = (None, 0.1)
    for i in range(4):
        pipeline._process_real(env.frame, env.cfg, now=i * 0.25)
    assert (pipeline.embeds_computed, pipeline.embeds_skipped) == (1, 3)
```

La fixture pone a cero `embeds_computed` y `embeds_skipped` antes de cada prueba.

Agregar a `test_settings_retention.py`:

```python
def test_recheck_interval_respeta_el_rango():
    assert settings.validate("recheck_interval_ms", 0) == 0
    assert settings.validate("recheck_interval_ms", 10000) == 10000
    with pytest.raises(ValueError):
        settings.validate("recheck_interval_ms", 10001)
```

- [ ] **Step 2: Ejecutar y comprobar que fallan**

Run: `pytest tests/test_pipeline_tracking.py tests/test_settings_retention.py -v`
Expected: fallan por el parámetro `now` y por la clave desconocida `recheck_interval_ms`.

- [ ] **Step 3: Agregar la configuración y `Gallery.version`**

Añadir `recheck_interval_ms` a `DEFAULTS` y `RULES` según las restricciones globales. `Gallery.version` empieza en 0 y sube dentro del lock al final de `load()`.

- [ ] **Step 4: Cambiar el pipeline**

- En `__init__`: crear `self._tracker = FaceTracker()`, `self._gallery_version = gallery.version` y los dos contadores en 0; eliminar `_streak`.
- En `reset_tracking`: llamar a `self._tracker.reset()` y limpiar `_last_alert`.
- En `_process_real`:
  - `now` por defecto es `time.time()`.
  - Si `gallery.version != self._gallery_version`, reiniciar solo el tracker y guardar la versión.
  - Tras detectar, `tracks = self._tracker.update([f.box for f in faces], now)`.
  - Por cada par: si `needs_embedding`, ejecutar `embed` y `best_match`, y llamar a `record_result`; si no, sumar a `embeds_skipped`.
  - Pasar a `record_result` el `meta` de `best_match`; el tracker lo quita si no supera el umbral.
  - Rellenar `face.best_score = track.sim`. `is_candidate = track.streak > 0`, `confirmed = track.confirmed`.
  - Si está confirmado: `face.match = {**track.meta, "score": track.sim}` y `_maybe_alert`.
  - `_maybe_alert` usa `time.time()`, sin cambios.
- Rótulos, `_publish_overlay` y `_log_detection` no cambian.
- `status()` añade `embeds_computed` y `embeds_skipped`.

- [ ] **Step 5: Ejecutar toda la suite**

Run: `pytest -v`
Expected: todas aprobadas (24 actuales más las nuevas).

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: reconoce rostros solo cuando hace falta"
```

### Task 3: medición con video

**Files:**
- Modify: `backend/scripts/benchmark_engine.py`
- Modify: `README.md:356`, `docs/pruebas.md:106`
- Test: `backend/tests/test_tracker.py`

**Interfaces:**
- Consumes: `FaceTracker` de la Task 1; `engine.detect`, `engine.embed`.
- Produces: `simulate(detections, recheck_s, threshold, confirm_frames, embed_fn) -> dict` con las claves `embeds`, `skipped` y `confirmed_frames`. `detections` es una lista de `(tiempo_video, [Box])`, y `embed_fn(indice_ciclo, indice_rostro)` devuelve `(meta, sim)`.

- [ ] **Step 1: Escribir la prueba que falla**

```python
def test_simulate_compara_con_y_sin_seguimiento():
    det = [(i * 0.25, [(100, 100, 80, 80)]) for i in range(8)]
    fn = lambda c, f: (None, 0.1)
    assert simulate(det, 0.0, 0.42, 2, fn)["embeds"] == 8
    con = simulate(det, 1.0, 0.42, 2, fn)
    assert (con["embeds"], con["skipped"]) == (2, 6)
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `pytest tests/test_tracker.py::test_simulate_compara_con_y_sin_seguimiento -v`
Expected: `simulate` no existe.

- [ ] **Step 3: Implementar `simulate` y `--video`**

`python -m scripts.benchmark_engine --video ruta.mp4 referencia.jpg`:
- Lee el video con `cv2.VideoCapture` y toma un fotograma cada 250 ms de video.
- La plantilla de `referencia.jpg` se compara con producto punto.
- Ejecuta las dos pasadas (`0.0` y `1.0`) con el reloj del video.
- Imprime llamadas a SFace, tiempo total, tiempo por fotograma y fotogramas confirmados.
- Si el video no abre, imprime un error y devuelve 1.
- Sin `--video`, el modo de fotografías no cambia.

- [ ] **Step 4: Ejecutar la prueba**

Run: `pytest tests/test_tracker.py -v`
Expected: 12 pruebas aprobadas.

- [ ] **Step 5: Documentar el comando**

Añadir una línea junto a cada referencia actual en `README.md` y `docs/pruebas.md`.

- [ ] **Step 6: Comprobar y hacer commit**

Run: `pytest -v`
Expected: todas aprobadas.

```bash
git add backend README.md docs/pruebas.md
git commit -m "feat: medición de seguimiento con video"
```
