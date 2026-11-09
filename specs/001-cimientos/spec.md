# Feature Specification: Cimientos del proyecto

**Feature Branch**: `hito-1-cimientos`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "El propietario necesita un proyecto base que permita levantar con un solo comando el servidor MCP y la base de datos en su equipo de desarrollo, ejecutar migraciones y comprobar desde un cliente MCP que una tool `ping` responde indicando si el servidor y la base de datos están operativos. El proyecto debe poder levantarse desde cero siguiendo solo el README, tener una estructura de carpetas en capas (dominio, servicios, base de datos y MCP) alineada con docs/plan-tecnico.md, pruebas automáticas, una verificación de estilo que corra en cada push a GitHub, y un registro del consumo de memoria de los servicios. Alcance: solo cimientos; no incluye acceso remoto, autenticación ni tablas de negocio. Respeta .specify/memory/constitution.md y docs/plan-tecnico.md. Incluye pruebas automáticas que verifiquen los criterios de aceptación."

**Hito**: 1 (Cimientos), según `HITOS.md`.

## Clarifications

### Session 2026-11-09

- Q: ¿Qué versión del SDK de MCP fijamos y con qué clase se construye el servidor? → A: `mcp==2.3.0` fijada exacta, con `MCPServer` importada desde `mcp.server.mcpserver` (verificado el 2026-11-09 en PyPI y en la guía oficial de migración v1 → v2). Condiciones: prueba de humo que importa `MCPServer` desde esa ruta y falla si cambia; versión, fecha de verificación y ruta de importación registradas en `docs/plan-tecnico.md`; actualizar el SDK es una decisión deliberada (cambiar el número en `pyproject.toml`, correr las pruebas y anotar el cambio).
- Q: ¿Usamos Streamable HTTP como transporte del servidor MCP desde el Hito 1, publicado solo en 127.0.0.1? → A: Sí, Streamable HTTP desde este hito, publicado solo en `127.0.0.1`. Se corrige `HITOS.md`: el transporte pasa del Hito 2 al Hito 1.
- Q: ¿En qué idioma van los nombres de código y base de datos? → A: Código y base de datos en inglés; documentación y mensajes al usuario en español.
- Q: ¿Se confirma uv como gestor de entornos y dependencias? → A: Sí, uv.
- Q: ¿Qué responde `ping` cuando la base de datos está caída y cuánto espera? → A: Un estado estructurado (servidor `ok`, base `error` con un mensaje breve en español), con un tiempo límite de conexión a la base de 2 segundos.
- Q: ¿Qué corre la verificación automática en GitHub? → A: Estilo (ruff) y pruebas unitarias en cada push; las pruebas de integración corren en local.
- Q: ¿Cómo se fija la versión de la base de datos? → A: Versión mayor fijada (PostgreSQL 18, la mayor vigente con soporte; la 19 solo está en RC al 2026-11-09), nunca `latest`.
- Q: ¿Cuándo y cómo se mide la memoria? → A: En reposo (servicios recién levantados y estabilizados) y después de 20 llamadas a `ping`, para cada servicio; se registra en `docs/plan-tecnico.md` con fecha y equipo.
- Q: ¿Desde dónde se miden los criterios de éxito de tiempo y de arranque? → A: Los 15 minutos empiezan en `git clone` con Docker y uv ya instalados y terminan en una respuesta correcta de `ping`; el criterio de arranque son 5 arranques desde cero, borrando los datos locales entre intentos (`docker compose down -v`).
- Q: ¿Qué escenarios deben estar explícitos? → A: Migración reversible (bajar a la versión base y volver a subir), verificación en GitHub que falla ante una prueba rota, y recuperación de `ping` cuando la base vuelve.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Levantar el proyecto y comprobar que está vivo (Priority: P1)

El propietario, en su equipo de desarrollo, ejecuta un solo comando que levanta la base de datos y
el servidor MCP. Después aplica las migraciones y, desde un cliente MCP local, llama a la tool
`ping`. La respuesta le dice si el servidor está operativo y si la base de datos responde.

**Why this priority**: es la base de todos los hitos siguientes. Sin un servidor que arranque, se
conecte a la base y responda a un cliente MCP, no se puede construir ni probar nada más.

**Independent Test**: en un equipo con el proyecto clonado y configurado, se ejecuta el comando de
arranque, se aplican las migraciones y se llama a `ping` desde un cliente MCP local; la respuesta
indica servidor operativo y base de datos operativa.

