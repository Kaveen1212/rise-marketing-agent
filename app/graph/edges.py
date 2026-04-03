# app/graph/edges.py
from app.graph.state import PosterState

def route_after_qa(state: PosterState) -> str:
    """After QA Agent runs — go back to designer or proceed to human review."""
    if state["qa_confidence"] < 0.60:
        return "regenerate"   # maps to "designer" node
    return "human_review"

def route_after_review(state: PosterState) -> str:
    """After human reviews — publish, revise, or end."""
    if state["review_status"] == "approved":
        return "approved"     # maps to "publisher" node
    if state["review_status"] == "revision":
        return "revision"     # maps to "designer" node
    return "rejected"         # maps to END
