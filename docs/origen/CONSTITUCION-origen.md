> **ARCHIVADO: material de origen, no es fuente de verdad. La fuente es `.specify/memory/constitution.md`.**

# Constitución del proyecto: App de finanzas personales con Claude

**Versión:** 0.3 (requerimientos con decisiones resueltas; stack y privacidad definidos)
**Fecha:** 2026-11-09
**Propietario:** Oscar Zúñiga ("TosTar")
Material de origen del que se derivó la constitución. Ya no se edita: los cambios se hacen en `.specify/memory/constitution.md`.

---

## 0. Cómo leer este documento

Cada decisión lleva una etiqueta de estado:

| Etiqueta | Significado |
|---|---|
| **[DECIDIDO]** | Lo dijo explícitamente el propietario. Es regla firme. |
| **[PROPUESTO]** | Se recomendó en el análisis y no fue rechazado, pero el propietario no lo confirmó. Se asume mientras no se diga lo contrario. |
| **[ABIERTO]** | Falta decidir. Está listado en la sección 14. |
| **[APLAZADO]** | El propietario decidió dejarlo para más adelante. No bloquea el diseño de negocio. |

Las reglas de negocio llevan identificador (`RN-xx`) para poder referenciarlas en el código, tests e issues. **Los números no se reutilizan:** una regla que deja de valer se marca como derogada y conserva su número.

---

## 1. Visión

Una aplicación **personal y manual** para llevar el control del dinero: cuánto entra, a dónde se va y cuánto se ahorra. El ingreso neto de cada mes se reparte en **bolsas** con porcentajes editables (idea base: 50 % necesidades, 30 % ahorro, 20 % gustos). Todo el registro y las consultas se hacen conversando con Claude, y un dashboard muestra las estadísticas.

**Objetivos:**
1. Saber en qué se gasta más.
2. Saber qué gastos son necesarios y cuáles son fijos mensuales.
3. Saber cuánto ingresa por mes.
4. Repartir el ingreso por porcentajes modificables.
5. Ver cuánto del presupuesto de cada bolsa se ha gastado y cuánto se ha ingresado al ahorro.
6. Servir como **proyecto de aprendizaje** (MCP, diseño de datos, IA integrada).

---

## 2. Alcance

### 2.1 Dentro del alcance **[DECIDIDO]**
- Registro manual de ingresos y gastos, en **colones (CRC) y dólares (USD)**.
- Carga de un saldo inicial al comenzar.
- Bolsas de dinero configurables, con porcentajes por mes.
- Gastos fijos mensuales.
- Metas de ahorro asociadas a bolsas acumulables.
- Movimientos de dinero entre bolsas.
- Anulación con registro de ingresos y gastos mal registrados.
- Cierre de mes.
- Estadísticas y dashboard interactivo.
- Integración con Claude mediante un servidor MCP.

### 2.2 Fuera del alcance (por ahora) **[DECIDIDO]**
- **Conexión con cuentas bancarias o tarjetas.** Todo es manual. No hay tablas de cuentas ni conciliación.
- Producción, multiusuario o venta. Es un proyecto personal.
- Asesoría financiera. Las recomendaciones de Claude son heurísticas de presupuesto, no asesoría profesional.
- Monedas distintas de colones y dólares.

### 2.3 Consecuencia importante
Como no hay conexión bancaria, la app mide **flujos registrados**, no el saldo real de las cuentas. Si se olvida registrar un gasto, la app y el dinero real se separan. Un "ajuste de saldo" manual queda como idea futura, no como requerimiento actual.

---

## 3. Principios de diseño

1. **La app calcula y valida; Claude interpreta y recomienda; el usuario decide.** La app nunca opina. Claude nunca guarda una decisión financiera sin confirmación.
2. **Previsualizar antes de confirmar.** Toda operación que reparte o mueve dinero tiene una tool de vista previa (`preview_*`) que no guarda nada, y otra que ejecuta.
3. **Calcular, no guardar números sueltos.** Saldos, avances de metas y sobrantes se derivan del historial de movimientos. No existe un campo "saldo" que se edite a mano.
4. **Libro mayor inmutable.** Los movimientos no se editan ni se borran. Un error se corrige con un movimiento contrario, una anulación registrada o un ajuste.
5. **El dinero es entero.** Los cálculos usan colones enteros. Los dólares se guardan en centavos enteros. Nunca `float`.
6. **Operaciones atómicas.** Si una operación implica varios cambios (crear bolsa + reajustar porcentajes, cerrar mes + registrar transferencias), se guarda todo o nada.
7. **Registrar la realidad antes que imponer reglas.** Un gasto que deja una bolsa en negativo **no se bloquea**: se registra, se avisa y se propone cómo cubrirlo.
8. **Archivar, no borrar.** Lo que tiene historial (bolsas, metas, categorías) se marca inactivo.
9. **Historial por mes.** Los porcentajes se guardan por mes para que un cambio actual no altere estadísticas pasadas.
10. Los datos se almacenan en el servidor del propietario. Al usar Claude mediante MCP, la información consultada y registrada transita por Cloudflare y Anthropic, y el propietario acepta ese tránsito. Las tools devuelven solo la información necesaria para cada consulta (minimización).

---

## 4. Glosario

