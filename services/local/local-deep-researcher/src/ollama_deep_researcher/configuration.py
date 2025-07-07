import os
from enum import Enum
from pydantic import BaseModel, Field
from typing import Any, Optional, Literal

from langchain_core.runnables import RunnableConfig

class SearchAPI(Enum):
    SEARXNG = "searxng"
    MCP = "mcp"

class Configuration(BaseModel):
    """The configurable fields for the research assistant."""

    max_web_research_loops: int = Field(
        default=3,
        title="Research Depth",
        description="Number of research iterations to perform"
    )
    local_llm: str = Field(
        default="llama3.2",
        title="LLM Model Name",
        description="Name of the LLM model to use"
    )
    llm_provider: Literal["ollama", "openai_compatible"] = Field(
        default="ollama",
        title="LLM Provider",
        description="Provider for the LLM (Ollama or OpenAI Compatible)"
    )
    search_api: Literal["searxng", "mcp"] = Field(
        default="searxng",
        title="Search API",
        description="Web search API to use (searxng includes arXiv results)"
    )
    fetch_full_page: bool = Field(
        default=True,
        title="Fetch Full Page",
        description="Include the full page content in the search results"
    )
    filter_low_reliability: bool = Field(
        default=False,
        title="Filter Low Reliability Sources",
        description="Exclude low-reliability sources (social media, forums) from search results"
    )
    min_source_reliability: Literal["Low", "Medium", "High"] = Field(
        default="Low",
        title="Minimum Source Reliability",
        description="Minimum reliability level for sources (Low=all, Medium=exclude low, High=only high)"
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434/",
        title="Ollama Base URL",
        description="Base URL for Ollama API"
    )
    openai_compatible_base_url: str = Field(
        default="http://localhost:8000/v1",
        title="OpenAI Compatible Base URL",
        description="Base URL for OpenAI-compatible API server"
    )
    openai_compatible_api_key: str = Field(
        default="EMPTY",
        title="OpenAI Compatible API Key",
        description="API key for OpenAI-compatible server (use 'EMPTY' if not required)"
    )
    strip_thinking_tokens: bool = Field(
        default=True,
        title="Strip Thinking Tokens",
        description="Whether to strip <think> tokens from model responses"
    )
    web_timeout: int = Field(
        default=30,
        title="Web Search Timeout",
        description="Timeout in seconds for web search operations"
    )
    arxiv_mcp_server_url: str = Field(
        default="http://192.168.19.61:9937",
        title="ArXiv MCP Server URL",
        description="URL for the ArXiv MCP server"
    )
    
    # Memory capture settings
    memory_enabled: bool = Field(
        default=True,
        title="Enable Memory Capture",
        description="Enable capturing research data to memory storage"
    )
    memory_mcp_server_path: str = Field(
        default="",
        title="Memory MCP Server Path",
        description="File system path to the memoer-mcp server (auto-detected if empty)"
    )
    memory_capture_level: Literal["minimal", "essential", "comprehensive"] = Field(
        default="essential",
        title="Memory Capture Level",
        description="Level of detail to capture in memories"
    )
    
    # LangGraph execution settings
    recursion_limit: int = Field(
        default=50,
        title="Recursion Limit",
        description="Maximum number of nodes to execute in the graph (prevents infinite loops)"
    )

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = (
            config["configurable"] if config and "configurable" in config else {}
        )
        
        # Get raw values from environment or config
        raw_values: dict[str, Any] = {
            name: os.environ.get(name.upper(), configurable.get(name))
            for name in cls.model_fields.keys()
        }
        
        # Filter out None values and convert string values for environment variables
        values = {}
        for k, v in raw_values.items():
            if v is not None:
                # Handle boolean conversion from environment variables
                if isinstance(v, str):
                    field = cls.model_fields.get(k)
                    if field and field.annotation in [bool, Optional[bool]]:
                        # Convert string to boolean
                        v = v.lower() in ('true', '1', 'yes', 'on', 'enabled')
                    elif field and field.annotation == int:
                        # Convert string to int
                        try:
                            v = int(v)
                        except ValueError:
                            continue  # Skip invalid int values
                values[k] = v
        
        return cls(**values)
