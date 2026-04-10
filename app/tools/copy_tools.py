"""
app/tools/copy_tools.py
Copywriting validation tools used by the Copywriter Agent (Agent 2).

Validates text against platform limits, checks cultural appropriateness,
and generates platform-optimised hashtags.
"""

from langchain_core.tools import tool


@tool
def validate_character_limits(text: str, platform: str, content_type: str) -> dict:
    """
    Validate that text meets platform character limits.
    content_type: 'headline', 'body', 'cta', 'hashtags'
    Returns: {"valid": bool, "char_count": int, "limit": int, "truncated": str | None}
    """
    limits = {
        "instagram": {"headline": 125, "body": 2200, "cta": 150, "hashtags": 2200},
        "facebook":  {"headline": 255, "body": 63206, "cta": 255, "hashtags": 5000},
        "linkedin":  {"headline": 150, "body": 3000, "cta": 150, "hashtags": 3000},
        "tiktok":    {"headline": 150, "body": 4000, "cta": 150, "hashtags": 4000},
    }
    limit = limits.get(platform, {}).get(content_type, 999)
    is_valid = len(text) <= limit

    truncated = None
    if not is_valid:
        truncated = text[:limit - 3] + "..."

    return {
        "valid": is_valid,
        "char_count": len(text),
        "limit": limit,
        "truncated": truncated,
    }


# Curated list of culturally sensitive phrases for Sri Lankan context
_CULTURAL_FLAGS = {
    "en": [
        "beef", "pork",                         # dietary sensitivities
        "caste", "ethnic",                       # social sensitivities
        "separatist", "civil war",               # political sensitivities
        "convert", "proselytize",                # religious sensitivities
        "cheap labor", "third world",            # derogatory framing
    ],
    "si": [
        "\u0da7\u0dd2\u0d9a\u0dca\u0d9a\u0da7\u0dca",  # placeholder for culturally flagged Sinhala terms
    ],
    "ta": [
        "\u0b9a\u0bbe\u0ba4\u0bbf",             # caste-related Tamil term
    ],
}

# Phrases that are too Western-centric for Sri Lankan audiences
_WESTERN_IDIOMS = [
    "break the internet", "go viral",
    "hustle culture", "grindset",
    "black friday", "cyber monday",
    "touchdown", "home run",
    "piece of cake", "easy as pie",
    "hit the ground running",
]


@tool
def check_cultural_tone(text: str, language: str) -> dict:
    """
    Check if the text is culturally appropriate for Sri Lankan audiences.
    Flags: culturally sensitive terms, overly Western idioms, potential translation issues.
    Returns: {"appropriate": bool, "flags": list[str], "suggestions": list[str]}
    """
    text_lower = text.lower()
    flags = []
    suggestions = []

    # Check language-specific cultural flags
    lang_flags = _CULTURAL_FLAGS.get(language, _CULTURAL_FLAGS.get("en", []))
    for term in lang_flags:
        if term.lower() in text_lower:
            flags.append(f"Culturally sensitive term detected: '{term}'")
            suggestions.append(f"Consider rephrasing to avoid '{term}' for Sri Lankan audiences")

    # Check Western idioms (mainly in English)
    if language == "en":
        for idiom in _WESTERN_IDIOMS:
            if idiom in text_lower:
                flags.append(f"Western idiom detected: '{idiom}'")
                suggestions.append(f"Replace '{idiom}' with a locally resonant phrase")

    # Check for excessive English in non-English content
    if language in ("si", "ta"):
        ascii_chars = sum(1 for c in text if ord(c) < 128 and c.isalpha())
        total_alpha = sum(1 for c in text if c.isalpha())
        if total_alpha > 0 and (ascii_chars / total_alpha) > 0.5:
            flags.append("High proportion of English text in non-English content")
            suggestions.append("Use more native script for authenticity")

    return {
        "appropriate": len(flags) == 0,
        "flags": flags,
        "suggestions": suggestions,
    }


# Base hashtag sets organised by topic categories
_HASHTAG_BASES = {
    "technology": ["TechSriLanka", "Innovation", "DigitalSL", "FutureTech", "SLTech"],
    "education": ["LearnSriLanka", "Education", "SkillUp", "SLEducation", "KnowledgeHub"],
    "career": ["CareerGrowth", "SLJobs", "ProfessionalDev", "Opportunity", "TalentSL"],
    "community": ["SriLankaCommunity", "SLTogether", "Community", "Impact", "SLPride"],
    "startup": ["StartupSL", "Entrepreneurship", "SLStartups", "Innovation", "FounderLife"],
    "default": ["RISETechVillage", "SriLanka", "Innovation", "Technology", "Growth"],
}

# Platform-specific hashtag counts (optimal for engagement)
_PLATFORM_COUNTS = {
    "instagram": 15,   # Instagram sweet spot: 11-15
    "facebook": 5,     # Facebook: fewer is better
    "linkedin": 5,     # LinkedIn: professional, concise
    "tiktok": 8,       # TikTok: moderate
}


@tool
def generate_hashtags(topic: str, platform: str, language: str) -> list[str]:
    """
    Generate platform-optimised hashtags for the given topic and language.
    Combines brand-specific, topic-specific, and platform-specific hashtags.
    Returns a list of hashtags without the # symbol.
    """
    topic_lower = topic.lower()

    # Find the best matching topic category
    matched_category = "default"
    for category in _HASHTAG_BASES:
        if category in topic_lower:
            matched_category = category
            break

    base_tags = list(_HASHTAG_BASES[matched_category])

    # Always include brand hashtag
    brand_tags = ["RISETechVillage", "RISE"]
    if "RISETechVillage" not in base_tags:
        base_tags = brand_tags + base_tags

    # Add language-specific hashtags
    lang_tags = {
        "en": ["SriLanka", "LK"],
        "si": ["SriLanka", "LK", "sinhala"],
        "ta": ["SriLanka", "LK", "tamil"],
    }
    base_tags.extend(lang_tags.get(language, lang_tags["en"]))

    # Add topic-derived hashtags (split topic into meaningful words)
    topic_words = [w.capitalize() for w in topic.split() if len(w) > 3]
    for word in topic_words[:3]:
        tag = word.replace(" ", "")
        if tag not in base_tags:
            base_tags.append(tag)

    # Trim to platform-optimal count and deduplicate
    max_count = _PLATFORM_COUNTS.get(platform, 10)
    seen = set()
    unique_tags = []
    for tag in base_tags:
        tag_lower = tag.lower()
        if tag_lower not in seen:
            seen.add(tag_lower)
            unique_tags.append(tag)

    return unique_tags[:max_count]
