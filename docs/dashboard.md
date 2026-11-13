# Especificación de diseño — Puro Pockets

**Fuente de verdad:** implementación actual en `app/globals.css`, `app/layout.tsx`, `components/puro-dashboard.tsx`, `data/mock.ts`, `lib/copy.ts` y `lib/format.ts`. Esta especificación describe únicamente esos archivos; no implica una API o comportamiento no implementado.

## 1. Propósito y alcance

Panel personal de finanzas para consultar un mes, sus métricas, bolsas, gastos fijos y movimientos. La implementación presente es una demostración de lectura basada en `data/mock.ts`; los cambios de vista, tema, filtros y estados son estado local del navegador.

**No incluye:** persistencia, API, conexión bancaria, actualización o creación de transacciones, reparto real de ingresos, conversión entre monedas ni autenticación funcional. La pantalla de contraseña y los controles de desarrollo son prototipos locales. La interfaz no ofrece acciones para modificar datos financieros.

## 2. Principios de diseño

El brief recibido no contiene un listado adicional de principios visuales. Lo que sí especifica y está respaldado por la implementación es:

- **Solo lectura:** se presentan datos y controles de consulta; no hay operaciones de escritura financiera.
- **Fidelidad a la fuente:** cifras, mensajes, formatos y estados descritos aquí provienen del código actual.
- **Monedas separadas:** CRC y USD se formatean por separado; la interfaz indica «Sin convertir».
- **Estados explícitos:** existen estados de carga, vacío, error y mes cerrado para la demostración.
- **Responsive:** navegación inferior en móvil, barra lateral en pantallas mayores y contenido que cambia de columnas según breakpoint.

Otros principios no especificados en el brief: **No diseñado**.

## 3. Tokens

### Variables de `globals.css`

Los valores de la columna «oscuro» son los de `.dark`. Cuando el sistema operativo prefiere oscuro y el elemento raíz no tiene la clase `light`, la regla `@media (prefers-color-scheme: dark)` vuelve a declarar los valores salvo los dos tokens señalados en la nota posterior. Esa condición no distingue el tema «Sistema» del tema «Oscuro».

| Variable | Claro (`:root`) | Oscuro (`.dark`) | Uso en la implementación |
|---|---|---|---|
| `--background` | `oklch(1 0 0)` | `oklch(0.145 0 0)` | Fondo de página, controles y superficies. |
| `--foreground` | `oklch(0.145 0 0)` | `oklch(0.985 0 0)` | Texto principal. |
| `--card` | `oklch(1 0 0)` | `oklch(0.205 0 0)` | Fondo de tarjetas. |
| `--card-foreground` | `oklch(0.145 0 0)` | `oklch(0.985 0 0)` | Texto de tarjetas. |
| `--popover` | `oklch(1 0 0)` | `oklch(0.205 0 0)` | Fondo de los selectores emergentes. |
| `--popover-foreground` | `oklch(0.145 0 0)` | `oklch(0.985 0 0)` | Texto de los selectores emergentes. |
| `--primary` | `oklch(0.48 0.14 158)` | `oklch(0.72 0.14 158)` | Acciones, estado seleccionado y serie de ingresos. |
| `--primary-foreground` | `oklch(0.99 0.01 150)` | `oklch(0.18 0.02 158)` | Texto/iconos sobre el primario. |
| `--secondary` | `oklch(0.97 0 0)` | `oklch(0.269 0 0)` | Superficie secundaria del tema. |
| `--secondary-foreground` | `oklch(0.205 0 0)` | `oklch(0.985 0 0)` | Contenido secundario. |
| `--muted` | `oklch(0.97 0 0)` | `oklch(0.269 0 0)` | Superficies atenuadas, skeletons y fondos hover. |
| `--muted-foreground` | `oklch(0.556 0 0)` | `oklch(0.708 0 0)` | Texto secundario y etiquetas de gráficos. |
| `--accent` | `oklch(0.97 0 0)` | `oklch(0.269 0 0)` | Acento semántico; sin uso directo identificado en el panel. |
| `--accent-foreground` | `oklch(0.205 0 0)` | `oklch(0.985 0 0)` | Contenido del acento; sin uso directo identificado. |
| `--destructive` | `oklch(0.577 0.245 27.325)` | `oklch(0.704 0.191 22.216)` | Sobregasto, atrasos y error. |
| `--border` | `oklch(0.922 0 0)` | `oklch(1 0 0 / 10%)` | Bordes de tarjetas, controles y líneas de cuadrícula. |
| `--input` | `oklch(0.922 0 0)` | `oklch(1 0 0 / 15%)` | Token semántico de borde de entrada; los inputs usan clases `border`. |
| `--ring` | `oklch(0.708 0 0)` | `oklch(0.556 0 0)` | Anillo de foco visible. |
| `--chart-1` | `oklch(0.87 0 0)` | `oklch(0.87 0 0)` | Primer color de categoría. |
| `--chart-2` | `oklch(0.556 0 0)` | `oklch(0.556 0 0)` | Segundo color de categoría. |
| `--chart-3` | `oklch(0.439 0 0)` | `oklch(0.439 0 0)` | Serie de gasto histórico y tercer color de categoría. |
| `--chart-4` | `oklch(0.371 0 0)` | `oklch(0.371 0 0)` | Cuarto color de categoría. |
| `--chart-5` | `oklch(0.269 0 0)` | `oklch(0.269 0 0)` | Serie de ahorro histórico y quinto color de categoría. |
| `--radius` | `0.625rem` | `0.625rem` | Base de los radios derivados del tema. |
| `--sidebar` | `oklch(0.985 0 0)` | `oklch(0.205 0 0)` | Token de superficie sidebar; el panel usa `bg-background`. |
| `--sidebar-foreground` | `oklch(0.145 0 0)` | `oklch(0.985 0 0)` | Token de texto sidebar; no aplicado directamente. |
| `--sidebar-primary` | `oklch(0.205 0 0)` | `oklch(0.488 0.243 264.376)` | Token de primario sidebar; no aplicado directamente. |
| `--sidebar-primary-foreground` | `oklch(0.985 0 0)` | `oklch(0.985 0 0)` | Token de contenido del primario sidebar; no aplicado directamente. |
| `--sidebar-accent` | `oklch(0.97 0 0)` | `oklch(0.269 0 0)` | Token de acento sidebar; no aplicado directamente. |
| `--sidebar-accent-foreground` | `oklch(0.205 0 0)` | `oklch(0.985 0 0)` | Token de contenido del acento sidebar; no aplicado directamente. |
| `--sidebar-border` | `oklch(0.922 0 0)` | `oklch(1 0 0 / 10%)` | Token de borde sidebar; no aplicado directamente. |
| `--sidebar-ring` | `oklch(0.708 0 0)` | `oklch(0.556 0 0)` | Token de foco sidebar; no aplicado directamente. |

