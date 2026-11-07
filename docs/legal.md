# Guía legal de uso de FaceGuard AI

> **Esto no es asesoría legal.** Es un resumen orientativo, no exhaustivo, para ayudar a identificar obligaciones. Las leyes cambian y su aplicación depende de cada caso. Consulte a un abogado de su jurisdicción antes de usar FaceGuard AI con personas reales. Última revisión del documento: noviembre de 2026.

## 1. Por qué importa

Una plantilla facial permite identificar a una persona de forma única: casi todas las leyes de protección de datos la tratan como **dato biométrico**, una categoría especial con más requisitos. Además, una falsa coincidencia puede provocar un trato injusto a una persona inocente.

FaceGuard AI está diseñado para **apoyar** a una persona (un guardia, un administrador), no para decidir. Es su responsabilidad mantenerlo así.

## 2. Principios que aplican casi en todas partes

1. **Base legal y finalidad.** Defina por escrito para qué usa el sistema (por ejemplo, avisar al guardia de la entrada si llega una persona con una orden de restricción vigente). No lo use para otra cosa.
2. **Consentimiento o autorización.** Para registrar a personas autorizadas (residentes, empleados) normalmente se necesita su consentimiento explícito e informado. Para la lista de alerta, un fundamento documentado (orden judicial, resolución del órgano de gobierno del edificio, denuncia formal).
3. **Transparencia.** Avisos visibles antes de entrar al área vigilada, que indiquen que hay reconocimiento facial, quién es el responsable y cómo ejercer derechos.
4. **Minimización y conservación limitada.** Registre solo a quien sea necesario y configure plazos de conservación cortos (Configuración → Conservación).
5. **Derechos de las personas.** Acceso, rectificación, eliminación y, donde aplique, oposición. FaceGuard AI permite eliminar registros y archivos.
6. **Seguridad.** Contraseñas fuertes, roles mínimos, equipo protegido físicamente, sin exposición a Internet.
7. **Decisión humana.** No tome decisiones automatizadas con efectos sobre una persona (impedir su paso, denunciarla) solo por una alerta.
8. **Evaluación de impacto.** En muchas jurisdicciones el tratamiento de biometría a gran escala o la vigilancia de espacios accesibles al público exige una evaluación de impacto previa.

## 3. Jurisdicciones (resumen)

| Jurisdicción | Normas principales | Puntos clave |
|---|---|---|
| **Unión Europea / EEE** | RGPD (art. 9); Reglamento de IA (Reglamento (UE) 2024/1689) | La biometría para identificar es categoría especial: requiere una excepción del art. 9 (p. ej., consentimiento explícito). El Reglamento de IA prohíbe la identificación biométrica remota en tiempo real en espacios de acceso público con fines policiales salvo excepciones, y clasifica muchos sistemas de identificación biométrica como de alto riesgo. Normalmente se exige evaluación de impacto (EIPD). Un uso privado para un edificio puede seguir siendo muy restringido: consulte a su autoridad de protección de datos |
| **Reino Unido** | UK GDPR, Data Protection Act 2018 | Similar al RGPD. La autoridad (ICO) ha sancionado usos de reconocimiento facial sin base legal suficiente |
| **Estados Unidos — Illinois** | Biometric Information Privacy Act (BIPA) | Aviso y **consentimiento por escrito** antes de recoger datos biométricos, política pública de retención y destrucción, prohibición de venderlos. Permite demandas privadas con indemnizaciones por infracción |
| **Estados Unidos — Texas, Washington** | CUBI (Texas), RCW 19.375 (Washington) | Aviso y consentimiento; límites a la conservación y la venta |
| **Estados Unidos — otros estados** | Leyes integrales de privacidad (p. ej., California CCPA/CPRA, Colorado, Virginia, Connecticut) y leyes locales (p. ej., Portland, Nueva York para comercios) | La biometría suele ser “dato sensible” con consentimiento o derecho de exclusión; algunas ciudades prohíben o exigen avisos para el reconocimiento facial en comercios |
| **Puerto Rico** | Constitución de Puerto Rico (art. II, sec. 8, protección de la vida privada); leyes federales de EE. UU. aplicables | No identificamos una ley específica de biometría; el derecho constitucional a la intimidad es amplio y aplica también entre particulares. Consulte a un abogado local |
| **México** | Ley Federal de Protección de Datos Personales en Posesión de los Particulares | La biometría se considera dato sensible: consentimiento expreso y por escrito, aviso de privacidad |
| **Brasil** | LGPD (Ley 13.709/2018) | Dato personal sensible; bases legales limitadas; la autoridad (ANPD) puede exigir informes de impacto |
| **Argentina** | Ley 25.326 | Datos sensibles; consentimiento; registro de bases de datos ante la autoridad |
| **Colombia** | Ley 1581 de 2012 | Dato sensible; autorización previa, expresa e informada; nadie puede ser obligado a entregarlo |
| **Chile** | Ley 19.628 y Ley 21.719 (nueva ley de protección de datos, con entrada en vigor diferida) | Dato sensible; requisitos reforzados con la nueva ley y su agencia de protección de datos |
| **Bolivia** | Constitución (arts. 21, 130–131) | Sin ley general de datos personales al momento de esta guía; aplique buenas prácticas internacionales (ver [seguridad-privacidad.md](seguridad-privacidad.md)) |

Si su país no aparece, busque la ley de protección de datos personales y las normas de videovigilancia locales; la mayoría sigue principios parecidos al RGPD.

## 4. Usos que no debe hacer con FaceGuard AI

- Abrir o bloquear puertas automáticamente según una coincidencia (el sistema no tiene prueba de vida y puede equivocarse).
- Vigilar a empleados, inquilinos o vecinos sin su conocimiento, o vigilar espacios privados ajenos (vivienda de otra persona, baños, vestidores).
- Registrar a personas por su origen, religión, orientación, opinión política u otras características protegidas.
- Compartir la lista de alerta o las capturas con terceros sin base legal.
- Usarlo donde la ley lo prohíba.

## 5. Lista de comprobación antes de usarlo en un lugar real

- [ ] Finalidad y base legal documentadas por escrito.
- [ ] Aprobación del órgano que corresponda (asamblea de copropietarios, dirección de la empresa).
- [ ] Evaluación de impacto, si su ley la exige.
- [ ] Consentimientos firmados de las personas autorizadas registradas.
- [ ] Documento que justifique cada registro de la lista de alerta.
- [ ] Avisos visibles en el acceso.
- [ ] Protocolo escrito para el guardia: verificar en persona y avisar; nunca actuar solo por la alerta.
- [ ] Plazos de conservación configurados.
- [ ] Procedimiento para atender solicitudes de acceso y eliminación.
- [ ] Usuarios con el rol mínimo; contraseñas únicas; equipo protegido.
