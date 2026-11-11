# Puro Pockets: hoja de ruta por hitos

**Versión:** 0.10 (borrador)
**Fecha:** 2026-11-09
**Fuentes de verdad:** reglas en `.specify/memory/constitution.md` (referenciadas como `RN-xx`); técnica en `docs/plan-tecnico.md`.
**Este documento define:** qué entrega cada hito, en qué orden y cuándo se considera terminado. No repite reglas de negocio ni el esquema de datos: los referencia.

---

## 1. Cómo se usa este documento con Spec Kit

Cada hito (menos el 0) se convierte en una carpeta `specs/NNN-nombre/` con su `spec.md`, un `plan.md` delgado y un `tasks.md`.

```
Por cada hito:
/speckit-specify  →  /speckit-clarify  →  /speckit-plan (delgado)
     →  /speckit-tasks  →  /speckit-analyze  →  /speckit-implement
```

- El bloque **"Prompt para /speckit-specify"** de cada hito es el texto de partida para el comando.
- La spec dice **qué** entrega el hito y **cómo se comprueba**; las reglas se citan (`RN-52`), nunca se reescriben.
- Al cerrar cada hito se actualiza `docs/plan-tecnico.md` si cambió el esquema o la arquitectura.
- Un hito se cierra solo cuando se cumple su **"Terminado cuando"**.

### Principios de la hoja de ruta
1. Cada hito termina en algo **demostrable** (desde terminal o desde Claude).
2. Lo más incierto se valida **temprano** (acceso remoto y OAuth antes que las reglas de dinero).

Las reglas no negociables (datos reales, capa de negocio, invariante de integridad y pruebas por hito) están en la sección **Gobernanza** de `.specify/memory/constitution.md`.

---

## 2. Vista general

| # | Hito | Entrega principal | Reglas que cubre |
|---|---|---|---|
| 0 | Preparación del terreno | Herramientas instaladas, repo ordenado, constitución y plan técnico listos | (gobernanza) |
| 1 | Cimientos | Proyecto Python, Docker Compose con Postgres, migraciones, tool `ping` | (técnico) |
| 2 | Acceso remoto sin datos | Túnel con dominio propio, deploy en homelab, conector en claude.ai | (técnico) |
| 3 | Autenticación | OAuth: solo tú puedes usar el MCP | (seguridad) |
| 4 | Bolsas y porcentajes | Bolsas, porcentajes por mes, saldo inicial | RN-01 a 03, 10 a 12, 54 |
| 5 | Ingresos base y gastos | Reparto del salario, gastos, CRC/USD, anulación (**MVP**) | RN-02, 03, 08 (reparto), 31 a 34, 37, 38, 53, 55 a 57, 59 |
| 6 | Extras y gastos fijos | Reparto de extras recomendado por Claude, gastos fijos | RN-04 a 09, 35, 36 |
| 7 | Bolsas flexibles y metas | Crear y archivar bolsas con reajuste, metas | RN-13 a 25, 28, 29 |
| 8 | Transferencias | Mover dinero entre bolsas con registro | RN-39 a 45, 58 |
| 9 | Cierre de mes | Déficits, sobrantes y cierre atómico | RN-46 a 52 |
| 10 | Dashboard | Estadísticas y gráficos | Sección 13 del plan técnico |
| 11 | Operación y endurecimiento | Respaldos probados, monitoreo, revisión de seguridad | (no funcional) |

El **MVP usable** llega al terminar el Hito 5: puedes cargar tu saldo inicial, registrar tu salario y tus gastos desde Claude y ver el estado de cada bolsa.

---

## 3. Decisiones que bloquean hitos

| Decisión pendiente | Debe resolverse antes de | Dónde se resuelve |
|---|---|---|
| Framework de la API para el dashboard | Hito 10 | `/speckit-clarify` del Hito 10 |

---

## Hito 0: Preparación del terreno

**Tipo:** checklist manual, sin spec (es preparación, no una funcionalidad).

**Objetivo:** dejar listo el equipo, el repositorio y los dos documentos madre antes de escribir código.

### 0.1 Instalar las herramientas en tu equipo de desarrollo

