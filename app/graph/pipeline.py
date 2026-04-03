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

def build_graph():
    builder = StateGraph(PosterState)

    # Add every agent as a node
    builder.add_node("brief_parser", brief_parser_agent)
    builder.add_node("copywriter",   copywriter_agent)
    builder.add_node("designer",     designer_agent)
    builder.add_node("qa_agent",     qa_agent)
    builder.add_node("human_review", lambda s: s)  # pause point — does nothing
    builder.add_node("publisher",    publisher_agent)

    # Fixed sequence
    builder.set_entry_point("brief_parser")
    builder.add_edge("brief_parser", "copywriter")
    builder.add_edge("copywriter",   "designer")
    builder.add_edge("designer",     "qa_agent")

    # Conditional routing
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

    # PostgreSQL checkpointer — saves state across the interrupt pause
    checkpointer = PostgresSaver.from_conn_string(
        settings.LANGGRAPH_CHECKPOINTER_URL.get_secret_value()
    )

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"]  # ← this IS the HITL gate
    )
