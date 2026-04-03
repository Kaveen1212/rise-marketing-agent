"""
app/services/pipeline_service.py
─────────────────────────────────────────────────────────────────────────────
Manages starting and resuming the LangGraph poster pipeline.

The API routes (briefs.py, review.py) never touch LangGraph directly.
They call this service, which owns all graph complexity.
This keeps routes thin and testable without running the full graph.

Three functions:
  start_pipeline()      → kick off a new graph run from a brief
  resume_pipeline()     → inject human decision and continue the graph
  get_pipeline_status() → read current state from the checkpointer
─────────────────────────────────────────────────────────────────────────────
"""

import structlog
from langgraph.types import Command

from app.graph.pipeline import build_graph
from app.graph.state import PosterState

log = structlog.get_logger()

# Build the graph once at module load — expensive operation, reused across calls
_graph = None


def _get_graph():
    """
    Lazy singleton — build the LangGraph graph only once.
    Avoids rebuilding the PostgreSQL checkpointer on every request.
    """
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ─────────────────────────────────────────────────────────────────────────────
# start_pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def start_pipeline(brief_id: str, initial_state: PosterState) -> str:
    """
    Start the LangGraph poster pipeline for a new brief.

    The graph runs Brief Parser → Copywriter → Designer → QA Agent
    and then STOPS at interrupt_before=["human_review"].

    At that point, the full state is serialised to PostgreSQL via the
    checkpointer. Nothing runs until resume_pipeline() is called.

    Args:
        brief_id:      Used as the LangGraph thread_id — links DB row to graph state
        initial_state: PosterState dict populated from the brief DB row

    Returns:
        thread_id (same as brief_id) — stored in poster_briefs for resume calls
    """
    graph = _get_graph()

    # thread_id is the key that identifies this specific run in the checkpointer.
    # We use the brief's UUID so we can always look up the graph state from the DB row.
    thread_config = {"configurable": {"thread_id": brief_id}}

    log.info("pipeline_starting", brief_id=brief_id)

    # ainvoke() runs the graph asynchronously.
    # It will pause automatically when it hits interrupt_before=["human_review"].
    # At that point it returns — the state is saved to PostgreSQL.
    await graph.ainvoke(initial_state, config=thread_config)

    log.info("pipeline_paused_at_hitl_gate", brief_id=brief_id)

    return brief_id


# ─────────────────────────────────────────────────────────────────────────────
# resume_pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def resume_pipeline(thread_id: str, state_update: dict) -> None:
    """
    Resume a paused LangGraph graph with the human reviewer's decision.

    Called by the review endpoints after approve / revise / reject.

    LangGraph's Command(resume=...) injects the human's decision into the
    graph state and then continues execution from the human_review node.
    The route_after_review() edge function then directs it to:
      - "approved"  → publisher_agent  → schedules posts
      - "revision"  → designer_agent   → regenerates with feedback
      - "rejected"  → END              → terminates

    Args:
        thread_id:    The brief_id / LangGraph thread_id of the paused graph
        state_update: Dict of state fields to inject, e.g.:
                      {"review_status": "approved", "reviewer_id": "...", ...}
    """
    graph = _get_graph()
    thread_config = {"configurable": {"thread_id": thread_id}}

    log.info(
        "pipeline_resuming",
        thread_id=thread_id,
        decision=state_update.get("review_status"),
    )

    # Command(resume=state_update) is LangGraph's mechanism for injecting
    # human input into an interrupted graph. It merges state_update into the
    # existing checkpointed state and continues from where execution stopped.
    await graph.ainvoke(Command(resume=state_update), config=thread_config)

    log.info("pipeline_resumed", thread_id=thread_id)


# ─────────────────────────────────────────────────────────────────────────────
# get_pipeline_status
# ─────────────────────────────────────────────────────────────────────────────

async def get_pipeline_status(thread_id: str) -> dict:
    """
    Read the current graph state from the PostgreSQL checkpointer.

    Does NOT run any agents — purely reads the saved state.
    Used by GET /poster/briefs/{brief_id} to show the current pipeline node.

    Returns:
        {
          "current_node": "qa_agent" | "human_review" | "publisher" | ...,
          "revision_count": 0 | 1 | 2 | 3,
          "review_status": "pending" | "approved" | "revision" | "rejected" | None,
          "qa_confidence": 0.0–1.0 | None,
        }
    """
    graph = _get_graph()
    thread_config = {"configurable": {"thread_id": thread_id}}

    try:
        # aget_state() reads the saved checkpoint without running the graph
        state_snapshot = await graph.aget_state(thread_config)

        if state_snapshot is None:
            return {"current_node": None, "revision_count": 0, "review_status": None}

        values = state_snapshot.values

        # next tells us which node will run when the graph is resumed
        next_nodes = list(state_snapshot.next) if state_snapshot.next else []
        current_node = next_nodes[0] if next_nodes else "completed"

        return {
            "current_node":   current_node,
            "revision_count": values.get("revision_count", 0),
            "review_status":  values.get("review_status"),
            "qa_confidence":  values.get("qa_confidence"),
        }

    except Exception as exc:
        log.warning("pipeline_status_read_failed", thread_id=thread_id, error=str(exc))
        return {"current_node": None, "revision_count": 0, "review_status": None}