| Herramienta | Para qué | Nota |
|---|---|---|
| **Git** | Control de versiones | Configura nombre y correo (`git config`). |
| **Docker Desktop** (con WSL 2 en Windows) | Correr Postgres y el MCP en contenedores | Verifica con `docker --version` y `docker compose version`. |
| **Python** (versión estable vigente, 3.12 o superior) | Lenguaje del proyecto | Verifica con `python --version`. |
| **uv** | Gestor de entornos y dependencias de Python | Alternativa: `venv` + `pip`. Decídelo ahora y no cambies. |
| **Claude Code** | Implementar las specs con IA | Se abre en la raíz del repo. |
| **Editor** (por ejemplo VS Code) | Revisar y editar | Opcional pero recomendado. |
| **Node.js LTS** | Solo para el MCP Inspector (herramienta de prueba de MCP) | Opcional. |
| **Cliente de Postgres** (DBeaver o `psql`) | Mirar las tablas | Opcional. |
| **Spec Kit** | Ya instalado en tu repo | No reinstalar. |

Consulta la documentación oficial de cada herramienta para el comando de instalación actual.

### 0.2 Ordenar el repositorio
- [ ] Mover `.specify/` y `.claude/` de la subcarpeta `puro-pockets/` a la **raíz del repo**, y eliminar la subcarpeta vacía.
- [ ] Verificar que `README.md` esté guardado en **UTF-8**.
- [ ] Crear `.gitignore` **antes** del siguiente commit. Debe excluir: `.env`, `*.dump`, `*.sql` con datos reales, volúmenes de Postgres, `.venv/`, `__pycache__/`.
- [ ] Crear `.env.example` (sin valores reales) para documentar las variables.
- [ ] Crear `CLAUDE.md` en la raíz con una instrucción corta: leer primero la constitución y el plan técnico antes de implementar cualquier cosa.

### 0.3 Estructura de carpetas objetivo

```
puro-pockets/                    (raíz del repositorio)
├── CLAUDE.md
├── README.md
├── HITOS.md
├── .gitignore
├── .env.example
├── .specify/                    (Spec Kit)
│   ├── memory/constitution.md   ← ÚNICA constitución
│   └── templates/overrides/plan-template.md   ← plan delgado por hito
├── .claude/skills/              (comandos de Spec Kit)
├── docs/
│   └── plan-tecnico.md          ← ÚNICO plan técnico
└── specs/                       (una carpeta por hito, creadas por Spec Kit)
```

La estructura del **código** se crea en el Hito 1.

### 0.4 Documentos madre
- [ ] Ejecutar `/speckit-constitution` con el contenido reorganizado de `docs/origen/CONSTITUCION-origen.md` (secciones 1 a 11 y 14) y una sección de **gobernanza** con las reglas de la sección 1 de este documento.
- [ ] Crear `docs/plan-tecnico.md` (secciones 12, 13, 15, 16 y 17 de `docs/origen/CONSTITUCION-origen.md` + stack decidido + enlace a este documento, sin copiar el mapa de hitos).
- [ ] Crear el override de `plan-template.md` (plan delgado).

**Terminado cuando:** las herramientas responden a sus comandos de versión, Claude Code abre el repo y ve las skills de Spec Kit, la constitución está ratificada (sin marcadores `[PLACEHOLDER]`) y el plan técnico existe.

---

## Hito 1: Cimientos

**Objetivo:** un proyecto Python que arranca con Docker, se conecta a Postgres, tiene migraciones y expone una tool de prueba por MCP en tu propia máquina.

### Entregables
- **Proyecto Python** con `pyproject.toml`, dependencias fijadas (`uv.lock`) y estructura en capas:

```
src/puro_pockets/
├── config.py          # configuración desde variables de entorno
├── db/                # conexión, sesión y modelos (SQLAlchemy)
├── domain/            # reglas puras: reparto, conversión, saldos (sin DB, sin MCP)
├── services/          # casos de uso con transacciones
└── mcp/               # servidor y tools (delgadas: validan y llaman a services)
migrations/            # Alembic
tests/
├── unit/
└── integration/
```

- **Docker Compose** con dos servicios: `db` (Postgres con volumen y healthcheck) y `mcp` (tu servidor). El puerto de Postgres atado a `127.0.0.1`.
- **Dockerfile** del servidor MCP.
- **Alembic** inicializado, con una primera migración base.
- **Tool `ping`** que confirma que el servidor está vivo y que la base responde.
- **Transporte Streamable HTTP** del servidor MCP, publicado solo en `127.0.0.1` (en el Hito 2 se expone por el túnel).
- **Calidad:** `pytest` (una prueba unitaria y una de integración), `ruff` para estilo.
- **CI básico en GitHub Actions:** `ruff` y pruebas unitarias en cada push.
- **Convención de idioma** de tablas y código, decidida y escrita en el plan técnico.

