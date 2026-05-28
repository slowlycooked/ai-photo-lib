import type { PersonFeedbackEffects } from "@/api/types";

function formatEffects(effects?: PersonFeedbackEffects): string {
  if (!effects) return "feedback=none";

  const parts: string[] = [];
  if (effects.prototype_rebuilt) {
    const personText = effects.rebuilt_person_ids.length > 0
      ? effects.rebuilt_person_ids.join(",")
      : "unknown";
    parts.push(`prototype=rebuild(person=${personText})`);
  } else {
    parts.push("prototype=skip");
  }

  if (effects.unknown_rematch_requested) {
    const scope = effects.unknown_rematch_scope ?? "unknown";
    const taskId = effects.unknown_rematch_task_id ?? "-";
    const mode = effects.unknown_rematch_task_created ? "queued" : "reused";
    parts.push(`rematch=${scope}/${mode}(task=${taskId})`);
  } else {
    parts.push("rematch=skip");
  }

  return parts.join("; ");
}

export function formatBatchFeedbackToast(
  actionLabel: string,
  updated: number,
  attempts: number,
  effects?: PersonFeedbackEffects,
): string {
  return `${actionLabel}成功：updated=${updated} attempts=${attempts} | ${formatEffects(effects)}`;
}
