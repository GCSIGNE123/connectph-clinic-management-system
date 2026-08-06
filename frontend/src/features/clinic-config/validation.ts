/** Small, dependency-free validators for the Clinic Configuration forms. */

export interface QueueSettingsFormInput {
  queue_prefix: string;
  max_daily_queue: number;
  reset_time: string;
}

export function validateQueueSettingsForm(input: QueueSettingsFormInput): string | null {
  if (!input.queue_prefix || input.queue_prefix.trim().length === 0) {
    return "Queue prefix is required.";
  }
  if (input.queue_prefix.length > 10) {
    return "Queue prefix must be 10 characters or fewer.";
  }
  if (!Number.isFinite(input.max_daily_queue) || input.max_daily_queue < 1) {
    return "Max daily queue must be at least 1.";
  }
  if (input.max_daily_queue > 10000) {
    return "Max daily queue must be 10,000 or fewer.";
  }
  if (!/^\d{2}:\d{2}$/.test(input.reset_time)) {
    return "Reset time must be a valid HH:MM value.";
  }
  return null;
}
