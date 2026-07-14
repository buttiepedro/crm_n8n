/** Paleta de respaldo cuando la etapa no tiene color asignado.
 *  Compartida entre el kanban de Leads y el embudo de Analytics para que
 *  cada etapa se vea del mismo color en ambas vistas. */
export const STAGE_COLORS = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6", "#ef4444"];

export function stageColor(color: string | null, index: number): string {
  return color || STAGE_COLORS[index % STAGE_COLORS.length];
}