**Excepción del tema de sistema oscuro:** dentro de `@media (prefers-color-scheme: dark)`, `:root:not(.light)` asigna `--primary: oklch(0.922 0 0)` y `--primary-foreground: oklch(0.205 0 0)`. La misma regla reafirma los demás valores oscuros indicados en la tabla. El modo claro/oscuro/sistema se cambia agregando o quitando las clases `light` y `dark` al elemento raíz.

### Alias declarados en `@theme inline`

Son alias exactos a variables semánticas; sus valores efectivos se heredan de la tabla anterior.

| Alias CSS | Valor declarado |
|---|---|
| `--color-sidebar-ring` | `var(--sidebar-ring)` |
| `--color-sidebar-border` | `var(--sidebar-border)` |
| `--color-sidebar-accent-foreground` | `var(--sidebar-accent-foreground)` |
| `--color-sidebar-accent` | `var(--sidebar-accent)` |
| `--color-sidebar-primary-foreground` | `var(--sidebar-primary-foreground)` |
| `--color-sidebar-primary` | `var(--sidebar-primary)` |
| `--color-sidebar-foreground` | `var(--sidebar-foreground)` |
| `--color-sidebar` | `var(--sidebar)` |
| `--color-chart-5` | `var(--chart-5)` |
| `--color-chart-4` | `var(--chart-4)` |
| `--color-chart-3` | `var(--chart-3)` |
| `--color-chart-2` | `var(--chart-2)` |
| `--color-chart-1` | `var(--chart-1)` |
| `--color-ring` | `var(--ring)` |
| `--color-input` | `var(--input)` |
| `--color-border` | `var(--border)` |
| `--color-destructive` | `var(--destructive)` |
| `--color-accent-foreground` | `var(--accent-foreground)` |
| `--color-accent` | `var(--accent)` |
| `--color-muted-foreground` | `var(--muted-foreground)` |
| `--color-muted` | `var(--muted)` |
| `--color-secondary-foreground` | `var(--secondary-foreground)` |
| `--color-secondary` | `var(--secondary)` |
| `--color-primary-foreground` | `var(--primary-foreground)` |
| `--color-primary` | `var(--primary)` |
| `--color-popover-foreground` | `var(--popover-foreground)` |
| `--color-popover` | `var(--popover)` |
| `--color-card-foreground` | `var(--card-foreground)` |
| `--color-card` | `var(--card)` |
| `--color-foreground` | `var(--foreground)` |
| `--color-background` | `var(--background)` |
| `--radius-sm` | `calc(var(--radius) * 0.6)` |
| `--radius-md` | `calc(var(--radius) * 0.8)` |
| `--radius-lg` | `var(--radius)` |
| `--radius-xl` | `calc(var(--radius) * 1.4)` |
| `--radius-2xl` | `calc(var(--radius) * 1.8)` |
| `--radius-3xl` | `calc(var(--radius) * 2.2)` |
| `--radius-4xl` | `calc(var(--radius) * 2.6)` |

### Tipografía, espaciado, bordes, radios, sombras e íconos