### Prompt para /speckit-specify
> El propietario necesita un proyecto base que le permita levantar con un solo comando el servidor MCP y la base de datos en su equipo, correr migraciones y comprobar desde un cliente MCP que una tool `ping` responde indicando que el servidor y la base de datos están operativos. Debe incluir pruebas automáticas y una verificación de estilo en cada push. Incluye pruebas automáticas que verifiquen los criterios de aceptación.

### Terminado cuando
- `docker compose up` levanta la base y el MCP sin errores.
- `alembic upgrade head` corre limpio en una base vacía.
- Un cliente MCP local (el MCP Inspector o un cliente de prueba en Python) llama `ping` y recibe respuesta correcta.
- ruff y las pruebas unitarias pasan en GitHub Actions; las de integración pasan en el equipo de desarrollo.
- `docker stats --no-stream` muestra el consumo de memoria de los servicios `db` y `mcp` con todo levantado, y el valor queda anotado en `docs/plan-tecnico.md` como referencia para el homelab.
- Un tercero (o tú en seis meses) puede levantar el proyecto siguiendo solo el README.

---

## Hito 2: Acceso remoto sin datos

**Objetivo:** que Claude, desde el navegador y el celular, llame a tu servidor MCP en el homelab por una URL fija. **Sin datos reales todavía.**

### Entregables
- **Dominio:** DNS gestionado por Cloudflare (nameservers cambiados en Namecheap, con los registros existentes copiados y DNSSEC revisado).
- **Túnel con nombre** de Cloudflare hacia un subdominio fijo (`mcp.tudominio.com`), corriendo como contenedor en el Compose.
- **Despliegue en el homelab:** instalar Docker en el homelab, clonar el repo, crear `.env` real, `docker compose up -d`, política `restart: unless-stopped`.
- **Conector personalizado** agregado en claude.ai (Customize → Connectors).
- **Procedimiento de actualización** documentado: cómo traer cambios del repo y reiniciar.

### Prompt para /speckit-specify
> El propietario quiere llamar a la tool `ping` de su servidor MCP desde Claude en el navegador y en el celular, estando fuera de su casa. El servidor corre en su homelab y se publica en una URL HTTPS fija con su propio dominio. En este hito no se maneja información financiera. Incluye pruebas automáticas que verifiquen los criterios de aceptación.

### Riesgos y mitigaciones
- El endpoint queda público sin autenticación: solo expone `ping`, sin datos. Si prefieres, apaga el túnel entre sesiones de prueba.
- Un corte de luz o de internet deja el servicio fuera de línea: verifica que arranque solo al volver.

### Terminado cuando
- Desde claude.ai, **usando datos móviles** (otra red), Claude llama `ping` y obtiene respuesta.
- Tras reiniciar el homelab, el servicio vuelve solo y el conector sigue funcionando **sin reconfigurarlo**.
- La URL no ha cambiado.

---

## Hito 3: Autenticación

**Objetivo:** que solo tú puedas usar el MCP. Es la puerta de seguridad antes de guardar cualquier dato real.

### Contexto técnico
El SDK de MCP para Python implementa el lado del **servidor de recursos** de OAuth 2.1: tu MCP valida los tokens que emite un servidor de autorización separado. El SDK verifica; **emitir los tokens es trabajo aparte**. Por eso este hito tiene una decisión de diseño importante.

### Entregables
- **Decisión del servidor de autorización**, resuelta con `/speckit-clarify`. Candidatos:
  - Un servidor de autorización mínimo y propio (login con contraseña de un solo usuario, hash seguro, flujo OAuth con PKCE, metadatos de descubrimiento y registro de cliente).
  - Un proveedor de identidad externo (más completo, pero pesado para el hardware del homelab).
- **Verificador de tokens** en el MCP: sin token válido, responde 401.
- **Compatibilidad comprobada con el conector de claude.ai**, incluida la URL de callback de OAuth de Claude y la opción de client ID/secret, según la documentación vigente de Anthropic.
- **Registro de accesos** y límite básico de intentos.
- **Gestión de secretos:** contraseña y claves fuera del repo, rotables.

### Prompt para /speckit-specify
> El propietario necesita que solo él pueda invocar las tools del servidor MCP. Al agregar el conector en Claude debe aparecer un inicio de sesión; sin sesión válida, las llamadas deben rechazarse. Debe poder desconectar y reconectar el conector, y revocar el acceso si lo necesita. Incluye pruebas automáticas que verifiquen los criterios de aceptación.

### Terminado cuando
- Una llamada a `/mcp` sin token recibe 401.
- Agregas el conector en claude.ai, inicias sesión, y `ping` funciona.
- Desconectar y reconectar el conector funciona.
- Un token inválido o vencido es rechazado.
- **A partir de aquí se permite guardar datos reales.**

