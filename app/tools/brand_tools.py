

from langchain_core.tools import tool



@tool
def validate_brand_guidelines(brand_notes: str) -> dict:
    """
    Validate that the brief's brand_notes align with RISE Tech Village guidelines.
    Returns approved visual elements and flagged violations.
    """
    # In reality: load brand guidelines from DB/file, compare against brand_notes
    # For now: return the approved elements Claude should enforce
    return {
        "approved_colours": ["#1A1A2E", "#16213E", "#0F3460", "#E94560"],
        "approved_fonts": ["Montserrat", "Inter"],
        "logo_required": True,
        "tone_keywords": ["aspirational", "tech-forward", "Sri Lankan-proud"],
        "violations": []
    }

@tool  
def classify_audience_segment(audience: str, platform: str) -> dict:
    """
    Classify the target audience segment for better content targeting.
    Returns demographic profile and content recommendations.
    """
    # Logic: map raw audience text to structured segment data
    return {
        "segment": "young_professionals",
        "age_range": "22-35",
        "interests": ["technology", "career growth", "innovation"],
        "platform_optimal_format": "square_image" if platform == "instagram" else "landscape"
    }