- **Familia tipográfica:** `No diseñado` en `globals.css`; no hay importación o declaración de `font-family` en `layout.tsx`. El `<body>` usa `antialiased`.
- **Tamaños/clases presentes:** `text-xs`, `text-sm`, `text-base`, `text-lg`, `text-2xl`; el encabezado mensual usa `text-[clamp(1.5rem,5.5vw,2rem)]` y los valores de métricas `text-[clamp(1rem,4.3vw,1.5rem)]`. En el gráfico histórico los ticks usan 10 y 11 px; tooltip, 12 px.
- **Pesos presentes:** `font-medium`, `font-semibold`; no hay escala tipográfica propia declarada.
- **Espaciado:** no hay tokens de espaciado propios en `globals.css`. Se usan utilidades Tailwind, entre ellas `p-4`, `sm:p-5`, `px-4`, `sm:px-6`, `gap-3`, `gap-4`, `sm:gap-5`, `lg:gap-6`, `pt-4` y `py-3`. El padding inferior del contenido y de la navegación contempla `env(safe-area-inset-bottom)`.
- **Radios:** `rounded-lg`, `rounded-xl`, `rounded-2xl`, `rounded-full` y `rounded` en barras. Los alias numéricos aparecen arriba; las tarjetas usan `rounded-xl`.
- **Bordes:** utilidades `border`, `border-b`, `border-t`, `border-r`, `border-y`, `divide-y`; el color semántico general es `--border`. No se declara ancho global personalizado.
- **Sombras:** `shadow-lg` para selectores de mes/tema y `shadow-xl` para el panel móvil de filtros. No hay token de sombra propio en `globals.css`.
- **Íconos:** `lucide-react`. Se usan `Wallet`, `LayoutDashboard`, `PiggyBank`, `CreditCard`, `AlertCircle`, `ArrowDownLeft`, `ArrowDownRight`, `ArrowLeft`, `ArrowRight`, `ArrowUpRight`, `Check`, `ChevronDown`, `CircleDollarSign`, `CircleHelp`, `Menu`, `Monitor`, `Moon`, `MoreHorizontal`, `Sun` y `X`. Los tamaños se asignan con clases como `size-3.5`, `size-4`, `size-5` y `size-6`.

## 4. Puntos de corte y reglas de layout

Los puntos de corte corresponden a las utilidades responsive de Tailwind usadas en los componentes: `sm` (640 px), `md` (768 px), `lg` (1024 px), `xl` (1280 px). El selector de mes usa además `min-[400px]`; el gráfico cambia el conteo de ticks con `(max-width: 1023px)`.

### Móvil: 320–767 px

- Header sticky en dos niveles: marca/tema y selector mensual a ancho completo.
- Navegación fija inferior, con área segura inferior.
- Contenido en una columna; métricas en grilla 2 × 2.
- Gráficos apilados y leyenda del histórico debajo del gráfico.
- Filtros de movimientos plegables; al abrirlos aparecen como panel inferior fijo.
- Movimientos como tarjetas; listado tabular oculto.

```text
┌────────────────────────────┐
│ Marca                  Tema│
│      ← Mes →               │
├───��────────────────────────┤
│ Resumen de mes   Estado    │
│ Avisos                     │
│ Métrica 1  │ Métrica 2      │
│ Métrica 3  │ Métrica 4      │
│ Historial + leyenda        │
│ Gastos fijos               │
│ Sin asignar                │
│ Categorías                 │
│ Panel de desarrollo / Salir│
├────────────────────────────┤
│ Resumen │ Bolsas │ Movim.   │
└────────────────────────────��
```

### `md`: 768–1023 px

- Header en una fila; barra lateral fija de 76 px con íconos sin texto visible.
- El área principal reserva 76 px a la izquierda.
- Las métricas siguen en dos columnas; las bolsas en dos columnas.
- Movimientos pasan a tabla; los filtros continúan dentro del panel móvil hasta `lg`.
- El gráfico mantiene leyenda debajo y usa ticks compactos.

```text
┌───────────────────────────────────────────┐
│ Marca                 ← Mes →        Tema │
├───────┬───────────────────────────────────┤
│       │ Resumen de mes             Estado │
│       │ Avisos                            │
│ iconos│ Métrica 1 │ Métrica 2              │
│   ↓   │ Métrica 3 │ Métrica 4              │
│       │ Historial + leyenda               │
│       │ Gastos fijos / Sin asignar         │
│       │ Categorías                        │
│       │ Desarrollo / Salir                 │
│       │                                     │
│       │ Tabla de movimientos en su vista   │
└───────┴───────────────────────────────────┘
```

### `lg` y `xl`: desde 1024 px

- Header en una fila; barra lateral de 240 px con icono y etiqueta.
- Filtros de movimientos en línea.
- Dashboard con grilla de 12 columnas; el grupo historial/gastos fijos ocupa 8 y el grupo sin asignar/categorías 4.
- Métricas en cuatro columnas; histórico y leyenda en fila, con leyenda lateral.
- Desde `xl` (1280 px), las tarjetas de bolsas usan tres columnas.
- El contenido y header tienen ancho máximo de 1280 px.

```text
┌──────────────────────────────────────────────────────────────────┐
│ Marca                           ← Mes →                      Tema│
├───────────────────────┬──────────────────────────────────────────┤
│ Resumen               │ Título del mes                 Estado    │
│ Bolsas                │ Avisos                                    │
│ Movimientos           │ Métrica 1 │ Métrica 2 │ Métrica 3 │ Métrica 4│
│                       │ Historial (8/12)    │ Sin asignar (4/12) │
│ Solo lectura          │ Gastos fijos (8/12) │ Categorías (4/12) │
│                       │ Desarrollo / Salir                       │
└───────────────────────┴──────────────────────────────────────────┘
```

## 5. Navegación y estados activos

