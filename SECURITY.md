# Política de seguridad

FaceGuard AI maneja datos biométricos. Tomamos en serio cualquier fallo de seguridad.

## Versiones con soporte

Solo la **última versión publicada** en [GitHub Releases](https://github.com/Galito1014/FaceGuard/releases) recibe correcciones de seguridad. Actualice antes de informar un problema para comprobar que sigue ocurriendo.

## Cómo informar una vulnerabilidad

**No abra un issue público.** Use el aviso privado de GitHub:

1. Vaya a la pestaña **Security** del repositorio.
2. Pulse **Report a vulnerability** (GitHub Private Vulnerability Reporting).
3. Describa el problema, la versión, la plataforma (Windows, Linux o Raspberry Pi) y los pasos para reproducirlo.

No incluya fotografías reales de personas ni bases de datos con datos reales en el informe. Use datos de prueba.

Intentaremos responder en 7 días y publicar una corrección o una mitigación en 90 días. Le daremos crédito en las notas de la versión si lo desea.

## Alcance

Nos interesan especialmente:

- acceso al panel o a la API sin iniciar sesión, o saltarse los permisos de un rol;
- acceso al panel desde redes no autorizadas (por ejemplo, desde Internet en una Raspberry Pi);
- crear la cuenta administradora sin el código de configuración;
- lectura de fotografías, plantillas biométricas o claves de cifrado;
- ejecución de código a través de archivos subidos (fotos, respaldos);
- instaladores o actualizaciones que se puedan sustituir sin que falle la verificación SHA-256.

Fuera de alcance: problemas que requieren acceso físico o de administrador al equipo, ataques de denegación de servicio en la red local, y la precisión de los modelos de reconocimiento (infórmela como issue normal).

## Configuración segura recomendada

- Mantenga FaceGuard AI actualizado.
- En la Raspberry Pi, **no abra el puerto 8000 en el router**. Para acceso remoto use una VPN.
- Use contraseñas únicas y cree usuarios con el rol mínimo necesario.
- Proteja físicamente el equipo y, si es posible, cifre el disco completo.
- Guarde los respaldos y la clave de cifrado en lugares distintos.

Más detalles en [docs/seguridad-privacidad.md](docs/seguridad-privacidad.md).