| Término | Definición |
|---|---|
| **Bolsa** | Contenedor de dinero con un propósito (Necesidades, Gustos, Ahorro, Emergencia…). Se pueden crear nuevas en cualquier momento. |
| **Comportamiento** | Cómo se comporta una bolsa: `consumo` o `acumulable` (ver sección 6). |
| **Mes presupuestario** | Mes al que pertenece un presupuesto, formato `YYYY-MM`. El salario que entra a fin de mes financia el mes siguiente. |
| **Ingreso base** | El salario mensual. Se reparte con los porcentajes del mes. |
| **Ingreso extra** | Cualquier otro ingreso. No tiene regla fija: cada vez se decide el reparto. |
| **Saldo inicial** | Dinero con el que se arranca la app, cargado una sola vez y repartido por montos entre las bolsas. |
| **Presupuesto original** | Lo que sale de aplicar los porcentajes al ingreso. |
| **Presupuesto ajustado** | Original más transferencias recibidas menos enviadas. |
| **Meta** | Objetivo de ahorro (con monto) asociado a una bolsa acumulable. **No tiene dinero propio:** su dinero es el de la bolsa. |
| **Transferencia** | Movimiento registrado de dinero entre bolsas. |
| **Anulación** | Marca registrada (con fecha y motivo) que deja sin efecto un ingreso o gasto mal registrado, sin borrarlo. |
| **Moneda base** | Colones (CRC). Todos los cálculos se hacen en colones. |
| **Tipo de cambio** | Colones por dólar, usado al convertir un movimiento en USD. Se guarda en cada movimiento. |
| **Cierre de mes** | Proceso donde se resuelven déficits y se decide el destino de los sobrantes. |
| **MCP** | Model Context Protocol: estándar para darle herramientas (tools) a Claude. |

---

## 5. Ingresos, monedas y saldo inicial

### 5.1 Ingreso base (salario) **[DECIDIDO]**
- El salario **ingresa a fin de cada mes** y se toma como el ingreso neto del **mes siguiente**.
- Ejemplo: el salario que entra el 30 de noviembre pertenece al mes presupuestario 2026-12 y se reparte con los porcentajes de diciembre.
- Los gastos pertenecen al mes calendario en que ocurren (el mes se deriva de la fecha del gasto).

### 5.2 Porcentajes por mes **[DECIDIDO]**
- Los porcentajes son **modificables**.
- **RN-01:** los porcentajes de un mes deben **sumar exactamente 100**. La app rechaza cualquier configuración que no cumpla.
- **RN-02:** los porcentajes se guardan **por mes** (los porcentajes de cada mes). Cambiar los porcentajes no altera meses anteriores.
- **RN-03 [PROPUESTO]:** si un mes no tiene porcentajes definidos, se copian del mes anterior.
- Configuración inicial sugerida: Necesidades 50 %, Ahorro 30 %, Gustos 20 %.

### 5.3 Ingreso extra **[DECIDIDO]**
- **RN-04:** el ingreso extra **no tiene regla fija de porcentajes**. Cada vez que entra, se pregunta cómo repartirlo.
- **RN-05:** **Claude recomienda las bolsas y los porcentajes**, basándose en el contexto del mes (qué bolsa va corta, gastos fijos pendientes, metas, repartos anteriores). El usuario confirma o ajusta.
- **RN-06:** un extra recién registrado queda en estado `pendiente` y se muestra como "sin asignar" en el dashboard hasta que se confirme el reparto. Nunca se asigna a ciegas.
- **RN-07:** el reparto del extra puede incluir **bolsas personalizadas** (por ejemplo, Emergencia).
- **RN-08:** el reparto en montos se calcula con enteros: las primeras bolsas reciben el monto redondeado y **la última absorbe el residuo** (por resta), para que la suma sea exacta.
- **RN-09 [DECIDIDO]:** el extra pertenece al **mes en que entra** (el mes presupuestario = mes de su fecha).

Flujo:

```
Usuario: "Me entraron 40.000 extra"
  → register_extra_income        (queda pendiente)
  → get_allocation_context       (datos del mes)
  → Claude propone bolsas y %    (con explicación breve)
  → Usuario confirma o ajusta
  → confirm_allocation           (valida suma = 100, guarda)
```

### 5.4 Monedas: colones y dólares
- **RN-55 [DECIDIDO]:** la app soporta **colones (CRC) y dólares (USD)** en ingresos, gastos y gastos fijos.
- **RN-56 [PROPUESTO]:** la **moneda base es el colón**. Todos los cálculos (presupuestos, saldos, porcentajes, estadísticas) se hacen en colones enteros. Un movimiento en dólares se convierte a colones al registrarlo.
- **RN-57 [PROPUESTO]:** cada movimiento en USD guarda **su moneda original, su monto original (en centavos) y el tipo de cambio usado**. El equivalente en colones se calcula una vez y **no se recalcula** después, para que el historial no cambie cuando cambia el dólar.
- Conversión (tipo de cambio guardado como entero: colones por dólar × 100):

```
monto_crc = redondeo( monto_usd_centavos × tipo_cambio / 10 000 )     (redondeo half-up)

Ejemplo: USD 10,00 a ₡512,34  →  1 000 × 51 234 / 10 000 = 5 123,4  →  ₡5 123
```

- En el dashboard, los totales se muestran en colones. Mostrar un equivalente en dólares es opcional.
- Los detalles de esta política (fuente del tipo de cambio, ahorros que se quieran conservar en dólares) están en la decisión abierta #12.

### 5.5 Saldo inicial **[DECIDIDO]**
- **RN-54:** la app **arranca con una carga de saldo inicial**: el dinero que ya existe al comenzar, repartido por **montos explícitos** entre las bolsas (no por porcentajes). Claude puede ayudar a proponer el reparto.
- El saldo inicial es un registro especial (de tipo saldo inicial). **No cuenta como ingreso del mes** en las estadísticas de ingresos, pero sí forma parte de los saldos de las bolsas.
- Se carga una sola vez, al inicio, con la tool `load_initial_balance`.

---

## 6. Bolsas

