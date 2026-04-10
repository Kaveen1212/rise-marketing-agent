from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from app.graph.state import PosterState
from app.graph.edges import route_after_qa, route_after_review
from app.agents.brief_parser import brief_parser_agent
from app.agents.copywriter import copywriter_agent
from app.agents.designer import designer_agent
from app.agents.qa_agent import qa_agent
from app.agents.publisher import publisher_agent
from app.config import settings

import psycopg
import structlog

log = structlog.get_logger()


def _get_checkpointer_url() -> str:
    """
    Convert the SQLAlchemy-style URL to a plain PostgreSQL URL for psycopg.
    PostgresSaver uses psycopg (v3) which expects postgresql://
    """
    url = settings.LANGGRAPH_CHECKPOINTER_URL.get_secret_value()
    url = url.replace("postgresql+psycopg2://", "postgresql://")
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    return url


# Module-level persistent connection for the checkpointer
_conn: psycopg.Connection | None = None
_graph = None


def _get_connection() -> psycopg.Connection:
    """Get or create a persistent psycopg v3 connection."""
    global _conn
    if _conn is None or _conn.closed:
        conn_string = _get_checkpointer_url()
        _conn = psycopg.connect(conn_string, autocommit=True)
    return _conn


def build_graph():
    """Build the compiled graph with PostgreSQL checkpointer (sync)."""
    global _graph
    if _graph is not None:
        return _graph

    builder = StateGraph(PosterState)

    builder.add_node("brief_parser", brief_parser_agent)
    builder.add_node("copywriter",   copywriter_agent)
    builder.add_node("designer",     designer_agent)
    builder.add_node("qa_agent",     qa_agent)
    builder.add_node("human_review", lambda s: s)
    builder.add_node("publisher",    publisher_agent)

    builder.set_entry_point("brief_parser")
    builder.add_edge("brief_parser", "copywriter")
    builder.add_edge("copywriter",   "designer")
    builder.add_edge("designer",     "qa_agent")

    builder.add_conditional_edges("qa_agent", route_after_qa, {
        "regenerate":   "designer",
        "human_review": "human_review",
    })
    builder.add_conditional_edges("human_review", route_after_review, {
        "approved": "publisher",
        "revision": "designer",
        "rejected": END,
    })
    builder.add_edge("publisher", END)

    conn = _get_connection()
    checkpointer = PostgresSaver(conn)

    try:
        checkpointer.setup()
        log.info("langgraph_checkpointer_ready")
    except Exception as exc:
        log.warning("checkpointer_setup_warning", error=str(exc))

    _graph = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"]
    )
    return _graph
