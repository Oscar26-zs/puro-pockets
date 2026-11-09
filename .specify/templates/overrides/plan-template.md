# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

> **Plan delgado (Puro Pockets).** Este plan no repite lo que ya está en
> `.specify/memory/constitution.md` ni en `docs/plan-tecnico.md`: lo referencia. Solo registra lo
> que este hito agrega o cambia. Las reglas se citan por su identificador (`RN-xx`), nunca se
> reescriben.

## Summary

[Qué entrega el hito, en 2 a 4 líneas, tomado de spec.md]

## Technical Context

**Base**: stack, arquitectura y esquema en `docs/plan-tecnico.md`. Aquí solo va lo nuevo o distinto.

**Dependencias nuevas o cambiadas**: [lista con versión fijada, o "ninguna"]

**Cambios al esquema**: [tablas, columnas o migraciones nuevas, o "ninguno"]

**Tools MCP nuevas o modificadas**: [lista, o "ninguna"]

**Decisiones pendientes de las que depende**: [de `HITOS.md` sección 3; si sigue abierta, NEEDS CLARIFICATION]

## Constitution Check

*GATE: debe pasar antes de la fase 0 y revisarse de nuevo después del diseño.*

- **Reglas que implementa este hito**: [RN-xx, solo citadas]
- **Reglas no negociables** (Gobernanza): [✓ o ✗ para cada una: datos reales, capa de negocio,
  invariante de integridad, pruebas por hito]
- **[PROPUESTO] que se asumen**: [lista, para que el propietario las confirme en el reporte]
- **[ABIERTO] de los que depende**: [si hay alguno, DETENER y preguntar al propietario]

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # Este archivo
├── research.md          # Solo si hubo NEEDS CLARIFICATION
├── data-model.md        # Solo si cambia el esquema
├── contracts/           # Solo si hay tools MCP nuevas o modificadas
├── quickstart.md        # Cómo comprobar el "Terminado cuando" del hito
└── tasks.md             # Lo crea /speckit-tasks
```

### Source Code (repository root)

La estructura en capas está en `docs/plan-tecnico.md` (y en `HITOS.md`, Hito 1). Aquí solo se listan
los archivos que este hito crea o modifica:

```text
[ruta/archivo]   # qué cambia
```

## Pruebas

[Pruebas automáticas que verifican cada criterio de aceptación y cada punto del "Terminado cuando"
del hito. Son obligatorias (Gobernanza, regla no negociable 4).]

## Actualización del plan técnico al cerrar

[Secciones de `docs/plan-tecnico.md` que cambian con este hito, o "ninguna"]

## Complexity Tracking

> Solo si el Constitution Check tiene violaciones que deban justificarse.

| Violación | Por qué se necesita | Alternativa más simple descartada porque |
|-----------|---------------------|------------------------------------------|
