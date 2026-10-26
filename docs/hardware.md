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
| Buzzer activo de 3,3–5 V (módulo con transistor, p. ej. KY-012) | Actuador: alerta sonora |
| Protoboard y cables dupont hembra-macho | Conexiones |

## Conexión a los pines GPIO (numeración BCM)

```
 Raspberry Pi 4 (vista superior, pines 1-14)
 ┌──────────────────────────────┐
 │ (1) 3V3       (2) 5V         │
 │ (3) GPIO2     (4) 5V         │
 │ (5) GPIO3     (6) GND        │
 │ (7) GPIO4     (8) GPIO14     │
 │ (9) GND ●─────────────────┐  │      LED rojo
 │(11) GPIO17 ●──[330 Ω]──►|─┘  │      (ánodo = pata larga hacia la resistencia)
 │(13) GPIO27 ●───────────── I/O  buzzer
 │(14) GND    ●───────────── GND  buzzer
 │ (1) 3V3    ●───────────── VCC  buzzer (o pin 2 = 5 V si el módulo lo requiere)
 └──────────────────────────────┘
```

| Señal | Pin físico | GPIO (BCM) | Destino |
|---|---|---|---|
| LED | 11 | GPIO17 | Resistencia 330 Ω → ánodo del LED; cátodo → GND (pin 9) |
| Buzzer | 13 | GPIO27 | Entrada I/O del módulo buzzer |
| Alimentación del buzzer | 1 (3,3 V) o 2 (5 V) | — | VCC del módulo |
| Tierra | 9 y 14 | — | GND del LED y del buzzer |

- Los pines se pueden cambiar en **Configuración → Alertas y GPIO** (sin reiniciar).
- Con **Probar** en esa misma pantalla, el LED parpadea y el buzzer suena 2 s.
- **No conecte un buzzer de 5 V sin transistor directamente a un GPIO**: los pines entregan 3,3 V y pocos mA. Use un módulo con transistor o un NPN (2N2222) con una resistencia de 1 kΩ en la base.

## Comportamiento de la alarma

| Nivel de la alerta | Notificación en el panel | LED | Buzzer (por defecto) |
|---|---|---|---|
| Bajo | ✅ | parpadeo lento | — |
| Medio | ✅ | parpadeo lento | ✅ |
| Alto | ✅ | parpadeo rápido | ✅ |

La duración (5 s por defecto) y el nivel mínimo para el buzzer se configuran en el panel.

## Ubicación de la cámara

- A la altura del rostro (1,6–1,8 m), apuntando a la puerta de ingreso, a **1–2 m** de donde pasan las personas. El rostro debe ocupar al menos 80 px de ancho en la imagen.
- Evitar contraluz (una ventana o la calle detrás de la persona). Si hace falta, agregar una luz frontal.
- La Raspberry Pi va dentro de la portería, protegida; solo la cámara queda en el ingreso.

## Función del dispositivo intermediario (red)

La Raspberry Pi actúa como **servidor local (edge computing)**: recibe el video por USB, lo procesa en el propio dispositivo y publica el panel web en la red local (Wi-Fi o Ethernet). El guardia abre el panel desde una PC, tablet o celular conectado a la misma red. Las imágenes **no salen del edificio** y no hace falta Internet ni servicios en la nube.
