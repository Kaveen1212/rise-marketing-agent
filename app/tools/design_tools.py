import base64
import io
import uuid
from pathlib import Path

from langchain_core.tools import tool
from PIL import Image, ImageDraw, ImageFont

STORAGE_DIR = Path(__file__).parent.parent.parent / "storage" / "posters"
LOGO_PATH = STORAGE_DIR / "logos" / "RiseLogo.png"


def _to_data_uri(file_path: Path) -> str:
    return f"data:image/jpeg;base64,{base64.b64encode(file_path.read_bytes()).decode()}"


def _overlay_logo(image_bytes: bytes) -> bytes:
    """Composite the RISE eagle logo onto the top-left corner of a poster image."""
    if not LOGO_PATH.exists():
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size

    logo = Image.open(LOGO_PATH).convert("RGBA")

    # Make the black background transparent (threshold < 30 on all channels)
    pixels = logo.load()
    for y in range(logo.height):
        for x in range(logo.width):
            r, g, b, a = pixels[x, y]
            if r < 30 and g < 30 and b < 30:
                pixels[x, y] = (r, g, b, 0)

    # Scale logo to 14% of poster width, preserving aspect ratio
    logo_w = max(60, int(w * 0.14))
    logo_h = int(logo.height * (logo_w / logo.width))
    logo = logo.resize((logo_w, logo_h), Image.LANCZOS)

    # Paste at top-left with 2% padding
    pad = max(10, int(w * 0.02))
    img.paste(logo, (pad, pad), logo)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _generate_placeholder(prompt: str, width: int, height: int) -> bytes:
    """Generate a branded placeholder poster image using PIL."""
    img = Image.new("RGB", (width, height), (26, 26, 46))  # #1A1A2E dark navy
    draw = ImageDraw.Draw(img)

    # Draw brand accent stripe
    draw.rectangle([(0, 0), (width, 8)], fill=(233, 69, 96))  # #E94560
    draw.rectangle([(0, height - 8), (width, height)], fill=(233, 69, 96))

    # Draw text
    try:
        font = ImageFont.truetype("arial.ttf", 28)
        small_font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
        small_font = font

    # Title
    draw.text((width // 2, height // 3), "RISE Tech Village", fill=(233, 69, 96), font=font, anchor="mm")

    # Prompt text (wrapped)
    short_prompt = prompt[:80] + "..." if len(prompt) > 80 else prompt
    draw.text((width // 2, height // 2), short_prompt, fill=(200, 200, 200), font=small_font, anchor="mm")

    # Watermark
    draw.text((width // 2, height - 40), "AI-Generated Poster", fill=(100, 100, 100), font=small_font, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return _overlay_logo(buf.getvalue())


def _clamp_sdxl_dimensions(width: int, height: int) -> tuple[int, int]:
    """Clamp dimensions to valid SDXL values (multiples of 64, 512-1024)."""
    w = max(512, min(1024, (width // 64) * 64))
    h = max(512, min(1024, (height // 64) * 64))
    if w * h > 1048576:
        w, h = 1024, 1024
    return w, h


@tool
def call_stability_ai(prompt: str, negative_prompt: str, width: int, height: int) -> str:
    """
    Generate an image using Stability AI SDXL REST API.
    Falls back to a branded placeholder if the API call fails.
    Returns the local URL of the generated image.
    """
    import httpx, base64
    from app.config import settings

    image_id = uuid.uuid4().hex[:12]
    save_dir = STORAGE_DIR / "generated"
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"{image_id}.jpg"

    api_key = settings.STABILITY_AI_API_KEY
    if not api_key:
        # No API key — use placeholder
        file_path.write_bytes(_generate_placeholder(prompt, 1024, 1024))
        return _to_data_uri(file_path)

    w, h = _clamp_sdxl_dimensions(width, height)

    try:
        response = httpx.post(
            f"https://api.stability.ai/v1/generation/{settings.STABILITY_AI_MODEL}/text-to-image",
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}", "Accept": "application/json"},
            json={
                "text_prompts": [
                    {"text": prompt, "weight": 1.0},
                    {"text": negative_prompt, "weight": -1.0},
                ],
                "cfg_scale": 7, "width": w, "height": h, "samples": 1, "steps": 30,
            },
            timeout=120.0,
        )
        response.raise_for_status()
        image_b64 = response.json()["artifacts"][0]["base64"]
        file_path.write_bytes(_overlay_logo(base64.b64decode(image_b64)))
    except Exception:
        # Fallback: retry with safe 1024x1024
        try:
            response = httpx.post(
                f"https://api.stability.ai/v1/generation/{settings.STABILITY_AI_MODEL}/text-to-image",
                headers={"Authorization": f"Bearer {api_key.get_secret_value()}", "Accept": "application/json"},
                json={
                    "text_prompts": [{"text": prompt, "weight": 1.0}],
                    "cfg_scale": 7, "width": 1024, "height": 1024, "samples": 1, "steps": 30,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            image_b64 = response.json()["artifacts"][0]["base64"]
            file_path.write_bytes(_overlay_logo(base64.b64decode(image_b64)))
        except Exception:
            # Final fallback: branded placeholder
            file_path.write_bytes(_generate_placeholder(prompt, 1024, 1024))

    return _to_data_uri(file_path)


@tool
def call_dalle3(prompt: str) -> str:
    """
    Fallback image generation using Stability AI with a different style preset.
    Falls back to placeholder if API fails.
    Returns the local URL of the generated image.
    """
    import httpx, base64
    from app.config import settings

    image_id = uuid.uuid4().hex[:12]
    save_dir = STORAGE_DIR / "generated"
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"{image_id}.jpg"

    api_key = settings.STABILITY_AI_API_KEY
    if not api_key:
        file_path.write_bytes(_generate_placeholder(prompt, 1024, 1024))
        return _to_data_uri(file_path)

    try:
        response = httpx.post(
            f"https://api.stability.ai/v1/generation/{settings.STABILITY_AI_MODEL}/text-to-image",
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}", "Accept": "application/json"},
            json={
                "text_prompts": [{"text": prompt, "weight": 1.0}],
                "cfg_scale": 10, "width": 1024, "height": 1024,
                "samples": 1, "steps": 40, "style_preset": "digital-art",
            },
            timeout=120.0,
        )
        response.raise_for_status()
        image_b64 = response.json()["artifacts"][0]["base64"]
        file_path.write_bytes(_overlay_logo(base64.b64decode(image_b64)))
    except Exception:
        file_path.write_bytes(_generate_placeholder(prompt, 1024, 1024))

    return _to_data_uri(file_path)


@tool
def resize_for_platform(image_url: str, platform: str) -> str:
    """
    Download image, resize to correct platform dimensions, save locally.
    Platform dimensions: instagram=1080x1080, facebook=1200x630, linkedin=1200x627, tiktok=1080x1920
    Returns the local URL of the resized image.
    """
    import httpx

    dimensions = {
        "instagram": (1080, 1080),
        "facebook":  (1200, 630),
        "linkedin":  (1200, 627),
        "tiktok":    (1080, 1920),
    }
    width, height = dimensions.get(platform, (1080, 1080))

    # Load source image from data URI or URL
    try:
        if image_url.startswith("data:"):
            _, encoded = image_url.split(",", 1)
            image_bytes = base64.b64decode(encoded)
        elif image_url.startswith("http://localhost"):
            local_path = Path(image_url.replace("http://localhost:8000/storage/", "storage/"))
            image_bytes = local_path.read_bytes()
        else:
            import httpx
            resp = httpx.get(image_url, timeout=30.0)
            resp.raise_for_status()
            image_bytes = resp.content
    except Exception:
        image_bytes = _generate_placeholder("Platform resize", width, height)

    # Resize
    img = Image.open(io.BytesIO(image_bytes))
    img = img.resize((width, height), Image.LANCZOS)

    # Save
    image_id = uuid.uuid4().hex[:12]
    save_dir = STORAGE_DIR / "platforms" / platform
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"{image_id}.jpg"
    img.save(file_path, "JPEG", quality=90)

    return _to_data_uri(file_path)


@tool
def select_layout_template(platform: str, tone: str, content_type: str) -> dict:
    """
    Select the best layout template for the given platform and tone.
    Returns template metadata: name, text_zones, logo_position, colour_scheme.
    """
    templates = {
        "instagram_aspirational": {
            "name": "hero_centre",
            "text_zone": "bottom_third",
            "logo_position": "top_left",
        }
    }
    key = f"{platform}_{tone}"
    return templates.get(key, templates["instagram_aspirational"])