---

## Hito 4: Bolsas y porcentajes

**Objetivo:** el esqueleto del presupuesto: bolsas, cómo se reparte el dinero por mes y el saldo con el que arrancas.

### Entregables
- **Tablas** (con migración): `bolsas`, `categorias`, `budget_month_allocations`, y el registro de ingresos necesario para el saldo inicial.
- **Lógica de dominio:** validación de que los porcentajes sumen 100 (RN-01), copia de porcentajes del mes anterior (RN-03), reparto en enteros con residuo en la última bolsa (RN-08), comportamientos `consumo` y `acumulable` (RN-10 a 12).
- **Datos iniciales:** las bolsas Necesidades (consumo), Ahorro (acumulable) y Gustos (consumo). Los porcentajes sugeridos (50 %, 30 % y 20 %) los guarda el propietario desde Claude; no se guardan automáticamente para ningún mes.
- **Tools:** `set_allocation`, `get_allocation`, `preview_initial_balance`, `load_initial_balance`, `list_bolsas`.
- **Saldo inicial** (RN-54): una sola vez, por montos explícitos, que no cuenta como ingreso del mes.
- **Prueba del invariante de integridad** (sección 11.4) contra datos sintéticos: este es el primer hito que registra dinero (gobernanza, regla no negociable 3).

### Prompt para /speckit-specify
> El propietario quiere definir sus bolsas de dinero (Necesidades, Gustos y Ahorro) y los porcentajes en que se reparte su ingreso cada mes, y cargar una vez el saldo con el que arranca, repartido por montos entre las bolsas. Los porcentajes deben sumar 100, quedar guardados por mes y poder cambiarse sin alterar meses anteriores. Incluye pruebas automáticas que verifiquen los criterios de aceptación.

### Terminado cuando
- Desde Claude defines Necesidades 50 %, Ahorro 30 % y Gustos 20 % para un mes, y la app rechaza una suma distinta de 100.
- Cargas un saldo inicial y `list_bolsas` muestra el saldo de cada bolsa.
- Cambiar los porcentajes del mes siguiente no modifica el mes anterior.
- Hay pruebas del reparto con residuo (por ejemplo, ₡10.001 entre tres bolsas suma exactamente ₡10.001).
- La prueba del invariante pasa con el saldo inicial.

---

## Hito 5: Ingresos base y gastos (MVP)

**Objetivo:** el ciclo diario de uso. Al terminar, la app ya sirve para llevar tus finanzas.

