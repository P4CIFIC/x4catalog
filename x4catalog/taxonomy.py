"""Small, deliberate vocabulary for X4-oriented cataloguing."""

TAXONOMY: dict[str, tuple[str, ...]] = {
    "subject": (
        "animals", "birds", "cats", "dogs", "insects", "fish", "botanical",
        "flowers", "trees", "people", "portraits", "architecture", "cities",
        "landscape", "mountains", "ocean", "space", "astronomy", "vehicles",
        "technology", "food", "objects", "fantasy", "horror", "religious", "mythology",
    ),
    "franchise": (
        "rick-and-morty", "the-simpsons", "family-guy", "south-park", "futurama",
        "adventure-time", "regular-show", "spongebob-squarepants", "pokemon",
        "super-mario", "the-legend-of-zelda", "minecraft", "star-wars", "marvel",
        "dc-comics", "batman", "spider-man", "sailor-moon", "dragon-ball", "one-piece",
        "naruto", "studio-ghibli", "disney", "mickey-mouse", "hello-kitty",
    ),
    "style": (
        "photograph", "engraving", "woodcut", "etching", "line-art", "ink-drawing",
        "manga", "anime", "comic", "pixel-art", "painting", "watercolor", "poster",
        "collage", "silhouette", "abstract", "pattern", "3d-render",
    ),
    "composition": (
        "single-subject", "multiple-subjects", "centered", "symmetrical", "full-bleed",
        "framed", "bordered", "minimal", "busy", "large-empty-space", "close-up",
        "wide-scene", "text-heavy", "no-text",
    ),
    "display": (
        "mostly-white", "mostly-black", "light", "balanced", "dark", "high-contrast",
        "medium-contrast", "low-contrast", "fine-detail", "large-shapes", "grayscale",
        "binary-black-white", "dithered", "possibly-inverted",
    ),
    "content": (
        "nsfw", "nudity", "partial-nudity", "explicit-nudity", "suggestive",
        "sexualized", "fetish", "violence", "gore", "graphic-violence", "horror",
    ),
    "intensity": (
        "bold", "dramatic", "provocative", "moody", "heavy-ink", "distressed",
        "ornate", "graphic-style", "high-energy", "soft", "stark",
    ),
    "x4": (
        "x4-excellent", "x4-good", "x4-acceptable", "x4-too-dark", "x4-too-busy",
        "x4-too-fine", "x4-small-text", "x4-needs-dithering", "x4-review",
    ),
    "status": (
        "favorite", "keep", "reject", "unreviewed", "low-confidence", "duplicate",
        "near-duplicate", "alternate-version",
    ),
}


def all_tags() -> tuple[str, ...]:
    return tuple(tag for tags in TAXONOMY.values() for tag in tags)


# Hidden on the public gallery unless the visitor turns sensitive content on.
SENSITIVE_TAGS = frozenset(
    {
        "nsfw",
        "nudity",
        "partial-nudity",
        "explicit-nudity",
        "suggestive",
        "sexualized",
        "fetish",
        "violence",
        "gore",
        "graphic-violence",
    }
)


def image_is_sensitive(tags: object) -> bool:
    names = []
    for tag in tags or []:
        if isinstance(tag, dict):
            names.append(str(tag.get("name") or ""))
        else:
            names.append(str(tag))
    return any(name.casefold() in SENSITIVE_TAGS for name in names)