### 6.1 Definición **[DECIDIDO]**
- Las bolsas **no son fijas**: se pueden agregar en cualquier momento.
- Una bolsa puede ser un **tipo propio** (por ejemplo, Emergencia es su propia bolsa, no un subtipo de Ahorro).
- **RN-10:** cada bolsa tiene un `comportamiento` que define cómo funciona. No existe una lista fija de "tipos" en el código.
- El grupo, opcional, solo sirve para estadísticas agrupadas (por ejemplo, agrupar Ahorro, Emergencia y Viaje). Puede quedar vacío.

### 6.2 Comportamientos **[DECIDIDO]**

| Comportamiento | Se usa para | Al empezar el mes | Al cerrar el mes | Metas |
|---|---|---|---|---|
| `consumo` | Registrar **gastos** (Necesidades, Gustos) | Empieza en **cero** | El sobrante se envía al destino que el usuario decida | No |
| `acumulable` | **Guardar** dinero (Ahorro, Emergencia, Viaje) | Conserva su saldo | No se modifica | **Sí** |

- **RN-11:** una bolsa `consumo` **no arrastra** su saldo al mes siguiente. Su sobrante se resuelve en el cierre de mes (sección 10).
- **RN-12:** una bolsa `acumulable` **siempre conserva su saldo**.
- Bolsas iniciales sugeridas: Necesidades (`consumo`), Gustos (`consumo`), Ahorro (`acumulable`).

### 6.3 Crear una bolsa **[DECIDIDO]**
- **RN-13:** al crear una bolsa **se reajustan los porcentajes de reparto** en la misma operación atómica. Debe quedar la suma en 100 %.
- Estrategias de reajuste que Claude puede ofrecer:

| Estrategia | Cómo funciona |
|---|---|
| Proporcional | Todas las bolsas existentes bajan en la misma proporción. |
| Desde una bolsa | Solo una bolsa cede el porcentaje. |
| Manual | El usuario indica el reparto completo. |

- **RN-14:** el reajuste proporcional usa enteros, y **la última bolsa absorbe el residuo**.
- **RN-15 [DECIDIDO]:** una bolsa nueva aplica desde el **mes siguiente** por defecto. Se puede pedir expresamente que aplique de inmediato, lo que obliga a recalcular el mes en curso.
- Flujo: `preview_rebalance` (sin guardar) → confirmación → `create_bolsa`.

### 6.4 Archivar una bolsa
- **RN-16:** una bolsa con movimientos **nunca se borra**: se archiva (queda inactiva).
- **RN-17:** al archivar, su porcentaje debe redistribuirse para que la suma siga en 100.
- **RN-18 [DECIDIDO]:** para archivar una bolsa con saldo, **se exige moverlo a otra bolsa** mediante una transferencia registrada (motivo `reasignacion`). Una bolsa solo puede archivarse cuando su saldo (o disponible, si es de consumo) es cero.
- Si la bolsa tiene una meta activa, la meta se archiva junto con la bolsa.

### 6.5 Destino de sobrante por defecto **[PROPUESTO]**
Cada bolsa `consumo` puede tener un destino de sobrante sugerido (por ejemplo, el sobrante de Gustos va a Viaje). Claude parte de ahí al proponer el cierre y el usuario solo confirma. El destino siempre es una bolsa acumulable.

---

## 7. Metas de ahorro **[DECIDIDO]**

**Principio central:** una meta **no tiene dinero propio**. Es un objetivo asociado a una bolsa acumulable, y su dinero **es el mismo dinero de la bolsa**. El dinero que se gasta de la bolsa se gasta de la bolsa, y el avance de la meta se calcula a partir del saldo de esa bolsa.

