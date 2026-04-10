"""
app/services/pipeline_service.py
Manages starting and resuming the LangGraph poster pipeline.

The graph uses a sync PostgreSQL checkpointer (psycopg v3) because
Windows doesn't support async psycopg with ProactorEventLoop.
Graph invocations run in a thread pool so they don't block FastAPI.
"""

import asyncio
import structlog
from functools import partial
from langgraph.types import Command

from app.graph.pipeline import build_graph
from app.graph.state import PosterState

log = structlog.get_logger()


def _run_sync(func, *args, **kwargs):
    """Run a sync function — used when already in sync context."""
    return func(*args, **kwargs)


async def start_pipeline(brief_id: str, initial_state: PosterState) -> str:
    """
    Start the LangGraph poster pipeline for a new brief.

    Runs Brief Parser -> Copywriter -> Designer -> QA Agent
    then STOPS at interrupt_before=["human_review"].
    """
    graph = build_graph()
    thread_config = {"configurable": {"thread_id": brief_id}}

    log.info("pipeline_starting", brief_id=brief_id)

    # Run sync graph.invoke() in a thread pool to avoid blocking the event loop
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        partial(graph.invoke, initial_state, config=thread_config),
    )

    log.info("pipeline_paused_at_hitl_gate", brief_id=brief_id)
    return brief_id


async def resume_pipeline(thread_id: str, state_update: dict) -> None:
    """
    Resume a paused LangGraph graph with the human reviewer's decision.
    """
    graph = build_graph()
    thread_config = {"configurable": {"thread_id": thread_id}}

    log.info(
        "pipeline_resuming",
        thread_id=thread_id,
        decision=state_update.get("review_status"),
    )

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        partial(graph.invoke, Command(resume=state_update), config=thread_config),
    )

    log.info("pipeline_resumed", thread_id=thread_id)


async def get_pipeline_status(thread_id: str) -> dict:
    """
    Read the current graph state from the PostgreSQL checkpointer.
    Does NOT run any agents — purely reads the saved state.
    """
    graph = build_graph()
    thread_config = {"configurable": {"thread_id": thread_id}}

    try:
        state_snapshot = graph.get_state(thread_config)

        if state_snapshot is None:
            return {"current_node": None, "revision_count": 0, "review_status": None}

        values = state_snapshot.values
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
