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
 * use the identical phrasing for the same queue number.
 *
 * Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): destination-
 * aware. When a room label is configured for this destination (e.g. "Room
 * #1" - see `queue_settings.room_label`, set via the `/queue-settings`
 * admin page), it takes priority over naming the doctor/department at all
 * ("please proceed to Room #1" instead of "...to Dr. X") - the doctor's
 * name is deliberately never spoken once a room is configured for that
 * destination. Without a room, falls back to naming the doctor if
 * assigned, else the department (e.g. Laboratory/Radiology, no doctor
 * assigned). Callers that pass none of the three (all existing non-TV call
 * sites - Doctor Workspace, Reception) get the original, unchanged
 * phrasing, so behavior for every existing caller is identical to before
 * this change.
 *
 * Wording (queue announcement wording update): "Now serving Patient #
 * {N}, please proceed to {destination}." - this exact template is shared
 * by every caller (Doctor Workspace Call/Recall, Reception Call/Re-
 * announce, TV Display), so a single change here updates the spoken
 * wording everywhere at once - no parallel announcement text exists
 * anywhere else in the codebase. */
export function buildAnnouncementText(
  queueNumber: string,
  destination?: { doctorName?: string | null; departmentName?: string | null; roomName?: string | null }
): string {
  const base = `Now serving Patient # ${queueNumber}`;
  if (destination?.roomName) {
    return `${base}, please proceed to ${destination.roomName}.`;
  }
  if (destination?.doctorName) {
    return `${base}, please proceed to Dr. ${destination.doctorName}.`;
  }
  if (destination?.departmentName) {
    return `${base}, please proceed to the ${destination.departmentName}.`;
  }
  return base;
}

// Post-RC1: a small local speak-queue so multiple simultaneous
// announcements (e.g. Doctor A and the Laboratory both get called within
// the same fetch cycle) are spoken one after another instead of the second
// call cancelling the first mid-utterance (`speechSynthesis.cancel()`
// clobbering, the original single-utterance behavior). `enqueueAnnouncement`
// is additive - `announceQueueNumber` (used by Doctor Workspace/Reception,
// which only ever announce one ticket per action) keeps its original
// cancel-and-speak-immediately behavior unchanged.
const speakQueue: string[] = [];
let isSpeaking = false;

function pumpSpeakQueue(prefs: QueueAnnouncerPrefs): void {
  if (isSpeaking) return;
  const next = speakQueue.shift();
  if (next === undefined) return;
  isSpeaking = true;
  try {
    const utterance = new SpeechSynthesisUtterance(next);
    utterance.rate = prefs.rate;
    utterance.volume = prefs.volume;
    if (prefs.voiceURI) {
      const voice = window.speechSynthesis.getVoices().find((v) => v.voiceURI === prefs.voiceURI);
      if (voice) utterance.voice = voice;
    }
    utterance.onend = () => {
      isSpeaking = false;
      pumpSpeakQueue(prefs);
    };
    utterance.onerror = () => {
      isSpeaking = false;
      pumpSpeakQueue(prefs);
    };
    window.speechSynthesis.speak(utterance);
  } catch {
    isSpeaking = false;
  }
}

/**
 * Enqueues a destination-aware announcement to be spoken after any
 * currently-speaking/queued announcement finishes (no overlap, no
 * clobbering - see file-level doc). Use this from the TV Display, where
 * multiple simultaneous Now-Serving changes must each be heard in full.
 */
export function enqueueAnnouncement(
  queueNumber: string | null | undefined,
  destination?: { doctorName?: string | null; departmentName?: string | null; roomName?: string | null },
  prefsOverride?: QueueAnnouncerPrefs
): void {
  if (!queueNumber) return;
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  const prefs = prefsOverride ?? getQueueAnnouncerPrefs();
  if (!prefs.enabled) return;
  try {
    speakQueue.push(buildAnnouncementText(queueNumber, destination));
    pumpSpeakQueue(prefs);
  } catch {
    // Speech is a nice-to-have announcement, never let it break the display.
  }
}

/**
 * Speaks the given queue number, cancelling any announcement still in
 * progress first (overlap prevention - see file-level doc). No-ops
 * silently if the browser lacks `speechSynthesis`, if announcements are
 * disabled in preferences, or if `queueNumber` is falsy (e.g. a ticket with
 * no assigned number yet). Kept for single-announcement callers (Doctor
 * Workspace Call/Recall, Reception) - unchanged behavior.
 */
export function announceQueueNumber(
  queueNumber: string | null | undefined,
  destinationOrPrefs?:
    | { doctorName?: string | null; departmentName?: string | null; roomName?: string | null }
    | QueueAnnouncerPrefs,
  prefsOverride?: QueueAnnouncerPrefs
): void {
  if (!queueNumber) return;
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;

  // Reception Queue Workflow Improvements: `destinationOrPrefs` is
  // additive - existing callers (Doctor Workspace Call/Recall) either omit
  // the second argument entirely or pass a `QueueAnnouncerPrefs` object
  // (identified by its `enabled` key), so their behavior/phrasing is
  // unchanged. A destination object (identified by having none of
  // `QueueAnnouncerPrefs`' required keys) opts into the same
  // "...proceed to Room X" phrasing `enqueueAnnouncement`/TV Display uses.
  const isPrefs = destinationOrPrefs != null && "enabled" in destinationOrPrefs;
  const destination = isPrefs ? undefined : (destinationOrPrefs as
    | { doctorName?: string | null; departmentName?: string | null; roomName?: string | null }
    | undefined);
  const prefs = (isPrefs ? (destinationOrPrefs as QueueAnnouncerPrefs) : prefsOverride) ?? getQueueAnnouncerPrefs();
  if (!prefs.enabled) return;

  try {
    // Prevent overlapping announcements: cancel whatever is still speaking
    // (queued or in-progress) before starting the new one.
    if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
      window.speechSynthesis.cancel();
    }

    const utterance = new SpeechSynthesisUtterance(buildAnnouncementText(queueNumber, destination));
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
