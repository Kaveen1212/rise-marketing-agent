from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from app.graph.state import PosterState
from app.tools.design_tools import call_stability_ai, call_dalle3, resize_for_platform, select_layout_template
import json

_llm = ChatAnthropic(model="claude-sonnet-4-6")
_tools = [call_stability_ai, call_dalle3, resize_for_platform, select_layout_template]
_agent = create_react_agent(_llm, _tools)

def designer_agent(state: PosterState) -> dict:
    # Build revision context — if this is a revision cycle, inject the feedback
    revision_context = ""
    if state.get("review_feedback"):
        revision_context = f"""
        REVISION REQUIRED — This is revision #{state['revision_count']}.
        The human reviewer rejected the previous version with this feedback:
        "{state['review_feedback']}"
        
        Treat this feedback as HARD CONSTRAINTS — not suggestions.
        Every point of feedback MUST be addressed in this version.
        """
    
    result = _agent.invoke({
        "messages": [
            {
                "role": "system",
                "content": f"""You are the Visual Design Agent for RISE Tech Village.
                Create poster images using the available tools.
                
                BRAND COLOURS: #1A1A2E (dark navy), #16213E (midnight blue), #E94560 (accent red)
                LOGO: Always include in top-left corner within safe zone
                
                {revision_context}
                
                Steps:
                1. Call select_layout_template to choose the best template
                2. Call call_stability_ai with the image prompt (try this first — cheaper)
                3. If Stability AI fails or produces poor output, call call_dalle3 instead
                4. For each platform in the brief, call resize_for_platform
                
                Return ONLY this JSON:
                {{
                  "image_url": "S3 URL of base image",
                  "design_manifest": {{"template": "...", "palette": [...], "fonts": [...]}},
                  "poster_urls": {{"instagram": "...", "facebook": "...", "linkedin": "...", "tiktok": "..."}}
                }}"""
            },
            {
                "role": "user",
                "content": f"""
                Create the poster for:
                Topic: {state['campaign_topic']}
                Image prompt: {state['image_prompt']}
                Platforms needed: {state['platforms']}
                Tone: {state['tone']}
                Audience: {state['audience_segment']}
                """
            }
        ]
    })
    parsed = json.loads(result["messages"][-1].content)
    return {
        "image_url":       parsed["image_url"],
        "design_manifest": parsed["design_manifest"],
        "poster_urls":     parsed["poster_urls"],
    }