**Acceptance Scenarios**:

1. **Given** el proyecto configurado y ningún servicio corriendo, **When** el propietario ejecuta el
   comando de arranque, **Then** la base de datos y el servidor MCP quedan corriendo sin errores.
2. **Given** los servicios corriendo y una base de datos vacía, **When** el propietario aplica las
   migraciones, **Then** terminan sin errores y la base queda en la última versión.
3. **Given** los servicios corriendo y las migraciones aplicadas, **When** un cliente MCP local
   llama a `ping`, **Then** la respuesta indica que el servidor y la base de datos están operativos.
4. **Given** el servidor corriendo pero la base de datos detenida, **When** un cliente MCP llama a
   `ping`, **Then** la respuesta indica que el servidor está operativo y la base de datos no, con
   un mensaje claro, sin colgarse ni devolver un error sin explicación.
5. **Given** datos de prueba en la base, **When** el propietario detiene y vuelve a levantar los
   servicios, **Then** los datos siguen ahí.
6. **Given** las migraciones aplicadas, **When** el propietario revierte hasta la versión base y
   las vuelve a aplicar, **Then** ambas operaciones terminan sin errores y la base queda en la
   última versión.
7. **Given** `ping` informando base de datos no operativa, **When** la base vuelve a estar
   disponible, **Then** la siguiente llamada a `ping` informa base operativa sin reiniciar el
   servidor.

---

### User Story 2 - Calidad comprobada en cada cambio (Priority: P2)

El propietario corre las pruebas automáticas y la verificación de estilo en su equipo, y cada vez
que sube cambios a GitHub esas verificaciones corren solas y le muestran si pasaron.

**Why this priority**: la gobernanza exige que cada hito incluya sus pruebas y no se cierre con
pruebas fallando. Tener las verificaciones desde el primer hito evita acumular deuda.

**Independent Test**: se corren las pruebas y la verificación de estilo localmente (pasan); se
sube un cambio con un error de estilo deliberado a una rama y la verificación en GitHub falla;
al corregirlo, pasa.

**Acceptance Scenarios**:

1. **Given** el proyecto recién clonado, **When** el propietario corre las pruebas, **Then** existe
   al menos una prueba unitaria y una de integración, y todas pasan.
2. **Given** un push a GitHub, **When** terminan las verificaciones automáticas, **Then** el
   resultado (éxito o falla) de estilo y pruebas unitarias es visible en GitHub.
3. **Given** un cambio con un error de estilo, **When** se sube a GitHub, **Then** la verificación
   falla e identifica el problema.
4. **Given** un cambio con una prueba unitaria rota, **When** se sube a GitHub, **Then** la
   verificación falla e identifica la prueba.
5. **Given** el código del proyecto, **When** se ejecuta la prueba de arquitectura, **Then** confirma
   que la capa de dominio no depende de la capa MCP ni de la capa de base de datos.

---

### User Story 3 - Levantar desde cero solo con el README (Priority: P3)

Un tercero (o el propietario dentro de seis meses) clona el repositorio en un equipo con las
herramientas del Hito 0 instaladas y, siguiendo únicamente el README, configura, levanta, migra,
llama a `ping` y corre las pruebas.

**Why this priority**: garantiza que el proyecto es reproducible y que el conocimiento no queda solo
en la cabeza del propietario. Depende de que las historias 1 y 2 existan.

**Independent Test**: una persona que no participó en el desarrollo sigue el README en un clon
limpio y llega a una respuesta correcta de `ping` sin pedir ayuda ni ejecutar pasos que no estén
escritos.

**Acceptance Scenarios**:

1. **Given** un clon limpio del repositorio, **When** alguien sigue el README paso a paso, **Then**
   llega a una respuesta correcta de `ping` sin pasos adicionales.
2. **Given** el README, **When** se busca cómo configurar las variables, **Then** remite a
   `.env.example`, que documenta cada variable sin valores reales.

---

### User Story 4 - Saber cuánta memoria consume (Priority: P3)

Con todo levantado, el propietario mide el consumo de memoria de la base de datos y del servidor
MCP y lo deja anotado como referencia para el homelab, que es un equipo con pocos recursos.

**Why this priority**: el requerimiento de liviandad exige que el sistema corra cómodamente en el
homelab; medir desde el inicio permite detectar crecimientos más adelante.

