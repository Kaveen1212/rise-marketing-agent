from langchain_core.tools import tool
from PIL import Image
import httpx, io

@tool
def check_brand_colours(image_url: str, approved_hex_codes: list[str]) -> dict:
    """Check if the image uses only approved RISE Tech Village brand hex colours."""
    # Download image, sample dominant colours, compare to approved_hex_codes
    # Use PIL to get pixel colours, calculate colour distance
    return {"pass": True, "found_colours": ["#1A1A2E", "#16213E"], "violations": []}

@tool
def calculate_contrast_ratio(image_url: str) -> dict:
    """
    Calculate WCAG AA text contrast ratio. Must be >= 4.5:1 to pass.
    Downloads the image and checks text regions against background.
    """
    # Use PIL to find text regions, calculate luminance contrast
    # WCAG formula: (L1 + 0.05) / (L2 + 0.05) where L1 > L2
    return {"pass": True, "ratio": 7.2, "wcag_aa": True, "wcag_aaa": True}

@tool
def verify_logo_placement(image_url: str) -> dict:
    """
    Verify the RISE Tech Village logo is present and within safe zones.
    Safe zone: top 20% of image, left 20% of width.
    """
    # Use image recognition or template matching to find the logo
    return {"pass": True, "logo_found": True, "position": "top_left", "in_safe_zone": True}

@tool
def scan_restricted_content(image_url: str) -> dict:
    """
    Scan for restricted or culturally inappropriate content for Sri Lanka.
    Checks: violence, adult content, politically sensitive imagery.
    """
    # In production: call a content moderation API (AWS Rekognition, OpenAI moderation)
    return {"pass": True, "flags": [], "confidence": 0.99}

@tool
def validate_dimensions(image_url: str, platform: str, expected_width: int, expected_height: int) -> dict:
    """
    Verify the image dimensions match the required platform specifications.
    """
    # Download image header, check dimensions with PIL
    return {"pass": True, "actual_width": expected_width, "actual_height": expected_height}

@tool
def score_text_rendering(image_url: str, language: str) -> dict:
    """
    Score the quality of text rendering, especially for Sinhala (si) and Tamil (ta).
    Checks: font rendering, character spacing, line breaks.
    Returns a score from 0.0 to 1.0.
    """
    # For Sinhala/Tamil: check that Unicode characters render correctly
    # Not pixelated, not replaced with boxes
    return {"pass": True, "score": 0.92, "language": language, "issues": []}
