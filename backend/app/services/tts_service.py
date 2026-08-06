"""Text-to-speech ARCHITECTURE ONLY (Phase 13).

This module builds the announcement *text* that a real TTS engine would be
handed in a future phase. It performs simple, real string templating - no
audio synthesis, no external TTS/audio API call, no audio file is produced.
`TvDisplayConfig.tts_enabled`/`tts_template` (see
`models/tv_display_config.py`) are the persisted configuration this reads;
wiring an actual speech engine (browser `SpeechSynthesis`, a cloud TTS API,
etc.) is explicitly out of scope for this phase.
"""


class TtsTemplateError(ValueError):
    """Raised when a configured template references an unknown placeholder."""


_ALLOWED_FIELDS = {"queue_number", "room", "doctor", "patient_initials"}


def generate_announcement_text(
    queue_number: str,
    room: str | None = None,
    *,
    template: str | None = None,
    doctor: str | None = None,
    patient_initials: str | None = None,
) -> str:
    """Render `template` (defaulting to the standard announcement phrase)
    with the given values. Missing optional fields render as an empty
    placeholder-safe string rather than raising, so a display config that
    doesn't route through a room/doctor still gets sensible text.
    """
    template = template or "Queue {queue_number}, please proceed to {room}."
    values = {
        "queue_number": queue_number,
        "room": room or "the counter",
        "doctor": doctor or "",
        "patient_initials": patient_initials or "",
    }
    try:
        return template.format(**values)
    except KeyError as exc:
        raise TtsTemplateError(f"Unknown placeholder in TTS template: {exc}") from exc