- **RN-19:** una meta tiene **nombre y monto objetivo** (en colones). Ejemplo: viaje de ₡500.000.
- **RN-20:** la **fecha objetivo es opcional**. No hay fecha obligatoria de cumplimiento.
- **RN-21:** una meta se asocia a **una bolsa acumulable**. La app rechaza asociarla a una bolsa de consumo (validación en la tool `create_goal`).
- **RN-22 [PROPUESTO]:** una bolsa tiene **como máximo una meta activa a la vez**. Si se quiere una segunda meta, se crea otra bolsa acumulable para ella. Razón: con dinero compartido, dos metas en la misma bolsa harían ambiguo el avance de cada una. (Pendiente de confirmar: decisión #11.)
- **RN-23:** el **avance de una meta se calcula** a partir del saldo de su bolsa. No existen aportes ni retiros propios de la meta.
- **RN-24:** estados de una meta: `activa`, `lograda`, `pausada`.
  - **[PROPUESTO]** Pasa automáticamente a `lograda` cuando el saldo de la bolsa alcanza el monto objetivo, y se registra la fecha del logro. **Permanece `lograda` aunque el saldo baje después** (gastar el dinero del viaje no "deshace" la meta).
- **RN-25:** el dinero llega a la bolsa por las vías normales (asignaciones por porcentaje, extras, transferencias, sobrantes de cierre, saldo inicial) y sale por gastos y transferencias. La meta no agrega ningún tipo de movimiento nuevo.
- **RN-26 [DEROGADA en v0.2]:** *(antes: solo se podía mover el saldo libre; el dinero de metas estaba protegido.)* Ya no existe "saldo libre" separado: todo el saldo de la bolsa es el mismo dinero de la meta.
- **RN-27 [DEROGADA en v0.2]:** *(antes: los aportes a una meta requerían saldo libre.)* Ya no hay aportes propios de la meta.
- **RN-28 [PROPUESTO]:** Claude puede proyectar una **fecha estimada** de cumplimiento usando el promedio mensual de la **variación neta del saldo** de la bolsa. Si ese promedio es cero o negativo, no hay estimación. (La app entrega los números; Claude hace la proyección.)
- **RN-29 [PROPUESTO]:** si el saldo supera el monto objetivo, el excedente **permanece en la bolsa**. Claude puede sugerir qué hacer con él (mover a otra bolsa, crear una meta nueva), siempre con confirmación.
- **RN-30 [RESUELTA]:** gastar el dinero de una meta es **un gasto normal contra su bolsa**. No hay una operación especial.

```
Bolsa "Viaje" (acumulable)            Meta: ₡500.000
 saldo ₡180.000   →   avance 36 %   →   faltan ₡320.000
 (gasto de ₡30.000 en la bolsa → saldo ₡150.000 → avance 30 %)
```

---

## 8. Gastos

- **RN-31:** un gasto tiene monto positivo, fecha, moneda, bolsa, categoría (opcional) y descripción.
- **RN-32:** el gasto pertenece al **mes calendario** de su fecha.
- **RN-33 [DECIDIDO]:** los gastos pueden registrarse contra **cualquier bolsa**, incluidas las acumulables. Gastar de una bolsa acumulable reduce su saldo (y, por tanto, el avance de su meta, si la tiene).
- **RN-34 [PROPUESTO]:** un gasto sin categoría clara queda como "pendiente de clasificar" y no se pierde.
- **Categorías:** lista editable, cada una asociada a una bolsa por defecto.

### 8.1 Gastos fijos mensuales **[DECIDIDO]**
- Se registran plantillas (alquiler, internet, suscripciones) con monto, moneda y día del mes.
- **RN-35:** la app recuerda o genera el gasto cada mes, y muestra cuáles ya se pagaron y cuáles faltan.
- **RN-36:** los fijos pendientes alimentan el contexto que Claude usa para recomendar repartos.

### 8.2 Sobregasto **[DECIDIDO]**
- **RN-37:** un gasto que deja una bolsa en negativo **no se bloquea**. Se registra, la tool devuelve una advertencia con las bolsas que tienen saldo disponible, y Claude propone de dónde cubrirlo.
- **RN-38:** si no se cubre en el momento, la bolsa queda en negativo y el dashboard la marca en rojo hasta el cierre.

### 8.3 Correcciones: anulación con registro **[DECIDIDO]**
- **RN-53:** un ingreso o gasto mal registrado **no se borra ni se edita**: se **anula con registro** (fecha de anulación y motivo). Corregir un dato es anular el movimiento y registrar uno nuevo.
  - Solo se puede anular mientras el **mes esté abierto**. En un mes cerrado no se permite (ver RN-48).
  - Todos los cálculos y estadísticas **ignoran los movimientos anulados**, pero estos siguen visibles en el historial.
- **RN-59 [PROPUESTO]:** si se anula un ingreso ya repartido, sus asignaciones a las bolsas se revierten. Eso puede dejar una bolsa en negativo, y se aplica entonces la advertencia de RN-37.

---

## 9. Transferencias entre bolsas **[DECIDIDO]**

Principio: **el dinero es uno solo**. Si una bolsa se pasó, ese dinero salió de otra, y debe quedar registrado.

- **RN-39:** se puede mover dinero entre bolsas **en cualquier momento**, no solo al cierre.
- **RN-40:** todo movimiento se guarda en el registro de transferencias con fecha, mes, origen, destino, monto (en colones), motivo y nota.
- **RN-41:** el monto debe ser positivo y el origen distinto del destino.
- **RN-42:** no se puede mover más de lo disponible en la bolsa de origen (su saldo, si es acumulable; su disponible del mes, si es de consumo).
- **RN-43:** las transferencias **nunca se editan ni se borran**. Un error se corrige con una transferencia en sentido contrario.
- **RN-44:** un mes cerrado no admite transferencias nuevas.
- **RN-45 [DEROGADA en v0.2]:** *(antes: una transferencia podía tener como destino una meta.)* Las metas no reciben dinero: se transfiere a su bolsa.
- **RN-58 [PROPUESTO]:** al mover dinero **fuera de una bolsa que tiene una meta activa**, la tool de vista previa advierte el efecto sobre el avance de la meta (por ejemplo, "baja de 36 % a 30 %").
- Motivos permitidos: `cubrir_sobregasto`, `reasignacion`, `cierre_de_mes`, `ajuste`.
- El motivo de cada transferencia permite analizar patrones (por ejemplo, cuántas veces se cubrió Gustos con Necesidades, lo que indica si los porcentajes están mal calibrados).

### 9.1 Presupuesto ajustado
```
presupuesto ajustado = asignado + transferencias recibidas − transferencias enviadas
disponible           = presupuesto ajustado − gastado
```
El dashboard muestra **ambos** presupuestos (original y ajustado) para ver cuánto se desvió el plan.

Flujo: `preview_transfer` (sin guardar) → confirmación → `transfer_between_bolsas`.

---

## 10. Cierre de mes **[DECIDIDO]**

Las bolsas de consumo empiezan cada mes en cero, así que el sobrante o déficit se resuelve en un cierre.

### 10.1 Orden del cierre
1. **Resolver déficits:** las bolsas en negativo se cubren con transferencias desde otras bolsas.
   - Primero se usan los **sobrantes de bolsas de consumo**.
   - Si no alcanzan, **puede usarse el saldo de una bolsa acumulable** (RN-52), siempre con confirmación explícita.
2. **Distribuir sobrantes:** lo que queda se envía a destinos que el usuario elige.

### 10.2 Destinos posibles de un sobrante
1. Una **bolsa acumulable** (suma a su saldo y, por tanto, al avance de su meta si la tiene).
2. **Sobrante no destinado:** se registra explícitamente y no se arrastra al mes siguiente.

### 10.3 Reglas
- **RN-46:** `close_month` es **atómico**: se registran todas las transferencias y se marca el mes como cerrado, o no pasa nada.
- **RN-47:** la suma de destinos de una bolsa no puede superar su sobrante.
- **RN-48:** un mes cerrado **no se edita**. Las correcciones se hacen con un ajuste explícito y registrado.
- **RN-49:** si el mes no se cierra, queda `abierto` y el dashboard muestra una alerta de **cierre pendiente**.
- **RN-50:** si un déficit no se puede cubrir, se registra como **sobregasto no cubierto** y el mes se cierra igual. Aparece en las estadísticas.
- **RN-51 [PROPUESTO]:** el cierre del mes que termina ocurre junto con el reparto del nuevo salario, en un único ritual de fin de mes: (1) cerrar el mes, (2) registrar el salario, (3) repartir el mes nuevo con los porcentajes.
- **RN-52 [DECIDIDO]:** un déficit **puede cubrirse con el saldo de una bolsa acumulable** cuando no hay sobrantes suficientes en bolsas de consumo. Requiere confirmación explícita, y la vista previa advierte el efecto sobre la meta de esa bolsa (RN-58).

### 10.4 Flujo
```
preview_month_close
  ├─ 1) Déficits
  ├─ 2) Sobrantes de consumo
  ├─ 3) Saldos acumulables disponibles para cubrir (con aviso de metas)
  └─ Propuesta de Claude (cubrir déficits, enviar sobrantes)
Usuario confirma o cambia
close_month
```

### 10.5 Alternativas descartadas
| Alternativa | Estado | Motivo |
|---|---|---|
| Arrastrar el sobrante de las bolsas de consumo al mes siguiente | **Descartada por el propietario** | Se prefiere reinicio en cero con destino explícito del sobrante. |
| Descontar el sobregasto del presupuesto del mes siguiente | No elegida | Se eligió cubrirlo moviendo dinero desde otras bolsas, con registro. |
| "Solo registrar" el sobregasto sin consecuencias | Solo como último recurso | Queda como "sobregasto no cubierto" (RN-50). |
| Metas con dinero propio (aportes y retiros separados de la bolsa) | **Descartada por el propietario** | La meta es un objetivo sobre el dinero de la bolsa, no un contenedor aparte (sección 7). |

---

## 11. Cálculos oficiales

Todos los valores de cálculo son colones enteros. `mes` tiene formato `YYYY-MM`. Los movimientos anulados se ignoran en todos los cálculos.

### 11.1 Bolsa de consumo (mes actual)
```
asignado             = Σ lo asignado a la bolsa por los ingresos del mes (mes presupuestario)
presupuesto ajustado = asignado + transferencias recibidas del mes − transferencias enviadas del mes
disponible           = presupuesto ajustado − gastos del mes
% usado              = gastos del mes / presupuesto ajustado   [PROPUESTO]
```
Se muestra también el % sobre el presupuesto original como dato de comportamiento.

### 11.2 Bolsa acumulable
```
saldo = Σ asignado (histórico, incluye saldo inicial)
      + Σ transferencias recibidas − Σ transferencias enviadas
      − Σ gastos
```

### 11.3 Meta
```
avance  = saldo de la bolsa asociada
falta   = max(0, monto_objetivo − avance)
% meta  = avance / monto_objetivo        (se muestra con tope de 100 %)
```

### 11.4 Invariante de integridad (debe tener test automático)
Los movimientos no crean ni destruyen dinero. En todo momento debe cumplirse:

```
Σ ingresos repartidos (incluye saldo inicial) − Σ gastos
   = Σ saldos de bolsas acumulables
   + Σ disponibles de bolsas de consumo de meses abiertos
   + Σ ajustes de cierre (sobrante no destinado suma; sobregasto no cubierto resta)
```

Los ingresos pendientes de repartir quedan fuera de la igualdad y se muestran aparte como "sin asignar".

---

## 12. Integración con Claude (MCP)

### 12.1 Catálogo de tools

| Tool | Función | Estado |
|---|---|---|
| `load_initial_balance` | Cargar el saldo inicial repartido por montos entre bolsas (una sola vez). | [DECIDIDO] |
| `add_expense` | Registrar gasto (con moneda y, si es USD, tipo de cambio). Si deja una bolsa en negativo, devuelve advertencia con las bolsas disponibles. | [DECIDIDO] |
| `add_income` | Registrar ingreso base (con moneda y tipo de cambio si aplica). | [DECIDIDO] |
| `register_extra_income` | Registrar ingreso extra en estado pendiente. | [DECIDIDO] |
| `get_allocation_context` | Entregar a Claude el panorama del mes: presupuesto vs gastado por bolsa, fijos pendientes, metas y repartos previos. | [DECIDIDO] |
| `confirm_allocation` | Confirmar el reparto de un extra (valida suma = 100). | [DECIDIDO] |
| `void_transaction` | Anular un ingreso o gasto con motivo, solo en mes abierto. Reemplaza a `update_transaction` y `delete_transaction`. | [DECIDIDO] |
| `get_bolsa_status` | Estado de una bolsa: asignado, transferencias, gastado, disponible y avance de su meta si la tiene. | [DECIDIDO] |
| `get_summary(mes)` | Resumen mensual. | [DECIDIDO] |
| `top_categories` | En qué se gasta más. | [DECIDIDO] |
| `list_transactions` | Listar movimientos con filtros. | [DECIDIDO] |
| `manage_recurring` | Crear, listar y modificar gastos fijos. | [DECIDIDO] |
| `set_allocation` / `update_allocation` | Cambiar porcentajes de un mes. | [DECIDIDO] |
| `preview_rebalance` | Calcular reajuste de porcentajes sin guardar. | [DECIDIDO] |
| `create_bolsa` | Crear bolsa y reajustar porcentajes (atómico). | [DECIDIDO] |
| `archive_bolsa` | Archivar bolsa (exige saldo cero, mediante transferencia previa) y redistribuir porcentaje. | [DECIDIDO] |
| `create_goal` | Crear meta asociada a una bolsa acumulable. | [DECIDIDO] |
| `get_goal_progress` | Avance, faltante, % y fecha estimada de una meta. | [DECIDIDO] |
| `update_goal` | Cambiar monto o fecha, pausar o reactivar. | [DECIDIDO] |
| `preview_transfer` | Simular movimiento entre bolsas (con aviso de efecto en metas). | [DECIDIDO] |
| `transfer_between_bolsas` | Registrar movimiento entre bolsas. | [DECIDIDO] |
| `preview_month_close` | Calcular déficits y sobrantes del mes, con propuesta. | [DECIDIDO] |
| `close_month` | Ejecutar el cierre (atómico). | [DECIDIDO] |

**Tools eliminadas en v0.2:** `contribute_to_goal`, `withdraw_from_goal`, `spend_from_goal`, `update_transaction`, `delete_transaction`. Las metas ya no reciben ni entregan dinero por separado (sección 7), y las correcciones se hacen por anulación (RN-53).

### 12.2 Reglas para las tools
1. Las tools devuelven datos exactos y validan reglas. No dan consejos.
2. Las tools que modifican dinero deben ser **idempotentes** o aceptar una clave de operación, para que una llamada repetida por Claude no duplique un movimiento. **[PROPUESTO]**
3. Las tools destructivas o de reparto piden confirmación del usuario antes de ejecutarse.
4. Las respuestas de error deben ser claras para que Claude pueda explicarlas.
5. Toda tool que reciba un monto en dólares exige el tipo de cambio (RN-57). Si falta, devuelve error en lugar de asumirlo.

---

## 13. Estadísticas y dashboard **[DECIDIDO en intención; detalle PROPUESTO]**

### 13.1 Preguntas que debe responder
- ¿En qué gasto más?
- ¿Cuánto de cada bolsa llevo gastado este mes (% del presupuesto)?
- ¿Cuánto he ingresado al ahorro, y de dónde vino (asignación mensual, extras, sobrantes de cierre)?
- ¿Cuánto ingreso tengo en el mes? (sin contar el saldo inicial)
- ¿Cuáles son mis gastos necesarios y cuáles son fijos?
- ¿Cómo voy en cada meta?

### 13.2 Componentes
- Tarjetas: ingreso del mes, gastado, disponible, ahorrado, ingresos **sin asignar**.
- Barras de progreso por bolsa (usado vs. presupuesto ajustado, con el original como referencia).
- Dona de gasto por categoría.
- Evolución mensual (línea o barras).
- Tabla de últimos movimientos con filtros (los anulados se distinguen visualmente).
- Lista de gastos fijos: pagados y pendientes.
- Tarjeta por meta: barra de progreso basada en el saldo de su bolsa, "faltan ₡X" y fecha estimada.
- Alertas: bolsa por encima de 80 % y 100 %, bolsa en negativo (rojo), cierre de mes pendiente, ingreso pendiente de repartir.
- Totales en colones, con equivalente en dólares opcional.

---

## 14. Decisiones

### 14.1 Resueltas el 2026-11-09

| # | Tema | Decisión |
|---|---|---|
| 1 | Moneda | Se soportan **colones y dólares** (RN-55). Detalles de implementación en #12. |
| 2 | Cubrir déficit | **Sí**: puede cubrirse con el saldo de una bolsa acumulable, con confirmación explícita (RN-52). |
| 3 | Bolsa archivada | Se **exige mover su saldo a otra bolsa** antes de archivarla (RN-18). |
| 4 | Gasto desde meta | La meta **no tiene dinero propio**: es el mismo dinero de la bolsa acumulable. El gasto sale de la bolsa y el avance de la meta se calcula a partir de su saldo (sección 7, RN-30). |
| 5 | Creación de bolsa | **Mes siguiente por defecto** (RN-15). |
| 6 | Mes de un extra | **El mes en que entra** (RN-09). |
| 7 | Correcciones | **Anulación con registro, solo en mes abierto** (RN-53). |
| 8 | Primer mes | **Empezar con carga de saldo inicial** (RN-54). |
| 9 | Despliegue del MCP | **Resuelta en lo principal:** MCP remoto por HTTPS con túnel de Cloudflare, para usarlo desde claude.ai y el celular. **Pendiente:** el servidor de autorización de OAuth se decide en el Hito 3 (ver `HITOS.md`). |
| 10 | Stack | **Python** para el MCP. |

### 14.2 Abiertas y aplazadas

| # | Tema | Estado | Pregunta | Recomendación actual |
|---|---|---|---|---|
| 11 | Metas por bolsa | **[ABIERTO]** | ¿Una bolsa puede tener varias metas activas o solo una? (RN-22) | Una sola meta activa por bolsa. Para otra meta, se crea otra bolsa acumulable. Evita el avance ambiguo al compartir el mismo dinero. |
| 12 | Monedas, detalles | **[ABIERTO]** | (a) ¿De dónde sale el tipo de cambio: lo escribes tú, o Claude lo busca? (b) ¿Quieres poder **conservar saldos en dólares** (por ejemplo, un ahorro en USD) o todo se convierte a colones al entrar? (c) ¿Las metas pueden tener objetivo en dólares? (d) Gastos fijos en USD: ¿qué tipo de cambio se usa al generarlos cada mes? | (a) Lo indicas tú al registrar (manual); Claude puede sugerir el último usado. (b) Todo se convierte a colones al entrar (RN-56), por simplicidad. (c) Metas solo en colones. (d) El último tipo de cambio usado, confirmado por ti. |

---

## 15. Requerimientos no funcionales

- **Privacidad:** Los datos se almacenan en el servidor del propietario. Al usar Claude mediante MCP, la información consultada y registrada transita por Cloudflare y Anthropic, y el propietario acepta ese tránsito. Las tools devuelven solo la información necesaria para cada consulta (minimización).
- **Autenticación:** el endpoint del MCP y el dashboard requieren token o login, aunque sea uso personal.
- **Respaldo:** copia automática y periódica de la base de datos.
- **Simplicidad de uso:** registrar un gasto debe tomar una sola frase a Claude.
- **Liviandad:** debe correr cómodamente en el hardware del homelab (laptop vieja, pocos recursos). Postgres corre en Docker; su consumo de memoria se mide con `docker stats` desde el Hito 1.
- **Calidad:** el invariante de la sección 11.4, las validaciones de sumas (porcentajes = 100) y la conversión de monedas deben estar cubiertos por tests automáticos.

---

## 16. Arquitectura propuesta **[PROPUESTO]**

```
Claude (chat) ──► Servidor MCP ──► PostgreSQL ◄── API ◄── Dashboard (React)
                  (tools)          (datos)
```

- **Base de datos:** PostgreSQL en un contenedor Docker, con volumen persistente.
- **MCP:** en Python, remoto por HTTPS mediante un túnel de Cloudflare (decisiones 9 y 10). El servidor de autorización de OAuth se decide en el Hito 3.
- **Dashboard:** React + Vite + TypeScript + Tailwind, con una librería de gráficos (por ejemplo Recharts).
- **Ejecución:** en el homelab del propietario.

---

## 17. Esquema de datos de referencia (v0.3, borrador, PostgreSQL)

Consolida y reemplaza los borradores anteriores. Es una propuesta técnica: puede ajustarse al implementar, siempre que respete las reglas de este documento.

Convenciones de tipos: identificadores y montos en `BIGINT`; banderas en `BOOLEAN`; fechas de calendario en `DATE`; instantes en `TIMESTAMPTZ`; el mes se guarda como texto de 7 caracteres `'YYYY-MM'` con un `CHECK` de formato.

```sql
-- Bolsas flexibles
CREATE TABLE bolsas (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre TEXT NOT NULL UNIQUE,
  comportamiento TEXT NOT NULL CHECK (comportamiento IN ('consumo','acumulable')),
  grupo TEXT,                                          -- opcional, solo estadísticas
  destino_sobrante_id BIGINT REFERENCES bolsas(id),    -- opcional; debe ser acumulable (se valida en código)
  activa BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE categorias (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre TEXT NOT NULL UNIQUE,
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  activa BOOLEAN NOT NULL DEFAULT TRUE
);

-- Porcentajes por mes (historial). La app valida que cada mes sume 100.
CREATE TABLE budget_month_allocations (
  mes CHAR(7) NOT NULL CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),  -- 'YYYY-MM'
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  porcentaje INTEGER NOT NULL CHECK (porcentaje BETWEEN 0 AND 100),
  PRIMARY KEY (mes, bolsa_id)
);

-- Ingresos (incluye el saldo inicial como registro especial)
CREATE TABLE ingresos (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fecha DATE NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('base','extra','saldo_inicial')),
  fuente TEXT,
  mes_presupuesto CHAR(7) NOT NULL                     -- salario de fin de mes -> mes siguiente
    CHECK (mes_presupuesto ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  moneda TEXT NOT NULL DEFAULT 'CRC' CHECK (moneda IN ('CRC','USD')),
  monto_original BIGINT NOT NULL CHECK (monto_original > 0),  -- CRC: colones; USD: centavos
  tipo_cambio BIGINT,                                  -- colones por USD x100; NULL si moneda = CRC
  monto BIGINT NOT NULL CHECK (monto > 0),             -- equivalente en colones (base de todos los cálculos)
  estado_reparto TEXT NOT NULL DEFAULT 'pendiente'
    CHECK (estado_reparto IN ('pendiente','repartido')),
  nota TEXT,
  anulado BOOLEAN NOT NULL DEFAULT FALSE,
  anulado_en TIMESTAMPTZ,
  motivo_anulacion TEXT,
  CHECK ((moneda = 'CRC' AND tipo_cambio IS NULL) OR (moneda = 'USD' AND tipo_cambio IS NOT NULL))
);

-- Reparto de cada ingreso por bolsa
CREATE TABLE income_allocations (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ingreso_id BIGINT NOT NULL REFERENCES ingresos(id),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  porcentaje INTEGER CHECK (porcentaje BETWEEN 0 AND 100),  -- NULL en el saldo inicial (monto explícito)
  monto BIGINT NOT NULL CHECK (monto >= 0)             -- colones; la última bolsa absorbe el residuo
);

-- Metas: objetivo asociado a una bolsa acumulable. No guardan dinero ni avance.
CREATE TABLE savings_goals (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),      -- debe ser acumulable (se valida en create_goal)
  nombre TEXT NOT NULL,
  monto_objetivo BIGINT NOT NULL CHECK (monto_objetivo > 0),  -- en colones
  fecha_objetivo DATE,                                 -- opcional
  estado TEXT NOT NULL DEFAULT 'activa'
    CHECK (estado IN ('activa','lograda','pausada')),
  fecha_logro DATE                                     -- se llena al pasar a 'lograda'
);
-- Una sola meta activa por bolsa (RN-22, pendiente de confirmar en decisión #11)
CREATE UNIQUE INDEX ux_meta_activa_por_bolsa
  ON savings_goals(bolsa_id) WHERE estado = 'activa';

-- Gastos
CREATE TABLE gastos (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fecha DATE NOT NULL,
  mes CHAR(7) NOT NULL                                 -- mes calendario de la fecha
    CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  categoria_id BIGINT REFERENCES categorias(id),
  descripcion TEXT,
  moneda TEXT NOT NULL DEFAULT 'CRC' CHECK (moneda IN ('CRC','USD')),
  monto_original BIGINT NOT NULL CHECK (monto_original > 0),
  tipo_cambio BIGINT,
  monto BIGINT NOT NULL CHECK (monto > 0),             -- equivalente en colones
  anulado BOOLEAN NOT NULL DEFAULT FALSE,
  anulado_en TIMESTAMPTZ,
  motivo_anulacion TEXT,
  CHECK ((moneda = 'CRC' AND tipo_cambio IS NULL) OR (moneda = 'USD' AND tipo_cambio IS NOT NULL))
);

-- Gastos fijos mensuales (plantillas)
CREATE TABLE gastos_recurrentes (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre TEXT NOT NULL,
  moneda TEXT NOT NULL DEFAULT 'CRC' CHECK (moneda IN ('CRC','USD')),
  monto_original BIGINT NOT NULL CHECK (monto_original > 0),
  dia_del_mes INTEGER NOT NULL CHECK (dia_del_mes BETWEEN 1 AND 31),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  categoria_id BIGINT REFERENCES categorias(id),
  activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- Libro mayor de transferencias entre bolsas (inmutable; siempre en colones)
CREATE TABLE transfers (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fecha DATE NOT NULL,
  mes CHAR(7) NOT NULL                                 -- mes presupuestario
    CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  from_bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  to_bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  monto BIGINT NOT NULL CHECK (monto > 0),
  motivo TEXT NOT NULL CHECK (motivo IN
    ('cubrir_sobregasto','reasignacion','cierre_de_mes','ajuste')),
  nota TEXT,
  CHECK (from_bolsa_id <> to_bolsa_id)
);

-- Estado de cada mes
CREATE TABLE month_closures (
  mes CHAR(7) PRIMARY KEY CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  estado TEXT NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto','cerrado')),
  cerrado_en TIMESTAMPTZ
);

-- Sobrantes no destinados y sobregastos no cubiertos al cerrar
CREATE TABLE closure_adjustments (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  mes CHAR(7) NOT NULL REFERENCES month_closures(mes),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('sobrante_no_destinado','sobregasto_no_cubierto')),
  monto BIGINT NOT NULL                                -- con signo: sobrante +, sobregasto -
);
```

**Cambios en v0.3:** traducción técnica a PostgreSQL (sin `PRAGMA`; `BOOLEAN`, `DATE`/`TIMESTAMPTZ`, `BIGINT`; mes como `CHAR(7)` con `CHECK` de formato). No cambia ninguna regla.

**Cambios respecto a v0.1:** se eliminan `goal_movements` y los campos `goal_id` de `gastos` y `transfers` (la meta ya no tiene dinero propio); se agregan campos de moneda, anulación y saldo inicial; se agrega `fecha_logro` a las metas.

**Validaciones que viven en el código (no en el esquema):**
- Cada mes suma 100 % en `budget_month_allocations` (RN-01).
- Las metas solo se asocian a bolsas `acumulable` (RN-21).
- No se transfiere más del saldo o disponible de la bolsa de origen (RN-42).
- Un mes cerrado no admite movimientos nuevos ni anulaciones (RN-44, RN-48, RN-53).
- Una bolsa solo se archiva con saldo cero (RN-18).
- El saldo inicial se carga una sola vez (RN-54).
- La conversión USD → CRC usa el tipo de cambio guardado y redondeo half-up (RN-57).
- Las operaciones compuestas (crear bolsa, cerrar mes, anular un ingreso ya repartido) se ejecutan en una sola transacción.

---

## 18. Plan por fases **[ELIMINADA en v0.3]**

Esta sección se eliminó. La única hoja de ruta es `HITOS.md`. El número se conserva para no alterar la numeración de las secciones.

---

## 19. Registro de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| 0.1 | 2026-11-09 | Primera versión: consolidación de todas las decisiones tomadas durante el análisis de requerimientos. |
| 0.2 | 2026-11-09 | Se resuelven las decisiones 1 a 8. **Metas rediseñadas:** ya no tienen dinero propio; su avance se calcula del saldo de la bolsa acumulable (se derogan RN-26, RN-27 y RN-45; se eliminan `goal_movements`, `contribute_to_goal`, `withdraw_from_goal` y `spend_from_goal`). Se agregan soporte de colones y dólares (RN-55 a RN-57), saldo inicial (RN-54), anulación con registro (RN-53), cobertura de déficit con saldo acumulable (RN-52), archivado exigiendo mover el saldo (RN-18). Se agregan decisiones abiertas 11 y 12. Las decisiones 9 y 10 quedan aplazadas. |
| 0.3 | 2026-11-09 | Se resuelven la decisión 10 (Python) y la 9 en lo principal (MCP remoto por HTTPS con túnel de Cloudflare; el servidor de autorización de OAuth queda para el Hito 3). Base de datos: PostgreSQL; las secciones 15, 16 y 17 se traducen solo en lo técnico. El principio 3.10 y el requisito de privacidad de la sección 15 se reemplazan por la aceptación explícita del tránsito por Cloudflare y Anthropic, con minimización. Se elimina la sección 18 (la hoja de ruta es `HITOS.md`). En las secciones 0 a 11 se quitan los valores literales de columnas (RN-16 "queda inactiva", saldo inicial, ejemplo de mes presupuestario) sin cambiar el significado de ninguna regla RN-xx. El archivo pasa a `docs/origen/CONSTITUCION-origen.md` como material de origen archivado; la fuente de verdad es `.specify/memory/constitution.md`. |
