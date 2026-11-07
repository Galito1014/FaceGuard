# Hardware y conexiones — FaceGuard AI

## Componentes

| Componente | Función |
|---|---|
| Raspberry Pi 4 Model B (8 GB) | Procesa el video, ejecuta los modelos, guarda la base de datos y sirve el panel web |
| Cámara web USB 720p/1080p | Sensor: capta los rostros en la entrada |
| microSD 32 GB clase A1/A2 | Sistema operativo, aplicación y datos cifrados |
| Fuente oficial USB-C 5,1 V 3 A | Evita la subtensión (que reduce la velocidad de la CPU) |
| Case con disipador y ventilador | Mantiene la temperatura < 70 °C en uso continuo |
| LED rojo de 5 mm + resistencia de 330 Ω | Actuador: alerta visual en portería |
| Buzzer piezoeléctrico de 2 patas (activo o pasivo) | Actuador: alerta sonora. Un buzzer magnético de 5 V requiere transistor (ver abajo) |
| Protoboard y cables dupont hembra-macho | Conexiones |

## Conexión a los pines GPIO (numeración BCM)

```
 Conector de 40 pines — extremo del pin 1 (lado de los LED de la placa)
          fila interior        fila exterior
 3V3    ( 1)  ·            ·  ( 2)  5V    ◄── ventilador rojo
 GPIO2  ( 3)  ·            ·  ( 4)  5V
 GPIO3  ( 5)  ·            ·  ( 6)  GND   ◄── ventilador negro
 GPIO4  ( 7)  ·            ·  ( 8)  GPIO14
 GND    ( 9)  ●──────────────────────────────── cátodo del LED (pata corta)
 GPIO17 (11)  ●──[220-330 Ω]──►|  ánodo del LED (pata larga)
 GPIO27 (13)  ●──────────────────────────────── buzzer (+)
              ·            ●  (14)  GND   ───── buzzer (−)
```

| Señal | GPIO (BCM) | Pin físico | Conexión |
|---|---|---|---|
| LED (+) | GPIO17 | 11 | Resistencia 220-330 Ω en serie → ánodo (pata larga) |
| LED (−) | — | 9 (GND) | Cátodo (pata corta) |
| Buzzer (+) | GPIO27 | 13 | Pata "+" (o la más larga) |
| Buzzer (−) | — | 14 (GND) | Pata "−" |
| Ventilador | — | 2 o 4 (5 V) y 6 (GND) | Solo alimentación: no usa GPIO ni choca con 17/27 |

- **Pines permitidos** para el LED y el buzzer: GPIO 4, 5, 6, 12, 13, 16-27 (libres de I2C, UART y SPI). Se cambian en
  **Configuración → Hardware & Alarm Settings** sin reiniciar.
- **Corriente:** un GPIO entrega 3,3 V; conviene no superar ~16 mA por pin. El LED con 330 Ω consume ~4 mA.
  Un buzzer **piezoeléctrico** consume pocos mA y se conecta directo. Un buzzer **magnético** (≈30 mA) o cualquier
  buzzer de 5 V que deba sonar fuerte necesita un transistor:

```
 GPIO27 ──[1 kΩ]── base   2N2222 (NPN)
 5V (pin 2) ── buzzer (+)   buzzer (−) ── colector
 emisor ── GND (pin 14)
```

### ¿Buzzer activo o pasivo?

Ejecute la **Prueba 2** con *Tipo de buzzer = Activo*. Si suena un tono, es activo. Si no suena o solo hace un clic,
es **pasivo**: cambie el tipo a *Pasivo (PWM)* (frecuencia por defecto 2500 Hz), guarde y repita la prueba.

## Comportamiento de la alarma

Solo una coincidencia **confirmada** (el número de análisis seguidos configurado, 3 por defecto) con una persona de la
**lista de alerta** activa la alarma. Una persona desconocida, una coincidencia bajo el umbral o una persona autorizada
nunca la activan.

| Acción | Valor por defecto |
|---|---|
| LED rojo | Encendido fijo 5 s |
| Buzzer | 3 s, intermitente (0,25 s encendido / 0,15 s apagado) |
| Cooldown por persona | 15 s sin otra alerta ni alarma de la misma persona |
| Buzzer desde nivel | Bajo (toda coincidencia) |

- La alarma corre en su propio hilo: el video nunca espera. Una alarma nueva reemplaza a la que esté en curso.
- **Silenciar:** botón en el Dashboard (operador o superior) y en Hardware & Alarm Settings.
- Cada alerta guarda el **estado de la alarma** (activada, simulada, desactivada, error) y cada activación queda en el
  **historial de activaciones** (se conserva el mismo tiempo que los eventos).
- Las salidas se abren **apagadas** al arrancar y se apagan al detener el servicio. Si la Raspberry Pi se reinicia
  durante una alarma, al volver no continúa sonando.
- Si los pines no se pueden abrir (otro proceso los usa, falta permiso, falta lgpio), el panel muestra **Error de
  hardware** con la causa y el reconocimiento facial sigue funcionando. En Windows o Linux sin GPIO se usa el modo
  simulado.
- La alarma se inicializa con el servicio `faceguard` (systemd): no hay scripts adicionales que ejecutar.

## Pruebas de diagnóstico

Desde **Hardware & Alarm Settings → Pruebas de diagnóstico**, o por consola con el servicio detenido:

```bash
sudo systemctl stop faceguard
cd /opt/faceguard-ai/backend && sudo -u faceguard ../venv/bin/python -m scripts.manage hardware-test todas
sudo systemctl start faceguard
```

| Prueba | Qué comprueba |
|---|---|
| 1 — LED | LED encendido 3 s |
| 2 — Buzzer | Buzzer 2 s |
| 3 — Alarma completa | LED y buzzer a la vez |
| 4 — Blacklist | Una detección de prueba confirmada pasa por el mismo código que el video y enciende las salidas (genera una alerta [SIMULADO]) |
| 5 — Desconocido | Rostro desconocido, coincidencia dudosa y persona autorizada no activan nada |

Si una prueba falla, el resultado indica la causa probable (polaridad del LED, buzzer pasivo, pin ocupado, permisos).

## Ubicación de la cámara

- A la altura del rostro (1,6–1,8 m), apuntando a la puerta de ingreso, a **1–2 m** de donde pasan las personas. El rostro debe ocupar al menos 80 px de ancho en la imagen.
- Evitar contraluz (una ventana o la calle detrás de la persona). Si hace falta, agregar una luz frontal.
- La Raspberry Pi va dentro de la portería, protegida; solo la cámara queda en el ingreso.

## Función del dispositivo intermediario (red)

La Raspberry Pi actúa como **servidor local (edge computing)**: recibe el video por USB, lo procesa en el propio dispositivo y publica el panel web en la red local (Wi-Fi o Ethernet). El guardia abre el panel desde una PC, tablet o celular conectado a la misma red. Las imágenes **no salen del edificio** y no hace falta Internet ni servicios en la nube.
