from typing import TypedDict, Optional

class PosterState(TypedDict):
    # Agent 1 writes these
    brief_id: str
    campaign_topic: str
    platforms: list[str]
    languages: list[str]
    tone: str
    audience_segment: str

    # Agent 2 writes these
    headline: dict        # {"en": "...", "si": "...", "ta": "..."}
    body_copy: dict
    cta: dict
    hashtags: dict
    image_prompt: str 

    # Agent 3 writes these
    image_url: str
    design_manifest: dict
    poster_urls: dict

    # Agent 4 writes these
    qa_report: dict
    qa_confidence: float
    revision_count: int   # max 3

    # Human reviewer writes these (at the interrupt boundary)
    review_status: str    # "pending" | "approved" | "revision" | "rejected"
    review_scores: Optional[dict]
    review_feedback: Optional[str]
    reviewer_id: Optional[str]
    reviewed_at: Optional[str]

    # Agent 5 writes these
    scheduled_at: Optional[dict]
    published_post_ids: Optional[dict]
    analytics_24h: Optional[dict]


