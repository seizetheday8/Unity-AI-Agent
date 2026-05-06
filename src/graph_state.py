from typing import TypedDict,List,Dict,Any,Optional

class GraphState(TypedDict,total=False):
    messages:List[Dict[str, Any]]
    project_rules_context: str
    tool_calls:list[Dict[str, Any]]
    tools:Dict[str, Any]
    plan_callable:Any
    cached_tool_sequence:List[str]
    instruction_signature:str
    thoughts:str
    retriever:Any
    final_content:str

    error:str
    last_error:str

    metrics:Dict[str, Any]

    llm_retry_count:int
    llm_retry_limit:int
    validation_retry_count:int
    validation_retry_limit:int

    feedback_messages:List[Dict[str, Any]]

    plan_retryable:bool
    validation_retryable:bool