- **Móvil (<768):** barra inferior fija con `Resumen`, `Bolsas` y `Movimientos`; cada botón muestra icono y etiqueta.
- **Tablet (768–1023):** barra lateral fija de 76 px; solo iconos, con nombre accesible mediante `aria-label`.
- **Escritorio (≥1024):** barra lateral fija de 240 px; icono y etiqueta.
- La pantalla activa es el estado local `screen` de `PuroDashboard`, inicia en `Resumen`. El botón activo lleva `aria-current="page"`, fondo `bg-primary/10` y texto `text-primary`; las otras opciones usan `text-muted-foreground` y hover.
- La navegación cambia la vista sin cambiar la URL. El mes puede avanzar/retroceder; el selector deshabilita meses futuros. El tema ofrece `Claro`, `Oscuro` y `Sistema`.
- «Salir» cambia el estado local a la pantalla de contraseña. «Entrar» no tiene manejador y la autenticación estática comunica que se habilitará más adelante.

## 6. Pantallas y orden de secciones

El shell común contiene header, contenido principal, panel de desarrollo y botón «Salir»; la navegación se fija aparte. El estado de carga/vacío/error reemplaza el contenido de la pantalla seleccionada, pero conserva el shell.

1. **Resumen:** encabezado «Resumen de» + mes formateado y badge de estado; avisos; cuatro métricas; en la grilla inferior, columna izquierda: evolución mensual y gastos fijos; columna derecha: sin asignar y gasto por categoría.
2. **Bolsas:** título «Tus bolsas», texto «Distribución y avance de tus objetivos» y tarjetas de cada bolsa.
3. **Movimientos:** título, texto «Los 10 registros más recientes», filtros y resultados. En móvil los resultados son tarjetas; desde `md`, tabla.
4. **Estados especiales:** skeleton de carga, tarjeta vacía o tarjeta de error con acción «Reintentar».
5. **Panel de desarrollo:** sección `<details>` plegable con selector de vista; aparece debajo de la pantalla principal.
6. **Salir:** botón de texto al final del contenido; al activarlo muestra `LoginScreen`.

En la vista Resumen, las tarjetas de métricas aparecen en este orden: ingresos, gastado, disponible, ahorrado. La leyenda del gráfico de categorías sigue el orden de `data.categories`.

## 7. Componentes

Todos los componentes de esta tabla están declarados en `components/puro-dashboard.tsx`, excepto donde se indica. Los valores financieros vienen de `data/mock.ts`; ningún componente consulta una API.

| Componente | Datos/props TypeScript | Variantes, estados y comportamiento responsive | Accesibilidad presente |
|---|---|---|---|
| `PuroDashboard` | Sin props; mantiene `screen`, `month`, `theme`, `state`, `loggedIn`. | Shell; el estado cambia entre vistas; ancho máximo 1280 px; oculta overflow horizontal. | `main`, header y navegación; tema de sistema sincronizado con `matchMedia`. |
| `Header` | `month: string`, `setMonth: (v: string) => void`, `theme: ThemeMode`, `setTheme: (v: ThemeMode) => void`. | Header sticky; selector en dos filas móvil y una desde `md`; etiqueta mensual abreviada bajo 400 px. Meses futuros deshabilitados; menú de tema. | `header`; botones nombrados; `aria-haspopup`, `aria-expanded`, `aria-pressed`; escape cierra y devuelve foco al botón; click exterior cierra. |
| `Sidebar` | `active: Screen`, `setActive: (v: Screen) => void`. | Barra inferior móvil, lateral 76 px en `md`, lateral 240 px en `lg`. | `aside`, `nav aria-label`, botones con `aria-label`, `aria-current`; iconos decorativos `aria-hidden`. |
| `Card` | `children: React.ReactNode`, `className?: string`. | Sección con borde, fondo de tarjeta y radio `rounded-xl`; variantes por clases del llamador. | `<section>`; nombre accesible depende del heading provisto por el contenido. |
| `CardHeading` | `title: string`, `detail?: string`. | Título y detalle; padding aumenta en `sm`; incluye botón de más opciones sin acción implementada. | `h2`; botón con `aria-label="Más opciones: …"`. |
| `StatusBadge` | `closed: boolean`. | «Mes abierto» verde primario o «Mes cerrado» atenuado. | Texto visible; el punto de color no tiene nombre propio. |
| `AlertPanel` | `monthClosed: boolean`; estado local de alertas descartadas. | Mes cerrado reemplaza la lista por texto de solo lectura; abierto muestra avisos descartables y contador. | Lista `ul/li`, iconos `aria-hidden`, botón de descarte con nombre accesible. |
| `MetricGrid` | Sin props; usa `metricItems` y `dashboardData`. | 2 columnas; 4 desde `lg`; valor con `clamp`. | Textos visibles; iconos decorativos sin alternativa. |
| `Unassigned` | Sin props; usa `data.unassigned`. | Dos columnas: CRC y USD. | Encabezado y montos como texto. |
| `HistoryChart` | Sin props; `data.history`. | Área 220 px, 250 px desde `sm`; leyenda inferior antes de `lg` y lateral en `lg`; compacta ticks hasta 1023 px. | Contenedor `role="img"` con nombre, `accessibilityLayer` y resumen `sr-only`; la leyenda visual es `aria-hidden`. |
| `CategoryChart` | Sin props; `data.categories`. | Donut cuadrado con máximo 220 px; leyenda en lista debajo. | Contenedor `role="img"` con nombre y `accessibilityLayer`; categorías también se exponen como lista textual. |
| `FixedExpenses` | Sin props; `data.fixed`. | Lista vertical con icono, detalle, monto y estado. | Lista `ul/li`; nombres/estados en texto. |
| `Overview` | `month: string`, `closed: boolean`. | Orden de secciones descrito en §6; distribución en columnas desde `lg`. | Título `h1`; los demás nombres son headings de tarjeta. |
| `PocketCard` | `pocket: (typeof data.pockets)[number]`. | Rama `consumo` o `acumulable`; alerta warning/danger; muestra progreso y disponible o balance/meta. Tarjetas 1 columna móvil, 2 `md`, 3 `xl`. | Barras `role="progressbar"` con etiqueta, mínimo/máximo y valor. El valor `used` puede ser mayor que `aria-valuemax` (ej. 104 frente a 100). |
| `Pockets` | Sin props; `data.pockets`. | Grid `md:grid-cols-2`, `xl:grid-cols-3`. | `h1`, nombre de bolsa y valores en texto. |
| `MovementFilters` | `type`, `setType`, `pocket`, `setPocket`, `month`, `setMonth`, `includeVoid`, `setIncludeVoid`, `open`, `setOpen`. | Filtros inline desde `lg`; antes, botón que abre panel inferior fijo con controles apilados y botón «Ver resultados». | Selects asociados a `label`; input month con `aria-label`; checkbox con texto. El botón que abre filtros no expone `aria-expanded`; el panel no declara rol de diálogo ni focus trap. |
| `MovementList` | `type`, `pocket`, `month`, `includeVoid`. | Filtra por mes, tipo, bolsa y anulados; móvil muestra tarjetas y `md` tabla. Vacío muestra `c.empty`. | Tabla semántica en desktop; estados «Anulado»/«Pendiente» también se expresan con texto. |
| `Movements` | Sin props; estado local de filtros y panel. | Inicia con todos los tipos/bolsas, mes de `data.month`, anulados excluidos. | Título `h1`; controles reciben etiquetas en `MovementFilters`. |
| `DevelopmentPanel` | `state: string`, `setState: (v: string) => void`. | `<details>` plegable; opciones normal, carga, vacío, error y mes cerrado. | `summary` nativo y botones con foco visible. |
| `LoadingView` | Sin props. | Skeleton de título, métricas y dos bloques; grillas cambian en `lg`. | No tiene texto de estado accesible propio. |
| `StateNotice` | `state: string`, `onRetry: () => void`. | Retorna skeleton, vacío o error; para otros valores no renderiza nada. | Iconos acompañados por texto; «Reintentar» tiene foco visible. |
| `LoginScreen` | Sin props. | Tarjeta centrada, ancho máximo `max-w-sm`. | `main`, etiqueta vinculada a password. Botón de entrada no está conectado a autenticación. |

