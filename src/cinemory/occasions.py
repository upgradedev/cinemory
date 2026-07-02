"""Occasion presets — config-driven themes that shape a reel.

An :class:`Occasion` bundles the creative direction for a reel: the music mood,
the pacing (how long each clip lingers and how scenes transition), the title
style, and prompt direction injected into every scene. Presets broaden Cinemory
beyond its anniversary origin to graduations, birthdays, weddings, year-in-review
recaps and business/award events.

Config-driven and easy to extend: add one entry to :data:`OCCASIONS` (a plain
dict of dataclasses — no external files, no package-data wiring) and it is
immediately selectable from the CLI, the API (`GET /occasions`) and the web UI.
Nothing else needs to change; the pipeline stays occasion-agnostic and simply
consumes the resulting :class:`~cinemory.models.ReelSpec`.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Occasion:
    """Creative direction for one kind of memory reel."""

    key: str
    label: str
    #: Music mood tag — maps to a track/generation prompt on the live path.
    music_style: str
    #: Target beats-per-minute; drives music-driven cut pacing (see ``music``).
    tempo: float
    #: Seconds each clip lingers on screen — lower = snappier montage.
    seconds_per_clip: float
    #: Transition flavour used for chapter bridges.
    transition: str
    #: Title-card typographic style hint for downstream rendering.
    title_style: str
    #: Injected into every scene prompt to steer the generative look.
    prompt_direction: str
    #: Default aspect ratio (vertical for social-first occasions).
    aspect_ratio: str = "16:9"
    #: Scene labels that override the generic synthetic defaults.
    scene_labels: list[str] = field(default_factory=list)

    def style_prompt(self, base_prompt: str) -> str:
        """Blend a base scene prompt with this occasion's creative direction."""
        base = base_prompt.strip().rstrip(",.")
        return f"{base}, {self.prompt_direction}"


# ── Presets ─────────────────────────────────────────────────────────────────
# To add an occasion: append an Occasion below. That is the entire change.
OCCASIONS: dict[str, Occasion] = {
    "anniversary": Occasion(
        key="anniversary",
        label="Anniversary",
        music_style="warm romantic strings",
        tempo=96.0,
        seconds_per_clip=3.5,
        transition="soft cross-dissolve",
        title_style="elegant serif, gold foil",
        prompt_direction="warm nostalgic light, intimate and cinematic",
        aspect_ratio="16:9",
        scene_labels=["How it began", "Our adventures", "Everyday joy", "Forever"],
    ),
    "graduation": Occasion(
        key="graduation",
        label="Graduation",
        music_style="uplifting orchestral build",
        tempo=112.0,
        seconds_per_clip=2.8,
        transition="bright light-leak wipe",
        title_style="bold modern sans, class-year accent",
        prompt_direction="triumphant golden-hour glow, hopeful and proud",
        aspect_ratio="16:9",
        scene_labels=["The years", "The work", "The moment", "What's next"],
    ),
    "birthday": Occasion(
        key="birthday",
        label="Birthday",
        music_style="playful upbeat pop",
        tempo=124.0,
        seconds_per_clip=2.2,
        transition="quick punch-in cut",
        title_style="rounded playful display, confetti accents",
        prompt_direction="bright saturated colour, festive and fun",
        aspect_ratio="9:16",
        scene_labels=["Another year", "The people", "The party", "Make a wish"],
    ),
    "wedding": Occasion(
        key="wedding",
        label="Wedding",
        music_style="cinematic emotional piano",
        tempo=88.0,
        seconds_per_clip=4.0,
        transition="slow film-dissolve",
        title_style="fine script, ivory and blush",
        prompt_direction="soft dreamy bokeh, timeless and romantic",
        aspect_ratio="16:9",
        scene_labels=["Getting ready", "The vows", "The celebration", "Just married"],
    ),
    "year-in-review": Occasion(
        key="year-in-review",
        label="Year in Review",
        music_style="driving indie montage",
        tempo=120.0,
        seconds_per_clip=1.8,
        transition="rhythmic beat-cut",
        title_style="calendar-stamp mono, month markers",
        prompt_direction="vibrant highlight-reel energy, fast and joyful",
        aspect_ratio="9:16",
        scene_labels=["Q1", "Q2", "Q3", "Q4"],
    ),
    "business-event": Occasion(
        key="business-event",
        label="Business Event / Award Ceremony",
        music_style="confident corporate cinematic",
        tempo=104.0,
        seconds_per_clip=3.2,
        transition="clean linear slide",
        title_style="sharp geometric sans, brand-accent bar",
        prompt_direction="polished professional lighting, premium and credible",
        aspect_ratio="16:9",
        scene_labels=["The venue", "The keynote", "The award", "The team"],
    ),
}

#: Aliases so slash-named occasions resolve to a single canonical key.
_ALIASES: dict[str, str] = {
    "award-ceremony": "business-event",
    "business-event/award-ceremony": "business-event",
    "yearinreview": "year-in-review",
    "year_in_review": "year-in-review",
}

DEFAULT_OCCASION = "anniversary"


def resolve_key(key: str | None) -> str:
    """Normalise a user-supplied occasion key to a canonical preset key."""
    if not key:
        return DEFAULT_OCCASION
    k = key.strip().lower()
    k = _ALIASES.get(k, k)
    return k if k in OCCASIONS else DEFAULT_OCCASION


def get_occasion(key: str | None) -> Occasion:
    """Return the :class:`Occasion` for ``key`` (falls back to the default)."""
    return OCCASIONS[resolve_key(key)]


def list_occasions() -> list[dict]:
    """Serialisable catalogue for the API / web selector."""
    return [
        {
            "key": o.key,
            "label": o.label,
            "music_style": o.music_style,
            "tempo": o.tempo,
            "seconds_per_clip": o.seconds_per_clip,
            "transition": o.transition,
            "title_style": o.title_style,
            "aspect_ratio": o.aspect_ratio,
        }
        for o in OCCASIONS.values()
    ]
