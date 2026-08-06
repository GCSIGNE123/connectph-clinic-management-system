"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import {
  getQueueAnnouncerPrefs,
  saveQueueAnnouncerPrefs,
  announceQueueNumber,
  type QueueAnnouncerPrefs,
} from "@/lib/queue-announcer";

/**
 * Item 8 (Audible Queue Calling): settings for the real Web Speech API TTS
 * announcement that now fires on every successful Call/Recall (Doctor
 * Workspace, Reception Queue, and TV Display all read the same
 * `localStorage`-backed preferences via `lib/queue-announcer.ts`) - same
 * "client-only, no backend model" pattern as Printer Settings
 * (`app/(dashboard)/printer-settings/page.tsx`).
 */
export default function QueueAnnouncerSettingsPage() {
  const [prefs, setPrefs] = useState<QueueAnnouncerPrefs>(getQueueAnnouncerPrefs());
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);

  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;

    // Voices are frequently NOT available synchronously on first load (a
    // well-known Web Speech API quirk, especially on Chrome) - populate
    // immediately in case they already are, then again once the async
    // `voiceschanged` event fires.
    const loadVoices = () => setVoices(window.speechSynthesis.getVoices());
    loadVoices();
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", loadVoices);
  }, []);

  function update(patch: Partial<QueueAnnouncerPrefs>) {
    const next = { ...prefs, ...patch };
    setPrefs(next);
    saveQueueAnnouncerPrefs(next);
  }

  function testAnnouncement() {
    announceQueueNumber("A013", prefs);
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Queue Announcer</h1>
        <p className="text-sm text-muted-foreground">
          Controls the spoken (&quot;Now serving patient number…&quot;) announcement that plays on this
          browser/device whenever a Call or Recall succeeds, on the Doctor Workspace, Reception Queue, and
          TV Display views. Stored on this browser/device only.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Announcements</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={prefs.enabled}
              onChange={(e) => update({ enabled: e.target.checked })}
              className="h-4 w-4"
            />
            Enable audio announcements
          </label>

          <div className="space-y-2">
            <Label htmlFor="voice-select">Voice</Label>
            <Select
              id="voice-select"
              value={prefs.voiceURI ?? ""}
              onChange={(e) => update({ voiceURI: e.target.value || null })}
              className="max-w-sm"
              disabled={!prefs.enabled}
            >
              <option value="">Browser default</option>
              {voices.map((v) => (
                <option key={v.voiceURI} value={v.voiceURI}>
                  {v.name} ({v.lang})
                </option>
              ))}
            </Select>
            {voices.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No voices reported yet by this browser - some browsers only populate the voice list after a
                short delay or a first speech attempt.
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="rate-range">Speech rate ({prefs.rate.toFixed(1)}x)</Label>
            <input
              id="rate-range"
              type="range"
              min={0.5}
              max={2}
              step={0.1}
              value={prefs.rate}
              onChange={(e) => update({ rate: Number(e.target.value) })}
              disabled={!prefs.enabled}
              className="max-w-sm"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="volume-range">Volume ({Math.round(prefs.volume * 100)}%)</Label>
            <input
              id="volume-range"
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={prefs.volume}
              onChange={(e) => update({ volume: Number(e.target.value) })}
              disabled={!prefs.enabled}
              className="max-w-sm"
            />
          </div>

          <Button type="button" variant="outline" onClick={testAnnouncement} disabled={!prefs.enabled}>
            Test announcement
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