## 8. Contrato de datos

La columna **Campo de la API** queda intencionalmente vacía para completar al definir una API. Los tipos `Pocket`, `Movement`, `ThemeMode` y `Screen` sí están declarados en `data/mock.ts`; los demás tipos de fila son los inferidos por `dashboardData`.

| Campo de `data/mock.ts` | Tipo actual | Campo de la API |
|---|---|---|
| `dashboardData.month` | `string` (`"2026-11"`) | |
| `dashboardData.closed` | `boolean` | |
| `dashboardData.pendingClose` | `string` | |
| `dashboardData.income` | `number` | |
| `dashboardData.spent` | `number` | |
| `dashboardData.available` | `number` | |
| `dashboardData.saved` | `number` | |
| `dashboardData.unassigned.crcCount` | `number` | |
| `dashboardData.unassigned.crcTotal` | `number` | |
| `dashboardData.unassigned.usdCount` | `number` | |
| `dashboardData.unassigned.usdTotal` | `number` | |
| `dashboardData.pockets` | `Pocket[]` | |
| `Pocket.name` | `string` | |
| `Pocket.kind` | `"consumo" \| "acumulable"` | |
| `Pocket.assigned`, `sent`, `received`, `adjusted`, `spent`, `available`, `used`, `balance` | `number \| undefined` | |
| `Pocket.goal` | `{ name: string; target: number; progress: number; remaining: number; monthlyAverage: number; projectable: boolean } \| undefined` | |
| `dashboardData.categories` | `{ name: string; value: number }[]` | |
| `dashboardData.history` | `{ month: string; income: number; spent: number; saved: number }[]` | |
| `dashboardData.fixed` | `{ name: string; amount: number; currency: "CRC" \| "USD"; status: "Pagado" \| "Pendiente" \| "Atrasado"; detail: string }[]` (forma inferida) | |
| `dashboardData.movements` | `Movement[]` | |
| `Movement.ref` | `string` | |
| `Movement.date` | `string` | |
| `Movement.description` | `string` | |
| `Movement.pocket` | `string` | |
| `Movement.amount` | `number` | |
| `Movement.currency` | `"CRC" \| "USD"` | |
| `Movement.type` | `"gasto" \| "ingreso" \| "transferencia"` | |
| `Movement.status` | `"pending" \| "void" \| undefined` | |
| `Movement.reason` | `string \| undefined` | |
| `ThemeMode` | `"light" \| "dark" \| "system"` | |
| `Screen` | `"Resumen" \| "Bolsas" \| "Movimientos"` | |

## 9. Formatos

Funciones reales de `lib/format.ts`:

