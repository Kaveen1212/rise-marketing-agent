from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from app.graph.state import PosterState
from app.tools.brand_tools import validate_brand_guidelines, classify_audience_segment
from app.config import settings
from app.agents._parse_json import extract_json

_llm = ChatAnthropic(
    model=settings.ANTHROPIC_MODEL,
    api_key=settings.ANTHROPIC_API_KEY.get_secret_value(),
)
_tools = [validate_brand_guidelines, classify_audience_segment]
_agent = create_react_agent(_llm, _tools)

def brief_parser_agent(state: PosterState) -> dict:
    result = _agent.invoke({
        "messages": [
            {
                "role": "system",
                "content": """You are the Brief Parser Agent for RISE Tech Village.
                Your job: validate and enrich a campaign brief.
                1. Call validate_brand_guidelines with the brand_notes
                2. Call classify_audience_segment for each platform
                3. Return ONLY valid JSON: {"audience_segment": "...", "tone": "..."}
                Never include explanation text — only the JSON object."""
            },
            {
                "role": "user", 
                "content": f"""
                Brief to parse:
                Topic: {state['campaign_topic']}
                Platforms: {state['platforms']}
                Languages: {state['languages']}
                Tone: {state['tone']}
                Audience: {state['audience_segment']}
                Brand notes: {state.get('brand_notes', 'None')}
                
                Validate and return the enriched brief fields as JSON.
                """
            }
        ]
    })
    parsed = extract_json(result["messages"][-1].content)
    return {
        "audience_segment": parsed["audience_segment"],
        "tone": parsed["tone"],
    }
