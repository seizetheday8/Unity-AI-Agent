from typing import List, Dict, Any
from langgraph.graph import StateGraph,END
from src.protocol import AgentResponse,ToolCall
from src.graph_state import GraphState
from src.graph_nodes import (
    retrieve_rules_node,
    plan_node,
    validate_node,
    finish_node,
)

def route_after_plan(state: GraphState):
    if state.get("plan_retryable"):
        return "plan"
    if state.get("tool_calls"):
        return "validate"
    return "finish"

def route_after_validate(state: GraphState):
    if state.get("validation_retryable"):
        return "plan"
    return "finish"

def build_graph():
    graph_builder = StateGraph(GraphState)

    graph_builder.add_node("retrieve", retrieve_rules_node)
    graph_builder.add_node("plan", plan_node)
    graph_builder.add_node("validate", validate_node)
    graph_builder.add_node("finish", finish_node)

    graph_builder.set_entry_point("retrieve")
    graph_builder.add_edge("retrieve", "plan")
    graph_builder.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "plan": "plan",
            "validate": "validate",
            "finish": "finish"
        }
    )
    graph_builder.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "plan": "plan",
            "finish": "finish"
        }
    )

    # graph_builder.add_edge("validate", "finish")
    graph_builder.add_edge("finish", END)
    return graph_builder.compile()


# 将图内状态转换为AgentResponse
def run_graph_planner(
        history_messages:List[Dict[str, Any]],
        retriever:Any,
        tools:Any,
        plan_callable:Any
):
    graph = build_graph()

    initial_state:GraphState = {
        "messages": history_messages,
        "retriever": retriever,
        "tools": tools,
        "plan_callable": plan_callable,
        "metrics": {},
        "llm_retry_count": 0,
        "llm_retry_limit": 3,
        "validation_retry_count": 0,
        "validation_retry_limit": 3,
        "plan_retryable": False,
        "validation_retryable": False,
    }
    final_state = graph.invoke(initial_state)
    metrics = final_state.get("metrics", {})

    if final_state.get("error"):
        raise RuntimeError(final_state["error"])

    raw_tool_calls = final_state.get("tool_calls", [])
    tool_calls = [ToolCall.model_validate(tool_call) for tool_call in raw_tool_calls]

    return AgentResponse(
        thoughts=final_state.get("thoughts", ""),
        content=final_state.get("final_content", ""),
        tool_calls=tool_calls,
    ),metrics