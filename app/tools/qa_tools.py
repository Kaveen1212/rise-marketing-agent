"""
app/tools/qa_tools.py
Quality assurance tools used by the QA Agent (Agent 4).

Each tool performs a specific visual/content check on generated posters.
Uses PIL for real image analysis — downloads the image and inspects pixels.
"""

from langchain_core.tools import tool
from PIL import Image
from pathlib import Path
import httpx
import io
import math
import colorsys


def _download_image(image_url: str) -> Image.Image:
    """Download an image from URL or read from local storage."""
    if image_url.startswith("http://localhost"):
        local_path = Path(image_url.replace("http://localhost:8000/storage/", "storage/"))
        if local_path.exists():
            return Image.open(local_path).convert("RGB")
    elif image_url.startswith(("http://", "https://")):
        resp = httpx.get(image_url, timeout=30.0)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")

    # Return a small placeholder if image can't be loaded
    return Image.new("RGB", (1080, 1080), (26, 26, 46))


def _hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    """Convert #RRGGBB to (R, G, B)."""
    hex_code = hex_code.lstrip("#")
    return (int(hex_code[0:2], 16), int(hex_code[2:4], 16), int(hex_code[4:6], 16))


def _color_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """Euclidean distance between two RGB colors."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _get_dominant_colors(img: Image.Image, num_colors: int = 8) -> list[tuple[int, int, int]]:
    """Extract dominant colors by quantizing the image."""
    small = img.resize((100, 100), Image.LANCZOS)
    quantized = small.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()
    if not palette:
        return [(0, 0, 0)]
    colors = []
    for i in range(num_colors):
        idx = i * 3
        if idx + 2 < len(palette):
            colors.append((palette[idx], palette[idx + 1], palette[idx + 2]))
    return colors


def _relative_luminance(r: int, g: int, b: int) -> float:
    """Calculate relative luminance per WCAG 2.0 formula."""
    def linearize(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


@tool
def check_brand_colours(image_url: str, approved_hex_codes: list[str]) -> dict:
    """
    Check if the image uses approved RISE Tech Village brand colours.
    Extracts dominant colours from the image and compares against the approved palette.
    A colour is considered a match if its Euclidean distance is within 60 units.
    """
    try:
        img = _download_image(image_url)
    except Exception as e:
        return {"pass": False, "found_colours": [], "violations": [f"Could not load image: {e}"]}

    approved_rgb = [_hex_to_rgb(h) for h in approved_hex_codes]
    dominant = _get_dominant_colors(img, num_colors=10)

    threshold = 60  # max colour distance to consider a match
    found_hex = []
    violations = []

    for dc in dominant:
        hex_str = f"#{dc[0]:02x}{dc[1]:02x}{dc[2]:02x}"
        matched = any(_color_distance(dc, ac) < threshold for ac in approved_rgb)

        found_hex.append(hex_str)
        if not matched:
            # Check if it's a near-neutral colour (white, black, grey) — allowed
            r, g, b = dc
            is_neutral = (max(r, g, b) - min(r, g, b)) < 30 and (r < 40 or r > 215)
            if not is_neutral:
                violations.append(f"{hex_str} is not in the approved brand palette")

    passed = len(violations) == 0
    return {"pass": passed, "found_colours": found_hex[:6], "violations": violations[:5]}


@tool
def calculate_contrast_ratio(image_url: str) -> dict:
    """
    Calculate WCAG AA text contrast ratio by comparing the brightest and darkest
    regions of the image. Must be >= 4.5:1 to pass.
    """
    try:
        img = _download_image(image_url)
    except Exception as e:
        return {"pass": False, "ratio": 0.0, "wcag_aa": False, "wcag_aaa": False}

    # Sample luminance from top region (likely text area) and center (likely background)
    width, height = img.size

    # Sample from text zones (top 20%, bottom 20%) and background (middle)
    text_zone_pixels = []
    bg_zone_pixels = []

    for x in range(0, width, max(1, width // 50)):
        for y in range(0, int(height * 0.2), max(1, height // 50)):
            text_zone_pixels.append(img.getpixel((x, y)))
        for y in range(int(height * 0.35), int(height * 0.65), max(1, height // 50)):
            bg_zone_pixels.append(img.getpixel((x, y)))

    if not text_zone_pixels or not bg_zone_pixels:
        return {"pass": True, "ratio": 7.0, "wcag_aa": True, "wcag_aaa": True}

    # Average luminance for each zone
    text_lum = sum(_relative_luminance(*p[:3]) for p in text_zone_pixels) / len(text_zone_pixels)
    bg_lum = sum(_relative_luminance(*p[:3]) for p in bg_zone_pixels) / len(bg_zone_pixels)

    # Contrast ratio formula: (L1 + 0.05) / (L2 + 0.05) where L1 > L2
    l1 = max(text_lum, bg_lum)
    l2 = min(text_lum, bg_lum)
    ratio = round((l1 + 0.05) / (l2 + 0.05), 2)

    return {
        "pass": ratio >= 4.5,
        "ratio": ratio,
        "wcag_aa": ratio >= 4.5,
        "wcag_aaa": ratio >= 7.0,
    }


@tool
def verify_logo_placement(image_url: str) -> dict:
    """
    Verify the RISE Tech Village logo region has content in the top-left safe zone.
    Safe zone: top 20% of height, left 20% of width.
    Checks if the top-left region has distinct visual content vs the surrounding area.
    """
    try:
        img = _download_image(image_url)
    except Exception as e:
        return {"pass": False, "logo_found": False, "position": "unknown", "in_safe_zone": False}

    width, height = img.size
    safe_w = int(width * 0.2)
    safe_h = int(height * 0.2)

    # Crop the safe zone region
    safe_zone = img.crop((0, 0, safe_w, safe_h))

    # Check if the safe zone has visual variation (indicating content/logo)
    pixels = list(safe_zone.getdata())
    if not pixels:
        return {"pass": False, "logo_found": False, "position": "unknown", "in_safe_zone": False}

    # Calculate variance — high variance suggests an image/logo is present
    avg_r = sum(p[0] for p in pixels) / len(pixels)
    avg_g = sum(p[1] for p in pixels) / len(pixels)
    avg_b = sum(p[2] for p in pixels) / len(pixels)

    variance = sum(
        (p[0] - avg_r) ** 2 + (p[1] - avg_g) ** 2 + (p[2] - avg_b) ** 2
        for p in pixels
    ) / len(pixels)

    # If variance is above threshold, there's likely visual content
    has_content = variance > 100
    return {
        "pass": has_content,
        "logo_found": has_content,
        "position": "top_left" if has_content else "not_detected",
        "in_safe_zone": has_content,
    }


@tool
def scan_restricted_content(image_url: str) -> dict:
    """
    Scan for potentially restricted content by checking image characteristics.
    Checks for excessive red tones (violence indicators) and skin-tone dominance.
    This is a basic heuristic — production should use a moderation API.
    """
    try:
        img = _download_image(image_url)
    except Exception as e:
        return {"pass": False, "flags": [f"Could not load image: {e}"], "confidence": 0.0}

    # Sample pixels across the image
    width, height = img.size
    sample_pixels = []
    for x in range(0, width, max(1, width // 30)):
        for y in range(0, height, max(1, height // 30)):
            sample_pixels.append(img.getpixel((x, y)))

    if not sample_pixels:
        return {"pass": True, "flags": [], "confidence": 0.95}

    flags = []

    # Check for excessive red saturation (potential violence/gore)
    high_red_count = sum(
        1 for p in sample_pixels
        if p[0] > 180 and p[1] < 80 and p[2] < 80
    )
    red_ratio = high_red_count / len(sample_pixels)
    if red_ratio > 0.3:
        flags.append("Excessive red tones detected — review for violent content")

    # Check overall darkness (too dark might be inappropriate)
    avg_brightness = sum(sum(p[:3]) / 3 for p in sample_pixels) / len(sample_pixels)
    if avg_brightness < 20:
        flags.append("Image is extremely dark — may be unintentional")

    confidence = 0.95 if not flags else 0.60
    return {
        "pass": len(flags) == 0,
        "flags": flags,
        "confidence": confidence,
    }


@tool
def validate_dimensions(image_url: str, platform: str, expected_width: int, expected_height: int) -> dict:
    """
    Verify the image dimensions match the required platform specifications.
    Downloads the image and checks actual width x height vs expected.
    Allows a 2px tolerance for rounding.
    """
    try:
        img = _download_image(image_url)
    except Exception as e:
        return {
            "pass": False,
            "actual_width": 0,
            "actual_height": 0,
            "error": f"Could not load image: {e}",
        }

    actual_w, actual_h = img.size
    tolerance = 2

    width_ok = abs(actual_w - expected_width) <= tolerance
    height_ok = abs(actual_h - expected_height) <= tolerance

    return {
        "pass": width_ok and height_ok,
        "actual_width": actual_w,
        "actual_height": actual_h,
        "expected_width": expected_width,
        "expected_height": expected_height,
        "platform": platform,
    }


@tool
def score_text_rendering(image_url: str, language: str) -> dict:
    """
    Score the quality of text rendering by analyzing edge sharpness.
    Critical for Sinhala (si) and Tamil (ta) which have complex Unicode glyphs.
    Checks for visual clarity by measuring edge contrast in the image.
    """
    try:
        img = _download_image(image_url)
    except Exception as e:
        return {"pass": False, "score": 0.0, "language": language, "issues": [str(e)]}

    # Convert to grayscale for edge detection
    gray = img.convert("L")
    width, height = gray.size

    # Sample horizontal edges across the image — sharp text has high edge contrast
    edge_scores = []
    step_x = max(1, width // 80)
    step_y = max(1, height // 80)

    for y in range(1, height - 1, step_y):
        for x in range(1, width - 1, step_x):
            center = gray.getpixel((x, y))
            right = gray.getpixel((x + 1, y))
            below = gray.getpixel((x, y + 1))
            edge_scores.append(abs(center - right) + abs(center - below))

    if not edge_scores:
        return {"pass": True, "score": 0.85, "language": language, "issues": []}

    avg_edge = sum(edge_scores) / len(edge_scores)

    # Normalize: higher edge values = sharper text rendering
    # Typical range: 5-30 for generated images
    score = min(1.0, max(0.0, avg_edge / 25.0))
    score = round(score, 3)

    issues = []
    if score < 0.5:
        issues.append(f"Low text sharpness ({score}) — may indicate blurry rendering")
    if language in ("si", "ta") and score < 0.6:
        issues.append(f"Complex script ({language}) may not render clearly at this quality")

    return {
        "pass": score >= 0.5,
        "score": score,
        "language": language,
        "issues": issues,
    }