**Independent Test**: con los servicios corriendo, se toma la medición de memoria de cada servicio
y se verifica que el valor quedó anotado en `docs/plan-tecnico.md`.

**Acceptance Scenarios**:

1. **Given** los dos servicios recién levantados y estabilizados, **When** el propietario toma la
   medición en reposo y otra después de 20 llamadas a `ping`, **Then** obtiene el consumo de
   memoria de cada servicio en ambos momentos y lo anota en `docs/plan-tecnico.md` con fecha y
   equipo.

---

### Edge Cases

- El servidor MCP arranca antes de que la base de datos esté lista: no debe reportarse operativo
  mientras la base no responda, y debe recuperarse solo cuando la base esté lista.
- Falta el archivo de configuración local o una variable obligatoria: el arranque falla con un
  mensaje que dice qué falta, sin mostrar valores secretos.
- El puerto de la base de datos o del servidor ya está ocupado en el equipo: el arranque falla con
  un mensaje claro.
- Se aplican las migraciones dos veces seguidas: la segunda vez no hace nada y no falla.
- La base de datos se detiene mientras el servidor corre: `ping` informa base no operativa en menos
  de 5 segundos (tiempo límite de conexión de 2 segundos); al volver la base, `ping` vuelve a
  informar operativa sin reiniciar el servidor.
- La base de datos intenta ser alcanzada desde otro equipo de la red: no debe ser accesible.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El proyecto MUST permitir levantar la base de datos y el servidor MCP con un solo
  comando en el equipo de desarrollo.
- **FR-002**: La base de datos MUST ser accesible solo desde el propio equipo, no desde otros
  equipos de la red.
- **FR-003**: Los datos de la base MUST persistir cuando los servicios se detienen y se vuelven a
  levantar.
- **FR-004**: El servidor MCP MUST NOT reportarse operativo mientras la base de datos no esté lista.
- **FR-005**: El proyecto MUST tener un mecanismo de migraciones versionadas, con una primera
  migración base que no crea tablas de negocio. Aplicar todas las migraciones sobre una base vacía
  MUST terminar sin errores, y reaplicarlas MUST NOT fallar.
- **FR-006**: El servidor MUST exponer a clientes MCP locales, mediante el transporte Streamable
  HTTP publicado solo en `127.0.0.1`, una tool `ping` que informe por separado el estado del
  servidor y el estado de la base de datos.
- **FR-007**: `ping` MUST devolver un estado estructurado: servidor `ok` y base de datos `ok` o
  `error`. Si la base no responde dentro de un tiempo límite de conexión de 2 segundos, `ping` MUST
  responder igualmente con servidor `ok`, base `error` y un mensaje breve en español que explique
  el motivo.
- **FR-008**: `ping` MUST devolver solo información de estado, sin credenciales, cadenas de conexión
  ni otros datos internos (principio 3.10, minimización).
- **FR-009**: La configuración MUST leerse de variables de entorno. Cada variable MUST estar
  documentada en `.env.example` sin valores reales, y ningún secreto MUST quedar en el repositorio.
- **FR-010**: El código MUST organizarse en capas de dominio, servicios, base de datos y MCP,
  alineadas con `docs/plan-tecnico.md`. La capa de dominio MUST NOT depender de la capa MCP ni de la
  capa de base de datos, y una prueba automática MUST verificarlo.
- **FR-011**: El proyecto MUST incluir pruebas automáticas: al menos una unitaria y una de
  integración. La de integración MUST llamar a `ping` contra una base de datos real.
- **FR-012**: En cada push a GitHub MUST correr automáticamente la verificación de estilo y las
  pruebas unitarias, con el resultado visible en GitHub.
- **FR-013**: Las dependencias MUST gestionarse con uv y quedar fijadas en su archivo de bloqueo, de
  modo que dos instalaciones desde el mismo commit obtengan las mismas versiones.
- **FR-014**: El README MUST permitir levantar el proyecto desde cero: requisitos, configuración,
  arranque, migraciones, llamada a `ping` y ejecución de pruebas.
- **FR-015**: El consumo de memoria de la base de datos y del servidor MCP MUST medirse en reposo
  (recién levantados y estabilizados) y después de 20 llamadas a `ping`, y quedar anotado en
  `docs/plan-tecnico.md` como valor de referencia, con fecha y equipo.
