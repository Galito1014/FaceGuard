# Cómo contribuir a FaceGuard AI

¡Gracias por su interés! Las contribuciones se aceptan bajo la licencia Apache 2.0 del proyecto.

## Antes de empezar

- Para cambios grandes, abra primero un **issue** y explique la idea.
- Las vulnerabilidades **no** van en issues: siga [SECURITY.md](SECURITY.md).
- **Nunca suba fotografías reales de personas, bases de datos, claves ni archivos `.env`.** Para pruebas use la imagen *Astronaut* (NASA, dominio público, incluida en scikit-image) o imágenes sintéticas. El CI rechaza archivos `.db`, `.onnx`, `.env`, claves y secretos.

## Preparar el entorno

Vea [docs/desarrollo.md](docs/desarrollo.md). Resumen:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m scripts.download_models
python -m pytest -q
```

## Reglas del proyecto

1. **Un solo núcleo.** La lógica de reconocimiento, base de datos, alertas y permisos vive en `backend/` y la usan Desktop y Raspberry Pi. No duplique lógica en `desktop/` ni en los instaladores.
2. **Pruebas.** Todo cambio de comportamiento lleva una prueba en `backend/tests/`. `python -m pytest -q` debe pasar.
3. **Base de datos.** Los cambios de esquema van en una migración nueva `backend/migrations/NNN_nombre.sql`; nunca edite una migración publicada.
4. **Privacidad por defecto.** Nada nuevo puede enviar datos fuera del equipo sin que el usuario lo active explícitamente. Ninguna función puede tratar una coincidencia como identificación definitiva.
5. **Seguridad por defecto.** Las opciones nuevas deben venir en su valor más seguro.
6. **Idioma.** La interfaz y la documentación están en español.

## Pull requests

- Una rama por cambio; describa qué cambia y cómo lo probó.
- Si toca el panel, incluya una captura (con datos ficticios).
- Si toca instaladores, indique en qué plataformas lo probó de verdad.
