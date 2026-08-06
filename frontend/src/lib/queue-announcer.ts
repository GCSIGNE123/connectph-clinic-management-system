/**
 * Item 8 (Audible Queue Calling): real Text-to-Speech via the Web Speech
 * API, replacing Phase 20 item 12's basic two-tone `playCallCue` chime
 * (`lib/audio-cue.ts` - left in place but no longer wired into Call/Recall,
 * in case something else still references it).
 *
 * A single shared module-level utility (not a React hook) so that Doctor
 * Workspace, the Reception Queue view, and the TV Queue Display can all
 * call the exact same `announceQueueNumber()` without duplicating the
 * "cancel in-progress speech, build an utterance from stored preferences"
 * logic three times. `speechSynthesis` is a single global per page/tab
 * regardless of how many components call into this module, so tracking
 * "is something currently speaking" via `speechSynthesis.speaking` and
 * calling `.cancel()` before every new `.speak()` is sufficient to
 * guarantee only the latest announcement is ever heard - no overlapping
 * voices, per the spec.
 */

export interface QueueAnnouncerPrefs {
  enabled: boolean;
  voiceURI: string | null;
  rate: number;
  volume: number;
}

const STORAGE_KEY = "queue-announcer-prefs";

const DEFAULT_PREFS: QueueAnnouncerPrefs = {
  enabled: true,
  voiceURI: null,
  rate: 1,
  volume: 1,
};

export function getQueueAnnouncerPrefs(): QueueAnnouncerPrefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<QueueAnnouncerPrefs>;
    return { ...DEFAULT_PREFS, ...parsed };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function saveQueueAnnouncerPrefs(prefs: QueueAnnouncerPrefs): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}

/** Builds the spoken announcement text - shared so Call and Recall always
 * use the identical phrasing for the same queue number. */
export function buildAnnouncementText(queueNumber: string): string {
  return `Now serving patient number ${queueNumber}`;
}

/**
 * Speaks the given queue number, cancelling any announcement still in
 * progress first (overlap prevention - see file-level doc). No-ops
 * silently if the browser lacks `speechSynthesis`, if announcements are
 * disabled in preferences, or if `queueNumber` is falsy (e.g. a ticket with
 * no assigned number yet).
 */
export function announceQueueNumber(queueNumber: string | null | undefined, prefsOverride?: QueueAnnouncerPrefs): void {
  if (!queueNumber) return;
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;

  const prefs = prefsOverride ?? getQueueAnnouncerPrefs();
  if (!prefs.enabled) return;

  try {
    // Prevent overlapping announcements: cancel whatever is still speaking
    // (queued or in-progress) before starting the new one.
    if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
      window.speechSynthesis.cancel();
    }

    const utterance = new SpeechSynthesisUtterance(buildAnnouncementText(queueNumber));
    utterance.rate = prefs.rate;
    utterance.volume = prefs.volume;

    if (prefs.voiceURI) {
      const voice = window.speechSynthesis.getVoices().find((v) => v.voiceURI === prefs.voiceURI);
      if (voice) utterance.voice = voice;
    }

    window.speechSynthesis.speak(utterance);
  } catch {
    // Speech is a nice-to-have announcement, never let it break Call/Recall.
  }
}
