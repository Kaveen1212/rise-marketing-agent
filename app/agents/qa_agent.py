# app/agents/qa_agent.py
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from app.graph.state import PosterState
from app.tools.qa_tools import (
    check_brand_colours,
    calculate_contrast_ratio,
    verify_logo_placement,
    scan_restricted_content,
    validate_dimensions,
    score_text_rendering,
)
import json


# The LLM this agent uses
_llm = ChatAnthropic(model="claude-sonnet-4-6")

# The tools this agent has access to
_tools = [
    check_brand_colours,
    calculate_contrast_ratio,
    verify_logo_placement,
    scan_restricted_content,
    validate_dimensions,
    score_text_rendering,
]

# The agent itself
_agent = create_react_agent(_llm, _tools)

def qa_agent(state: PosterState) -> dict:
    checks_to_run = []
    for platform in state['platforms']:
        checks_to_run.append(f"- validate_dimensions for {platform}")
    for lang in state['languages']:
        checks_to_run.append(f"- score_text_rendering for language '{lang}'")
    
    result = _agent.invoke({
        "messages": [
            {
                "role": "system", 
                "content": """You are the QA Agent for RISE Tech Village poster system.
                Run ALL quality checks before a human sees this poster.
                
                REQUIRED CHECKS (run every single one):
                1. check_brand_colours — approved: #1A1A2E, #16213E, #0F3460, #E94560
                2. calculate_contrast_ratio — must be >= 4.5:1 (WCAG AA)
                3. verify_logo_placement — must be in top-left safe zone
                4. scan_restricted_content — zero tolerance for flagged content
                5. validate_dimensions — for each platform
                6. score_text_rendering — for each language (critical for Sinhala/Tamil)
                
                CONFIDENCE SCORING:
                - Start at 1.0
                - Subtract 0.25 for each FAIL
                - Subtract 0.10 for each soft warning
                
                Return ONLY this JSON:
                {
                  "qa_report": {
                    "brand_colours": {"pass": bool, "details": "..."},
                    "contrast_ratio": {"pass": bool, "ratio": float},
                    "logo_placement": {"pass": bool, "position": "..."},
                    "restricted_content": {"pass": bool, "flags": []},
                    "dimensions": {"pass": bool},
                    "text_rendering": {"pass": bool, "score": float}
                  },
                  "qa_confidence": 0.0-1.0
                }"""
            },
            {
                "role": "user",
                "content": f"""
                Run full QA on this poster:
                Base image: {state['image_url']}
                Platform images: {state['poster_urls']}
                Languages used: {state['languages']}
                Platforms: {state['platforms']}

                Required dimension and rendering checks for THIS poster:
                {chr(10).join(checks_to_run)}

                Run every check listed in your instructions. Do not skip any.
                """
            }
        ]
    })
    parsed = json.loads(result["messages"][-1].content)
    return {
        "qa_report":     parsed["qa_report"],
        "qa_confidence": parsed["qa_confidence"],
    }