```ts
export const formatCRC = (value: number) => `₡${Math.abs(value).toLocaleString("en-US", { maximumFractionDigits: 0 }).replaceAll(",", ".")}`
export const formatUSD = (value: number) => `US$ ${Math.abs(value).toLocaleString("es-CR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
export const formatPercent = (value: number) => `${new Intl.NumberFormat("es-CR", { maximumFractionDigits: 0 }).format(value)} %`
export const formatDate = (value: string) => new Intl.DateTimeFormat("es-CR", { day: "numeric", month: "short" }).format(new Date(`${value}T12:00:00`))
export const formatMonth = (value: string) => new Intl.DateTimeFormat("es-CR", { month: "long", year: "numeric" }).format(new Date(`${value}-15T12:00:00`))
```

| Dato | Ejemplo de salida exacta | Regla |
|---|---|---|
| CRC `540000` | `₡540.000` | Valor absoluto, sin decimales, separador de miles de `en-US` reemplazado por punto. |
| CRC `-4500` | `₡4.500` | `formatCRC` elimina signo; donde corresponde, el llamador antepone `−`. |
| USD `12.99` | `US$ 12,99` | Valor absoluto, dos decimales, locale `es-CR`. No convierte divisas. |
| Porcentaje `82` | `82 %` | Locale `es-CR`, máximo cero decimales y un espacio antes de `%`. |
| Fecha `2026-11-09` | `9 nov` | Día numérico y mes abreviado en locale `es-CR`; parsea al mediodía local. |
| Mes `2026-11` | `noviembre de 2026` | Mes largo y año en locale `es-CR`; el título de resumen capitaliza la primera letra. |

El eje histórico expresa miles como `₡500k`; el tooltip usa `₡500k`. El resumen mensual da formato a los totales en CRC. En movimientos se antepone `+` cuando `amount > 0`; en caso contrario se antepone `−`. `money` usa `Math.abs` para el valor monetario.

## 10. Textos

Contenido completo y literal de `lib/copy.ts`:

```ts
export const copy = {
  brand: "Puro Pockets", subtitle: "Tus finanzas, en orden.", nav: ["Resumen", "Bolsas", "Movimientos"] as const,
  monthOpen: "Mes abierto", monthClosed: "Mes cerrado", readOnly: "Este mes está cerrado y es de solo lectura",
  metrics: { income: "Ingresos del mes", spent: "Gastado", available: "Disponible", saved: "Ahorrado", unassigned: "Sin asignar" },
  alerts: "Avisos", closePending: "Falta cerrar octubre", extraPending: "1 extra sin asignar", danger: "Sobregasto", warning: "Uso alto",
  history: "Evolución mensual", category: "Gasto por categoría", fixed: "Gastos fijos", pockets: "Tus bolsas", movements: "Movimientos recientes",
  filters: "Filtros", all: "Todos", canceled: "Incluir anulados", retry: "Reintentar", loading: "Cargando tus datos…", empty: "No hay movimientos para mostrar.", error: "No pudimos cargar tus datos.", month: "Mes",
  loginTitle: "Qué dicha verte", loginDescription: "Ingresá tu contraseña para ver tus bolsitas.", password: "Contraseña", enter: "Entrar", readOnlyLabel: "Solo lectura",
  used: "usado del presupuesto ajustado", original: "Presupuesto original", received: "Recibidas", sent: "Enviadas", balance: "Saldo actual", goal: "Meta", remaining: "Faltan", estimate: "Estimado", noEstimate: "Sin estimación",
  paid: "Pagado", pending: "Pendiente", late: "Atrasado", void: "Anulado", type: "Tipo", pocket: "Bolsa", date: "Fecha", description: "Descripción", amount: "Monto", reason: "Motivo", status: "Estado", noLogin: "La autenticación se habilitará más adelante.", development: "Panel de desarrollo", state: "Estado de vista", closedMonth: "Mes cerrado", standard: "Normal", loadingState: "Carga", emptyState: "Vacío", errorState: "Error de conexión", theme: "Tema", light: "Claro", dark: "Oscuro", system: "Sistema", signOut: "Salir", currencyNote: "Sin convertir", progress: "Avance de la meta", adjusted: "Presupuesto ajustado",
} as const
```

## 11. Alertas y cálculos mostrados

- **Avisos del resumen:** lista estática con «Falta cerrar octubre», «Gustos superó el presupuesto en ₡4.500» y «1 extra sin asignar · US$ 25,00». Cada aviso se puede descartar localmente. Si se descartan todos, aparece «Todo está al día.» La lista se sustituye por `c.readOnly` si el mes está cerrado. `closePending` y `extraPending` existen en `copy.ts`, pero los textos visibles del panel están escritos directamente en el componente.
- **Bolsa de consumo — uso alto:** si `used >= 80` y no hay condición de peligro, etiqueta «Uso alto».
- **Bolsa de consumo — sobregasto:** si `used >= 100` o `available < 0`, prevalece «Sobregasto». La barra dibujada limita su ancho a `Math.min(used, 100)%`; el texto porcentual sigue mostrando el valor sin limitar.
- **Meta:** `months = Math.ceil(remaining / monthlyAverage)`; se parte de `new Date("2026-11-15T12:00:00")`, se suman esos meses y se muestra mes/año en `es-CR`. En el ejemplo, Viaje (`20.000 / 60.000`) da `diciembre de 2026`; Fondo de emergencia (`150.000 / 25.000`) da `mayo de 2027`. Si `projectable` es falso, se muestra «Sin estimación».
- **Otras cifras:** `adjusted`, `available`, `used`, `progress` y los totales son valores de `data/mock.ts`; el componente no los recalcula desde los demás importes. El título de categorías «₡310.000 en total» también está fijo en el componente.
- **Movimientos:** filtro por `date.startsWith(month)`, tipo, bolsa y estado `void`. Los anulados se excluyen por defecto. El filtro de bolsa separa `pocket` por ` · ` para transferencias. No hay ordenamiento, paginación o límite dinámico implementado; se muestra el arreglo en el orden fuente.

## 12. Estados

| Estado | Apariencia y texto | Comportamiento actual |
|---|---|---|
| Normal | Pantalla seleccionada con datos mock. | Estado inicial. El panel de desarrollo permite volver a normal. |
| Carga | Skeleton pulsante de título, cuatro métricas y dos tarjetas/bloques. | No hay petición de red; estado conmutado manualmente. `c.loading` no se muestra en `LoadingView`. |
| Vacío | Tarjeta centrada con icono y «No hay movimientos para mostrar.» | La vista vacía global reemplaza el contenido. La lista también usa ese texto cuando sus filtros no encuentran filas. |
| Error | Tarjeta con icono, «No pudimos cargar tus datos.» y botón «Reintentar». | Reintentar cambia el estado local a normal; no repite una petición. |
| Mes cerrado | Badge «Mes cerrado» y aviso «Este mes está cerrado y es de solo lectura». | Se activa con `state === "closed"` o `data.closed`; el panel de avisos se reemplaza. No hay backend ni escritura que bloquear. |
| Login | Tarjeta centrada con marca, campo de contraseña, botón «Entrar» y texto sobre autenticación futura. | Se muestra al pulsar «Salir»; el botón «Entrar» no autentica ni cambia estado. |

El estado de demostración puede inicializarse leyendo `?state=` de la URL (`normal`, `loading`, `empty`, `error`); también se puede cambiar desde «Panel de desarrollo».

## 13. Accesibilidad

- **Estructura:** `header`, `main`, `aside`, `nav`, headings, listas y tabla semántica; la página declara `lang="es-CR"`.
- **Navegación:** nombre de navegación, nombre por botón, `aria-current="page"` para la vista activa e iconos decorativos `aria-hidden`.
- **Controles:** botones principales tienen nombres accesibles, áreas táctiles de al menos 44 px (`size-11`/`min-h-11`) y estilos `focus-visible` con anillo.
- **Selector mensual:** botón con mes nombrado, `aria-haspopup="dialog"`, `aria-expanded`, diálogo etiquetado, meses con `aria-label` y `aria-pressed`, futuros deshabilitados, Escape cierra y devuelve foco; click exterior cierra.
- **Tema:** botón nombrado y expandible; opciones expresan selección con `aria-pressed`.
- **Avisos:** lista semántica; iconos ocultos a lectores de pantalla; botón de descarte con nombre que incluye el aviso.
- **Gráficos:** `role="img"` y etiqueta descriptiva; histórico incluye un resumen textual `sr-only`; categorías incluye leyenda en lista. El gráfico de histórico oculta la leyenda visual accesoria con `aria-hidden`.
- **Progreso:** tarjetas de bolsas declaran `role="progressbar"`, nombre, mínimo, máximo y valor. En el ejemplo de Gustos, `aria-valuenow` es 104 y `aria-valuemax` es 100 aunque el ancho visual está limitado a 100; ese valor fuera de rango requiere revisión antes de considerar el componente conforme.
- **Filtros:** selects con labels, mes con nombre accesible y checkbox con texto asociado. El panel móvil actual no anuncia expansión como diálogo ni implementa trampa de foco.
- **Login:** etiqueta asociada al input de contraseña; autenticación no implementada.
- **Movimiento reducido:** `globals.css` reduce scroll suave, animaciones, iteraciones y transiciones mediante `prefers-reduced-motion: reduce`.

## 14. Criterios de aceptación responsive

Marcar cada casilla después de revisar la vista con el navegador en el ancho indicado. Cada celda distingue modo claro y oscuro.

| Ancho | Claro | Oscuro | Verificar |
|---:|:---:|:---:|---|
| 320 px | [ ] | [ ] | Sin scroll horizontal; métricas, fecha, botones y navegación no se cortan. |
| 360 px | [ ] | [ ] | Encabezado y controles mensuales caben; etiquetas y montos no se superponen. |
| 768 px | [ ] | [ ] | Sidebar de iconos; tabla visible; filtros siguen en panel desplegable. |
| 1024 px | [ ] | [ ] | Sidebar expandida; filtros inline; grilla principal 8/4; leyenda lateral. |
| 1280 px | [ ] | [ ] | Ancho máximo 1280 px; tres columnas de bolsas disponibles. |
| 1920 px | [ ] | [ ] | Contenido permanece centrado y limitado; no aparecen huecos/overflow nuevos. |

## 15. Datos de ejemplo

Copia literal de `data/mock.ts`. Estos datos son **SOLO de ejemplo**; no representan datos reales ni se sincronizan con una API.

```ts
export type ThemeMode = "light" | "dark" | "system"
export type Screen = "Resumen" | "Bolsas" | "Movimientos"
export interface Pocket { name: string; kind: "consumo" | "acumulable"; assigned?: number; sent?: number; received?: number; adjusted?: number; spent?: number; available?: number; used?: number; balance?: number; goal?: { name: string; target: number; progress: number; remaining: number; monthlyAverage: number; projectable: boolean } }
export interface Movement { ref: string; date: string; description: string; pocket: string; amount: number; currency: "CRC" | "USD"; type: "gasto" | "ingreso" | "transferencia"; status?: "pending" | "void"; reason?: string }
export const dashboardData = {
  month: "2026-11", closed: false, pendingClose: "2026-10", income: 540000, spent: 310000, available: 230000, saved: 90000,
  unassigned: { crcCount: 0, crcTotal: 0, usdCount: 1, usdTotal: 25 },
  pockets: [
    { name: "Necesidades", kind: "consumo", assigned: 250000, sent: 7500, adjusted: 242500, spent: 198000, available: 44500, used: 82 },
    { name: "Gustos", kind: "consumo", assigned: 100000, received: 7500, adjusted: 107500, spent: 112000, available: -4500, used: 104 },
    { name: "Ahorro", kind: "acumulable", balance: 480000, goal: { name: "Viaje", target: 500000, progress: 96, remaining: 20000, monthlyAverage: 60000, projectable: true } },
    { name: "Emergencias", kind: "acumulable", balance: 150000, goal: { name: "Fondo de emergencia", target: 300000, progress: 50, remaining: 150000, monthlyAverage: 25000, projectable: true } },
    { name: "Hogar", kind: "acumulable", balance: 0 },
  ] as Pocket[],
  categories: [{name:"Alimentación",value:95000},{name:"Vivienda",value:80000},{name:"Salidas",value:52000},{name:"Ropa",value:35000},{name:"Suscripciones",value:25000},{name:"Transporte",value:23000}],
  history: [{month:"jun",income:500,spent:430,saved:70},{month:"jul",income:500,spent:455,saved:45},{month:"ago",income:520,spent:410,saved:110},{month:"sep",income:500,spent:470,saved:30},{month:"oct",income:520,spent:440,saved:80},{month:"nov",income:540,spent:310,saved:90}],
  fixed: [{name:"Alquiler",amount:80000,currency:"CRC",status:"Pagado",detail:"G-41"},{name:"Internet",amount:18000,currency:"CRC",status:"Pendiente",detail:"Vence el día 15"},{name:"Suscripción de video",amount:12.99,currency:"USD",status:"Pendiente",detail:"Vence el día 20"},{name:"Seguro",amount:22000,currency:"CRC",status:"Atrasado",detail:"Venció el día 5"}],
  movements: [
    {ref:"G-52",date:"2026-11-11",description:"Supermercado",pocket:"Necesidades",amount:-18500,currency:"CRC",type:"gasto"},
    {ref:"T-3",date:"2026-11-10",description:"Necesidades → Gustos",pocket:"Necesidades · Gustos",amount:7500,currency:"CRC",type:"transferencia",reason:"Cubrir sobregasto"},
    {ref:"G-51",date:"2026-11-10",description:"Salida con amigos",pocket:"Gustos",amount:-12000,currency:"CRC",type:"gasto"},
    {ref:"I-9",date:"2026-11-09",description:"Extra en dólares",pocket:"Sin asignar",amount:25,currency:"USD",type:"ingreso",status:"pending"},
    {ref:"G-50",date:"2026-11-09",description:"Transporte",pocket:"Necesidades",amount:-6500,currency:"CRC",type:"gasto"},
    {ref:"G-49",date:"2026-11-08",description:"Ropa",pocket:"Gustos",amount:-35000,currency:"CRC",type:"gasto",status:"void"},
    {ref:"G-48",date:"2026-11-08",description:"Internet",pocket:"Necesidades",amount:-18000,currency:"CRC",type:"gasto"},
    {ref:"G-47",date:"2026-11-07",description:"Suscripción",pocket:"Gustos",amount:-9000,currency:"CRC",type:"gasto"},
    {ref:"I-8",date:"2026-11-01",description:"Salario",pocket:"Ingresos",amount:500000,currency:"CRC",type:"ingreso"},
    {ref:"T-2",date:"2026-10-30",description:"Ahorro → Emergencias",pocket:"Ahorro · Emergencias",amount:25000,currency:"CRC",type:"transferencia",reason:"Reasignación"},
  ] as Movement[],
} as const
```

## 16. Fuera de alcance y decisiones pendientes

- API, modelo de servidor, persistencia, sincronización y autorización: **No diseñado**.
- Reglas reales para cerrar un mes, calcular un presupuesto o determinar «extras pendientes»: **No diseñado**; las cifras y avisos actuales son mock/estáticos.
- Conversión CRC/USD, tipo de cambio y moneda base: **No diseñado**; el texto existente es «Sin convertir».
- Comportamiento funcional del botón «Entrar», recuperación de contraseña y sesiones: **No diseñado**.
- Acción del botón «Más opciones» en cada tarjeta: **No diseñado**.
- Orden/paginación de movimientos y datos posteriores a los diez registros de ejemplo: **No diseñado**.
- Decisión de si los estados simulados y «Panel de desarrollo» deben mantenerse en producción: **No diseñado**.
- Revisión de `aria-valuenow` para valores superiores al 100 y semántica/foco del panel móvil de filtros: pendiente de definición/implementación.