### Entregables
- **Tablas** (migración `0004_movements`, que conserva los datos del Hito 4): moneda, monto original, tipo de cambio y anulación en `incomes`; `expenses`; `idempotency_keys`.
- **Ingreso base:** el salario de fin de mes se asigna al mes siguiente (u otro mes indicado) y se reparte con los porcentajes de ese mes o heredados (sección 5.1 de la constitución; RN-02, 03, 08). Con vista previa (`preview_income`; sin `confirm` no guarda).
- **Gastos:** contra cualquier bolsa, con categoría opcional (RN-31 a 34). Categorías con bolsa por defecto.
- **Monedas:** colones y dólares; conversión a colones al registrar, con el tipo de cambio indicado por el propietario y guardado en el movimiento (RN-55 a 57, decisión #12). Sin `float`.
- **Sobregasto:** no se bloquea; se registra y se advierte (RN-37, 38).
- **Anulación con registro**, solo en mes abierto (todos abiertos hasta el Hito 9) (RN-53, 59). Incluye el saldo inicial, que después puede volver a cargarse (RN-54).
- **Cálculos oficiales** de bolsa de consumo y acumulable (sección 11.1 y 11.2).
- **Tools:** `preview_income`, `add_income`, `add_expense`, `void_transaction`, `get_bolsa_status`, `list_transactions`, `get_summary`, `top_categories`, `create_category`, `list_categories`.
- **Prueba del invariante de integridad** (sección 11.4), creada en el Hito 4, se extiende a ingresos repartidos, gastos, anulaciones y USD, ejecutada contra datos generados.
- **Idempotencia** en las tools que escriben (clave de operación `operation_id`).

### Prompt para /speckit-specify
> El propietario quiere registrar desde Claude su salario y sus gastos, en colones o dólares. El salario que entra a fin de mes se reparte entre las bolsas según los porcentajes del mes siguiente. Quiere ver cuánto lleva gastado y cuánto le queda en cada bolsa, ver en qué gasta más, y anular un movimiento mal registrado dejando constancia. Un gasto que excede una bolsa se registra igual y avisa. Incluye pruebas automáticas que verifiquen los criterios de aceptación.

### Terminado cuando
- Desde Claude: registras un salario y se reparte Necesidades 50 %, Ahorro 30 % y Gustos 20 % en el mes siguiente.
- Registras un gasto en dólares y queda convertido a colones con el tipo de cambio indicado.
- Un gasto que deja una bolsa en negativo se guarda y la respuesta advierte.
- Anulas un gasto, y desaparece de los cálculos pero sigue en el historial.
- Repetir la misma llamada no duplica el gasto.
- Un movimiento en USD sin tipo de cambio se rechaza.
- La migración conserva los datos del Hito 4 (el saldo inicial queda en colones) y su downgrade está protegido.
- La prueba del invariante pasa.
- **Prueba de uso real:** usas la app una semana con tus gastos verdaderos y anotas fricciones antes de seguir.

---

## Hito 6: Extras y gastos fijos

**Objetivo:** ingresos que no son salario, y gastos que se repiten cada mes.

### Entregables
- **Tablas** (migración `0005_extras_recurring`, que conserva los datos del Hito 5): `recurring_expenses`, `recurring_expense_amounts` y `expenses.recurring_id`; en `incomes` se reutilizan `kind = 'extra'` y `allocation_status` (solo un extra puede quedar pendiente).
- **Ingreso extra** en estado `pendiente` hasta confirmar el reparto, en el mes de su fecha, con moneda y tipo de cambio como en el Hito 5 (RN-04 a 09).
- **Tool de contexto** (`get_allocation_context`) que entrega a Claude solo agregados del mes: presupuesto vs. gastado por bolsa, fijos pendientes (los de USD aparte, sin convertir) y porcentajes de repartos anteriores. Claude propone bolsas y porcentajes; tú apruebas la vista previa y se confirma con `confirm_allocation` (con la ficha de esa vista previa). Instrucciones del servidor MCP que explican el flujo.
- **Gastos fijos:** plantillas con monto (con historial: un cambio vale desde el mes siguiente), moneda, día del mes, bolsa, categoría opcional y mes de inicio; se desactivan, nunca se borran (RN-35, 36). Se pagan con `add_expense` y `recurring`; un solo pago vigente por mes. Un fijo en USD exige el tipo de cambio de cada pago (decisión #12d).
- **Tools:** `register_extra_income`, `get_allocation_context`, `confirm_allocation`, `manage_recurring`, `list_pending_recurring`; `add_expense` acepta `recurring`.
- **Alerta de "sin asignar":** los extras pendientes aparecen en `get_summary` y `list_transactions` (cantidad, total en colones y los de USD aparte).
- **Invariante** (sección 11.4) extendido: extras pendientes fuera, repartidos dentro, anulaciones que revierten y pagos de fijos.

Los gastos fijos se recuerdan **bajo demanda** (`list_pending_recurring`), sin proceso programado: lo decidió el propietario al pedir el Hito 6 (2026-11-10), como recomendaba este documento.

### Prompt para /speckit-specify
> El propietario quiere registrar ingresos extra y que, en cada uno, Claude le proponga cómo repartirlo entre las bolsas según la situación del mes, para él confirmar o ajustar antes de guardar. También quiere registrar sus gastos fijos mensuales y saber cuáles ya pagó y cuáles faltan. Incluye pruebas automáticas que verifiquen los criterios de aceptación.

### Terminado cuando
- Registras un extra: queda pendiente y visible como "sin asignar".
- Claude propone un reparto razonable con base en el estado de tus bolsas, y al confirmar, la suma da exactamente el monto.
- Claude no confirma un reparto sin mostrarte la vista previa y esperar tu aprobación explícita; un reparto que no suma 100 o un extra ya repartido se rechazan.
- Registras un gasto fijo y `list_pending_recurring` muestra cuáles faltan en el mes.
- Pagas un fijo (en USD, con el tipo de cambio de ese pago) y deja de figurar como pendiente; un segundo pago del mismo mes se rechaza.
- La migración conserva los datos del Hito 5 y su downgrade está protegido.
- La prueba del invariante pasa.

---

## Hito 7: Bolsas flexibles y metas

**Objetivo:** crear bolsas nuevas en cualquier momento y asociar metas de ahorro a bolsas acumulables.

La decisión #11 (una sola meta activa por bolsa) quedó resuelta el 2026-11-11 (constitución 1.0.3).

### Entregables
- **Tablas** (migración `0006_pockets_goals`, que conserva los datos del Hito 6): `savings_goals` con el índice único parcial de una meta activa por bolsa (RN-22); `pockets.archived_at`.
- **Crear bolsa** con reajuste atómico de porcentajes, y estrategias proporcional, desde una bolsa o manual (RN-13, 14). Escribe el conjunto completo del mes objetivo; aplica desde el mes siguiente por defecto o desde el actual (RN-15), nunca un mes pasado. Ningún reparto ya guardado se recalcula.
- **Archivar bolsa** exigiendo saldo cero (RN-16 a 18) y redistribuyendo su porcentaje en el mes actual y en los futuros con porcentajes propios (RN-17); sus metas se archivan con ella. Una bolsa archivada no recibe gastos ni repartos. Para vaciarla se usará el Hito 8 (ver sus pruebas pendientes).
- **Metas:** objetivo asociado a una bolsa acumulable, sin dinero propio; avance calculado del saldo con la misma función de 11.2; estados y fecha de logro evaluados en la transacción de cada operación que sube un saldo; números del RN-28 para que Claude proyecte (RN-19 a 25, 28, 29; RN-26 y 27 derogadas, RN-30 resuelta).
- **Contexto del extra** (`get_allocation_context`) con las metas activas y su avance (RN-05).
- **Tools:** `preview_rebalance`, `create_bolsa`, `archive_bolsa`, `create_goal`, `get_goal_progress`, `update_goal`, con vista previa y ficha (`preview_token`) en crear y archivar.
- **Invariante** (sección 11.4): crear bolsas, reajustar porcentajes, archivar y crear o cambiar metas no altera ningún saldo.

### Prompt para /speckit-specify
> El propietario quiere crear bolsas nuevas (por ejemplo Emergencia o Viaje), y que al crearlas se le muestre cómo cambiarían los porcentajes para aprobarlos. Quiere definir metas de ahorro, como un viaje de ₡500.000 sin fecha obligatoria, ligadas a una bolsa de ahorro, y ver su avance según el saldo de esa bolsa. Incluye pruebas automáticas que verifiquen los criterios de aceptación.

### Terminado cuando
- Creas la bolsa Emergencia: la vista previa muestra el reajuste, al confirmar los porcentajes suman 100 y aplican desde el mes siguiente.
- Creas la meta "Viaje ₡500.000" en una bolsa acumulable y `get_goal_progress` muestra avance y faltante.
- La app rechaza crear una meta en una bolsa de consumo, y una segunda meta activa en la misma bolsa.
- La meta pasa a `lograda` al alcanzar el objetivo y se mantiene así aunque luego gastes de la bolsa.
- Archivar una bolsa con saldo distinto de cero se rechaza; una bolsa vacía se archiva, ningún mes de ahora en adelante le reparte y rechaza gastos.
- Claude no confirma una bolsa nueva ni un archivado sin mostrarte la vista previa y esperar tu aprobación explícita.
- La migración conserva los datos del Hito 6 y su downgrade está protegido.
- La prueba del invariante pasa, y también la de que el avance de una meta es el saldo de su bolsa.

---

## Hito 8: Transferencias entre bolsas

**Objetivo:** mover dinero entre bolsas con registro permanente, por ejemplo para cubrir un sobregasto.

### Entregables
- **Tabla `transfers`** inmutable, con motivo (RN-39 a 45).
- **Presupuesto ajustado** frente al original (sección 9.1).
- **Vista previa con aviso del efecto sobre metas** (RN-58).
- **Corrección de errores** mediante transferencia inversa (RN-43).
- **Archivado de bolsas** completado: mover el saldo a otra bolsa permite archivarla (RN-18).
- **Pruebas pendientes del Hito 7** que se completan aquí: (1) una bolsa con saldo se vacía con una transferencia y luego `archive_bolsa` la archiva; (2) una bolsa de consumo con disponible del mes se vacía igual y se archiva; (3) archivar una bolsa acumulable con meta activa tras vaciarla archiva la meta; (4) la vista previa de la transferencia avisa el efecto sobre la meta (RN-58).
- **Tools:** `preview_transfer`, `transfer_between_bolsas`.

### Prompt para /speckit-specify
> El propietario quiere mover dinero de una bolsa a otra, por ejemplo para cubrir un gasto que excedió Gustos, viendo antes cómo quedarían ambas bolsas y qué efecto tendría sobre su meta de ahorro. Cada movimiento debe quedar registrado y no poder editarse ni borrarse. Incluye pruebas automáticas que verifiquen los criterios de aceptación.

### Terminado cuando
- Gustos queda en negativo, y con una transferencia desde Necesidades vuelve a cero, con el movimiento en el historial.
- No se puede mover más de lo disponible en la bolsa de origen.
- Mover dinero fuera de una bolsa con meta activa muestra el efecto en el avance.
- La prueba del invariante sigue pasando con transferencias.
- Puedes archivar una bolsa tras vaciarla con una transferencia.

---

## Hito 9: Cierre de mes

**Objetivo:** el ritual de fin de mes: resolver déficits, decidir el destino de los sobrantes y cerrar.

### Entregables
- **Tablas:** `month_closures`, `closure_adjustments`.
- **Vista previa del cierre** (`preview_month_close`) con déficits, sobrantes de consumo, saldos acumulables que podrían cubrir y propuesta de Claude.
- **Cierre atómico** (`close_month`): cubre déficits primero (con sobrantes y, con confirmación, con saldo acumulable), luego envía sobrantes a las bolsas elegidas o los registra como no destinados (RN-46 a 52).
- **Bloqueo de meses cerrados:** sin movimientos, transferencias ni anulaciones nuevas (RN-44, 48, 53).
- **Alerta de cierre pendiente** (RN-49).
- **Ritual de fin de mes** documentado en un solo flujo (RN-51).

### Prompt para /speckit-specify
> A fin de mes, el propietario quiere ver los déficits y sobrantes de sus bolsas de consumo, recibir una propuesta de cómo cubrir déficits y a dónde enviar los sobrantes, confirmarla o cambiarla, y cerrar el mes de forma que lo cerrado no pueda modificarse. Las bolsas de consumo empiezan el mes siguiente en cero. Incluye pruebas automáticas que verifiquen los criterios de aceptación.

### Terminado cuando
- Un mes con un déficit y un sobrante se cierra, y el sobrante cubre el déficit.
- Un sobrante enviado a una bolsa acumulable aparece en su saldo.
- Un sobrante sin destino queda como "no destinado" y el invariante sigue cuadrando.
- Si algo falla a mitad del cierre, no queda nada a medias.
- Un mes cerrado rechaza gastos y anulaciones.
- Las bolsas de consumo del mes siguiente empiezan en cero.

---

## Hito 10: Dashboard y estadísticas

**Objetivo:** ver tus finanzas en gráficos y tablas, en privado.

### Entregables
- **Capa de lectura (API)** que reutiliza `services/`, sin duplicar reglas. Framework por decidir en este hito.
- **Dashboard** en React + Vite + TypeScript + Tailwind, con gráficos.
- **Componentes** de la sección 13.2 del plan técnico (`docs/plan-tecnico.md`): tarjetas, progreso por bolsa (original vs. ajustado), dona por categoría, evolución mensual, tabla con filtros, fijos pagados y pendientes, tarjeta por meta, alertas.
- **Acceso privado:** el dashboard no se expone por el túnel público; se accede por VPN privada (por ejemplo Tailscale) o red local.
- **Autenticación propia del dashboard.**

### Prompt para /speckit-specify
> El propietario quiere consultar en una página web privada cuánto ingresó, cuánto gastó y cuánto le queda por bolsa, en qué categorías gasta más, cómo evolucionan sus meses y cómo van sus metas de ahorro. Los datos deben coincidir exactamente con los que le reporta Claude. Incluye pruebas automáticas que verifiquen los criterios de aceptación.

### Terminado cuando
- Los totales del dashboard coinciden con `get_summary` para el mismo mes.
- El dashboard no es accesible desde internet público.
- Los movimientos anulados se distinguen y no suman.
- Los totales se muestran en colones.

---

## Hito 11: Operación y endurecimiento

**Objetivo:** que el sistema sea confiable a largo plazo, porque son tus finanzas.

### Entregables
- **Respaldos automáticos** de Postgres (`pg_dump`), con retención definida y copia fuera del homelab.
- **Restauración probada:** restaurar un respaldo en una base limpia y verificar el invariante.
- **Monitoreo básico:** healthchecks, alerta si el servicio cae, revisión de espacio en disco.
- **Actualizaciones:** procedimiento para actualizar imágenes de Docker y dependencias.
- **Revisión de seguridad:** secretos rotados, puertos expuestos, permisos, registros de acceso.
- **Revisión de uso de recursos** del homelab (memoria y disco) con todo corriendo.
- **Documentación final:** README completo y guía de recuperación ante desastres.

### Prompt para /speckit-specify
> El propietario quiere tener la seguridad de que sus datos financieros no se pierdan y de que el sistema se pueda recuperar. Necesita respaldos automáticos, una restauración comprobada, avisos si el servicio falla y un procedimiento claro para actualizar y recuperar el sistema. Incluye pruebas automáticas que verifiquen los criterios de aceptación.

### Terminado cuando
- Se hizo una restauración real desde un respaldo y los saldos y el invariante coinciden.
- Si apagas el servicio, recibes un aviso.
- Existe una guía escrita para recuperar el sistema desde cero.

---

## 4. Registro de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| 0.1 | 2026-11-09 | Primera versión: 12 hitos (0 a 11), con acceso remoto y autenticación antes que cualquier dato real. |
| 0.2 | 2026-11-09 | Porcentajes iniciales con nombres explícitos (Necesidades 50 %, Ahorro 30 %, Gustos 20 %) en los Hitos 4 y 5. Verificación de memoria con `docker stats` en el Hito 1. Referencias a `CONSTITUCION.md` corregidas a `docs/origen/CONSTITUCION-origen.md` (archivado). La sección 13 se cita en el plan técnico; la sección 14 queda en la constitución. |
| 0.3 | 2026-11-09 | Las reglas sobre datos reales, capa de negocio, invariante y pruebas por hito pasan a la gobernanza de la constitución; la sección 1 conserva dos principios y enlaza a la gobernanza. Cada "Prompt para /speckit-specify" (Hitos 1 a 11) pide pruebas automáticas de forma explícita. |
| 0.4 | 2026-11-09 | El transporte Streamable HTTP pasa del Hito 2 al Hito 1 (clarificación de la spec `001-cimientos`); en el Hito 2 se expone por el túnel. |
| 0.5 | 2026-11-09 | Se quita el SDK de MCP de las decisiones pendientes (decidido: `mcp==2.3.0` con `MCPServer`). El "Terminado cuando" del Hito 1 precisa que en GitHub Actions corren ruff y las pruebas unitarias, y las de integración en el equipo de desarrollo. |
| 0.6 | 2026-11-09 | Se quita de la sección 3 la decisión del servidor de autorización de OAuth (decidido en el Hito 3: propio y mínimo, para un único usuario; registrado en `docs/plan-tecnico.md`). |
| 0.7 | 2026-11-10 | Hito 4: se agrega `preview_initial_balance` a sus tools (principio 3.2 de la constitución; registrado en `docs/plan-tecnico.md` v0.6). La prueba del invariante de integridad empieza en el Hito 4, el primero que registra dinero (regla no negociable 3 de la constitución, que prevalece); el Hito 5 la extiende. Los datos iniciales son solo las bolsas; el 50/30/20 lo guarda el propietario (decisión del 2026-11-10). |
| 0.8 | 2026-11-10 | Se quita de la sección 3 la decisión #12 (resuelta; constitución 1.0.1). Hito 5: tablas con nombres en inglés (`incomes`, `expenses`, `idempotency_keys`) y migración que conserva los datos del Hito 4; tools `preview_income` (principio 3.2), `create_category` y `list_categories`; anulación del saldo inicial; RN-59 pasa del Hito 8 al Hito 5 en la vista general (sus entregables ya la citaban) y se agregan RN-02, 03 y 08 por el reparto del salario; dos criterios más en "Terminado cuando" (USD sin tipo de cambio; migración y downgrade). |
| 0.9 | 2026-11-11 | Hito 6: entregables con la migración `0005_extras_recurring` (que conserva los datos del Hito 5), contexto con solo agregados, ficha de vista previa e instrucciones del servidor, gastos fijos con historial de monto y pago con `add_expense`, "sin asignar" en resumen y listado, invariante extendido. Se quita la cuestión de `/speckit-clarify` (decidida por el propietario: gastos fijos bajo demanda). Cuatro criterios más en "Terminado cuando" (aprobación explícita, pago de fijo en USD, migración y downgrade, invariante). |
| 0.10 | 2026-11-11 | Se quita de la sección 3 la decisión #11 (resuelta; constitución 1.0.3). Hito 7: entregables con la migración `0006_pockets_goals` (conserva los datos del Hito 6), reajuste que escribe el conjunto completo del mes, archivado que redistribuye el mes actual y los futuros, metas evaluadas en cada operación que sube un saldo, metas en el contexto del extra; reglas de la vista general y del entregable de metas ajustadas (RN-26 y 27 derogadas, RN-30 resuelta); cuatro criterios más en "Terminado cuando". Hito 8: pruebas pendientes del archivado de bolsas con saldo. |
