"""Tournament constants shared across modules."""

ROUND_TIER_ORDER = [
    "round_of_32",
    "sweet_16",
    "elite_eight",
    "final_four",
    "championship_game",
    "champion",
]

ROUND_NAME_TO_TIER = {
    # ESPN headline format (notes[0].headline) — verified against 2025 tournament data
    "1st Round": "round_of_32",
    "2nd Round": "sweet_16",
    "Sweet 16": "elite_eight",
    "Elite 8": "final_four",
    "Final Four": "championship_game",
    "National Championship": "champion",
    # Alternate forms — keep as fallback
    "First Round": "round_of_32",
    "Second Round": "sweet_16",
    "Elite Eight": "final_four",
    "Championship": "champion",
}

# 2026 NCAA Men's Tournament game dates (YYYYMMDD, Eastern time)
TOURNAMENT_GAME_DATES = {
    "20260317",
    "20260318",  # First Four
    "20260319",
    "20260320",  # Round of 64
    "20260321",
    "20260322",  # Round of 32
    "20260326",
    "20260327",  # Sweet 16
    "20260328",
    "20260329",  # Elite Eight
    "20260404",  # Final Four
    "20260406",  # Championship
}

PICKS_ROUND_KEYS = [k for k in ROUND_TIER_ORDER if k != "champion"]

REQUIRED_PICKS_KEYS = set(ROUND_TIER_ORDER)

# Supported image formats for bracket submission (must match Claude Vision API)
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
SUPPORTED_IMAGE_FORMATS_LABEL = "PNG, JPG, GIF, or WebP"
