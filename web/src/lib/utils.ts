import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

/** Combina clases de Tailwind (convención de shadcn/ui). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Primera letra en mayúscula (el título del resumen capitaliza el mes, dashboard.md §9). */
export const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)
