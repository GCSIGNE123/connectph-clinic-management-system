/**
 * Phase 20 (item 12): a single, simple audible cue for Doctor Workspace's
 * Call/Recall actions - deliberately NOT a configurable sound system, just
 * one short two-tone chime via the Web Audio API (no bundled audio file,
 * no new dependency). Safe to call from any browser event handler (an
 * `AudioContext` created here is a fresh, short-lived one per cue, which
 * avoids the "one AudioContext per page, must be resumed after a user
 * gesture" lifecycle complexity - the Call/Recall button click IS the user
 * gesture that unlocks audio in every modern browser's autoplay policy).
 */
export function playCallCue(): void {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const now = ctx.currentTime;

    const playTone = (freq: number, start: number, duration: number) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, now + start);
      gain.gain.setValueAtTime(0.0001, now + start);
      gain.gain.exponentialRampToValueAtTime(0.2, now + start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + start + duration);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + start);
      osc.stop(now + start + duration + 0.02);
    };

    // Two-tone "ding-dong" style chime, ~0.5s total.
    playTone(880, 0, 0.18);
    playTone(659, 0.2, 0.22);

    // Close the context shortly after the tones finish so we don't leak
    // AudioContext instances if Call/Recall is pressed repeatedly.
    window.setTimeout(() => {
      ctx.close().catch(() => {});
    }, 900);
  } catch {
    // Audio is a nice-to-have cue, never let it break the Call/Recall action.
  }
}
