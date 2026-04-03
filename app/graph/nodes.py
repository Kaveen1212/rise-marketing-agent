from app.graph.state import PosterState

def human_review_node(state: PosterState) -> dict:
    """
    This node does nothing. It exists only as a pause point.
    
    LangGraph pauses BEFORE entering this node (interrupt_before=["human_review"]).
    The state is saved to PostgreSQL. Execution stops here.
    
    When the reviewer calls POST /review/{id}/approve (or revise/reject),
    the API calls graph.ainvoke(Command(resume={...})) which injects the
    human's decision into the state and resumes from here.
    
    By the time this node actually runs, review_status is already set.
    It just passes through to route_after_review which reads review_status.
    """
    return {}  # Return empty dict — this node writes nothing to state
