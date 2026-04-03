from langchain_core.tools import tool

@tool
def call_stability_ai(prompt: str, negative_prompt: str, width: int, height: int) -> str:
    """
    Generate an image using Stability AI SDXL REST API.
    Returns the S3 URL of the uploaded generated image.
    """
    import httpx, base64, boto3
    # POST to https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image
    # Upload result to S3
    # Return S3 URL
    return "https://s3.amazonaws.com/rise-posters-prod/generated/abc123.jpg"

@tool
def call_dalle3(prompt: str) -> str:
    """
    Generate an image using DALL-E 3 (fallback for complex compositions).
    Returns the S3 URL of the uploaded generated image.
    """
    from openai import OpenAI
    # client.images.generate(model="dall-e-3", prompt=prompt, size="1024x1024")
    # Download image bytes, upload to S3
    return "https://s3.amazonaws.com/rise-posters-prod/generated/def456.jpg"

@tool
def resize_for_platform(image_url: str, platform: str) -> str:
    """
    Download image from S3, resize to correct platform dimensions, re-upload.
    Platform dimensions: instagram=1080x1080, facebook=1200x630, linkedin=1200x627, tiktok=1080x1920
    Returns the S3 URL of the resized image.
    """
    from PIL import Image
    import httpx, io, boto3
    dimensions = {
        "instagram": (1080, 1080),
        "facebook":  (1200, 630),
        "linkedin":  (1200, 627),
        "tiktok":    (1080, 1920),
    }
    # Download, resize with PIL, re-upload to S3 under new key
    return f"https://s3.amazonaws.com/rise-posters-prod/platforms/{platform}/abc123.jpg"

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