- **FR-016**: Los nombres de código, tablas y columnas MUST estar en inglés; la documentación y los
  mensajes al usuario MUST estar en español. La convención MUST quedar escrita en
  `docs/plan-tecnico.md`.
- **FR-017**: Este hito MUST NOT incluir tablas de negocio, datos financieros, acceso remoto ni
  autenticación.
- **FR-018**: El SDK de MCP MUST quedar fijado en una versión exacta (`mcp==2.3.0`) y el servidor
  MUST construirse con `MCPServer` importada desde `mcp.server.mcpserver`. Una prueba de humo
  MUST importar `MCPServer` desde esa ruta y fallar si la ruta deja de existir.
- **FR-019**: `docs/plan-tecnico.md` MUST registrar la versión fijada del SDK de MCP, la fecha en que
  se verificó y la ruta de importación.
- **FR-020**: Actualizar el SDK de MCP MUST ser una decisión deliberada: cambiar el número de versión
  en `pyproject.toml`, correr todas las pruebas y anotar el cambio en `docs/plan-tecnico.md`. El
  procedimiento MUST quedar escrito en el README o en el plan técnico.
- **FR-021**: La base de datos MUST usar una versión mayor fijada (PostgreSQL 18), nunca `latest`.

### Reglas citadas

- Gobernanza, regla no negociable 1: ningún dato financiero real antes del hito de autenticación
  (este hito no guarda datos de negocio; FR-017).
- Gobernanza, regla no negociable 2: lógica de negocio en una capa propia, independiente de MCP y de
  la base de datos (FR-010).
- Gobernanza, regla no negociable 4: el hito incluye sus pruebas automáticas y no se cierra con
  pruebas fallando (FR-011, FR-012).
- Principio 3.10: minimización de la información que devuelven las tools (FR-008).

### Key Entities

- **Estado de salud**: lo que informa `ping`. Incluye el estado del servidor (`ok`), el estado de la
  base de datos (`ok` o `error`) y, cuando la base está en `error`, un mensaje breve en español que
  explique el motivo.
- **Versión del esquema**: la última migración aplicada a la base de datos. Permite saber si una
  base está al día.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una persona que no participó en el desarrollo, con Docker y uv ya instalados, obtiene
  una respuesta correcta de `ping` en menos de 15 minutos siguiendo solo el README, contando desde
  `git clone` hasta la respuesta.
- **SC-002**: El comando de arranque levanta ambos servicios sin errores en 5 de 5 arranques
  consecutivos desde cero, borrando los datos locales entre intentos (`docker compose down -v`).
- **SC-003**: Aplicar las migraciones sobre una base vacía termina sin errores en el 100 % de los
  intentos, y una segunda aplicación consecutiva tampoco falla.
- **SC-004**: `ping` responde en menos de 2 segundos con ambos componentes operativos, y en menos
  de 5 segundos cuando la base de datos está detenida.
- **SC-005**: El 100 % de las pruebas automáticas pasan en el equipo de desarrollo, y la
  verificación automática en GitHub pasa en el último commit del hito.
- **SC-006**: Un push con un error de estilo deliberado hace fallar la verificación automática en
  GitHub en el 100 % de los casos.
- **SC-007**: El consumo de memoria de cada servicio, en reposo y después de 20 llamadas a `ping`,
  queda registrado en `docs/plan-tecnico.md` antes de cerrar el hito.
- **SC-008**: Un push con una prueba unitaria rota hace fallar la verificación automática en GitHub
  en el 100 % de los casos.

## Assumptions

- El equipo de desarrollo es el del propietario, con las herramientas verificadas en el Hito 0
  (control de versiones, contenedores, lenguaje y gestor de dependencias).
- El repositorio está en GitHub y las verificaciones automáticas se ejecutan ahí.
- Las pruebas de integración, que necesitan una base de datos real, corren en el equipo de
  desarrollo; en GitHub corren la verificación de estilo y las pruebas unitarias, como indica
  `HITOS.md`.
- En este hito no hay un límite de memoria que cumplir: solo se registra el valor de referencia.
- El cliente MCP local para probar `ping` puede ser una herramienta de inspección de MCP o un
  cliente de prueba propio.
- Las decisiones técnicas pendientes del Hito 1 (SDK de MCP, transporte, idioma de los nombres,
  gestor de dependencias, versión de la base de datos) quedaron resueltas en Clarifications y
  registradas en `docs/plan-tecnico.md`.
