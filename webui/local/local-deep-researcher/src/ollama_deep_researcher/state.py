import operator
from dataclasses import dataclass, field
from typing_extensions import Annotated

@dataclass(kw_only=True)
class SummaryState:
    research_topic: str = field(default=None) # Report topic     
    input_analysis: dict = field(default_factory=dict) # User input analysis results
    search_strategy: str = field(default="web_search") # Search strategy: web_search, arxiv_search, hybrid_search
    search_query: str = field(default=None) # Search query
    web_research_results: Annotated[list, operator.add] = field(default_factory=list) 
    sources_gathered: Annotated[list, operator.add] = field(default_factory=list) 
    research_loop_count: int = field(default=0) # Research loop count
    running_summary: str = field(default=None) # Final report
    verification_questions: Annotated[list, operator.add] = field(default_factory=list) # Chain of verification questions
    verification_results: Annotated[list, operator.add] = field(default_factory=list) # Chain of verification answers
    intent_result: dict = field(default_factory=dict) # Intent classification results from enhanced classifier
    tool_results: Annotated[list, operator.add] = field(default_factory=list) # Tool execution results
    enhanced_context: str = field(default="") # Enhanced context from tool usage

@dataclass(kw_only=True)
class SummaryStateInput:
    research_topic: str = field(default=None) # Report topic     

@dataclass(kw_only=True)
class SummaryStateOutput:
    running_summary: str = field(default=None) # Final report