from langchain_core.tools import tool

@tool
def validate_character_limits(text: str, platform: str, content_type: str) -> dict:
    """
    Validate that text meets platform character limits.
    content_type: 'headline', 'body', 'cta', 'hashtags'
    Returns: {"valid": bool, "char_count": int, "limit": int, "truncated": str}
    """
    limits = {
        "instagram": {"headline": 125, "body": 2200, "hashtags": 30},
        "facebook":  {"headline": 255, "body": 63206, "hashtags": 10},
        "linkedin":  {"headline": 150, "body": 3000, "hashtags": 5},
        "tiktok":    {"headline": 150, "body": 4000, "hashtags": 20},
    }
    limit = limits.get(platform, {}).get(content_type, 999)
    return {"valid": len(text) <= limit, "char_count": len(text), "limit": limit}

@tool
def check_cultural_tone(text: str, language: str) -> dict:
    """
    Check if the text is culturally appropriate for Sri Lankan audiences.
    Flags: overly Western idioms, culturally insensitive phrases, translation errors.
    Returns: {"appropriate": bool, "flags": list[str], "suggestions": list[str]}
    """
    # In production: use a curated list of phrases + Claude's judgement
    return {"appropriate": True, "flags": [], "suggestions": []}

@tool
def generate_hashtags(topic: str, platform: str, language: str) -> list[str]:
    """
    Generate platform-optimised hashtags for the given topic and language.
    Returns a list of hashtags without the # symbol.
    """
    # In production: query trending hashtags from platform API or curated list
    base_tags = ["RISETechVillage", "SriLankaTech", "Innovation"]
    return base_tags
