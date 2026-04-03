from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from app.graph.state import PosterState
from app.tools.copy_tools import validate_character_limits, check_cultural_tone, generate_hashtags
import json

_llm = ChatAnthropic(model="claude-sonnet-4-6")
_tools = [validate_character_limits, check_cultural_tone, generate_hashtags]
_agent = create_react_agent(_llm, _tools)

def copywriter_agent(state: PosterState) -> dict:
    result = _agent.invoke({
        "messages": [
            {
                "role": "system",
                "content": """You are the Copywriter Agent for RISE Tech Village.
                Generate poster copy in ALL requested languages simultaneously.
                
                TONE: Aspirational, tech-forward, Sri Lankan-proud.
                RULES:
                - Validate every text against character limits before finalising
                - Check cultural tone for Sinhala (si) and Tamil (ta) content
                - Generate platform-specific hashtags
                
                Return ONLY this JSON structure:
                {
                  "headline": {"en": "...", "si": "...", "ta": "..."},
                  "body_copy": {"en": "...", "si": "...", "ta": "..."},
                  "cta": {"en": "...", "si": "...", "ta": "..."},
                  "hashtags": {"instagram": [...], "facebook": [...], "linkedin": [...], "tiktok": [...]},
                  "image_prompt": "detailed visual description for image generation AI"
                }"""
            },
            {
                "role": "user",
                "content": f"""
                Campaign brief:
                Topic: {state['campaign_topic']}
                Platforms: {state['platforms']}
                Languages: {state['languages']}
                Audience: {state['audience_segment']}
                Tone: {state['tone']}
                Key message: {state.get('key_message', state['campaign_topic'])}
                
                Generate all copy now. Validate each piece with tools before including it.
                """
            }
        ]
    })
    parsed = json.loads(result["messages"][-1].content)
    return {
        "headline":     parsed["headline"],
        "body_copy":    parsed["body_copy"],
        "cta":          parsed["cta"],
        "hashtags":     parsed["hashtags"],
        "image_prompt": parsed["image_prompt"],
    }
