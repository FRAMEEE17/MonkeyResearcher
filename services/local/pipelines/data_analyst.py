"""
title: Local Deep Researcher
author: Integration Example
description: Local Deep Researcher integration with OpenWebUI using LangGraph
required_open_webui_version: 0.4.3
version: 0.1
license: MIT
requirements: langgraph>=0.2.55,langchain-community>=0.3.9,tavily-python>=0.5.0,langchain-ollama>=0.2.1,duckduckgo-search>=7.3.0,langchain-openai>=0.1.1,httpx>=0.28.1,markdownify>=0.11.0,python-dotenv==1.0.1,beautifulsoup4>=4.12.0
"""

import os
import sys
from typing import List, Union, Generator, Iterator, Optional, Callable, Awaitable, Any, AsyncGenerator
from logging import getLogger
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage
from dataclasses import asdict

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
RESEARCHER_PATH = os.environ.get(
      "LOCAL_DEEP_RESEARCHER_PATH",
      os.path.join(CURRENT_DIR, "..", "local-deep-researcher", "src")
)

try:
    if os.path.exists(RESEARCHER_PATH):
        sys.path.insert(0, RESEARCHER_PATH)
        from ollama_deep_researcher.graph import graph
        from ollama_deep_researcher.configuration import Configuration
        from ollama_deep_researcher.state import SummaryStateInput
        print("Successfully imported local-deep-researcher modules")
    else:
        print(f"Warning: Local Deep Researcher path not found: {RESEARCHER_PATH}")
        # Create dummy imports to allow pipeline to load
        graph = None
        Configuration = None
        SummaryStateInput = None
except Exception as e:
    print(f"Warning: Could not import local-deep-researcher: {e}")
    # Create dummy imports to allow pipeline to load
    graph = None
    Configuration = None
    SummaryStateInput = None

logger = getLogger(__name__)

class Pipeline:
    """
    Local Deep Researcher Pipeline for OpenWebUI
    
    This pipeline integrates the local-deep-researcher LangGraph agent with OpenWebUI,
    allowing users to perform deep web research through a conversational interface.
    """
    
    class Valves(BaseModel):
        """Configuration valves for the pipeline"""
        
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
        llm_provider: str = Field(
            default="openai_compatible",
            title="LLM Provider",
            description="Provider for the LLM (ollama or openai_compatible)"
        )
        search_api: str = Field(
            default="searxng",
            title="Search API",
            description="Web search API to use (duckduckgo, tavily, perplexity, searxng)"
        )
        fetch_full_page: bool = Field(
            default=True,
            title="Fetch Full Page",
            description="Include the full page content in the search results"
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
        # API Keys for search services
        tavily_api_key: str = Field(
            default="",
            title="Tavily API Key",
            description="API key for Tavily search service"
        )
        perplexity_api_key: str = Field(
            default="",
            title="Perplexity API Key", 
            description="API key for Perplexity search service"
        )
        searxng_url: str = Field(
            default="http://localhost:8080",
            title="SearXNG URL",
            description="URL for SearXNG search instance"
        )

    def __init__(self):
        self.name = "🐒🔬 Monkey Researcher 🌟"
        self.valves = self.Valves()
        
        # Set environment variables for the researcher
        self._update_environment()
        
        # Initialize the research graph
        self.research_graph = graph
        self.is_available = graph is not None

    def _update_environment(self):
        """Update environment variables based on valve settings"""
        if self.valves.tavily_api_key:
            os.environ["TAVILY_API_KEY"] = self.valves.tavily_api_key
        if self.valves.perplexity_api_key:
            os.environ["PERPLEXITY_API_KEY"] = self.valves.perplexity_api_key
        if self.valves.searxng_url:
            os.environ["SEARXNG_URL"] = self.valves.searxng_url

    def _extract_research_topic(self, messages: List[dict]) -> str:
        """Extract the research topic from the conversation messages"""
        # Get the last user message as the research topic
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, list):
                    # Handle multimodal content
                    for item in content:
                        if item.get("type") == "text":
                            return item.get("text", "")
                return content
        return "General research topic"

    def _create_config(self) -> dict:
        """Create configuration for the research graph"""
        return {
            "configurable": {
                "max_web_research_loops": self.valves.max_web_research_loops,
                "local_llm": self.valves.local_llm,
                "llm_provider": self.valves.llm_provider,
                "search_api": self.valves.search_api,
                "fetch_full_page": self.valves.fetch_full_page,
                "ollama_base_url": self.valves.ollama_base_url,
                "strip_thinking_tokens": self.valves.strip_thinking_tokens,
                "openai_compatible_base_url": self.valves.openai_compatible_base_url,
                "openai_compatible_api_key": self.valves.openai_compatible_api_key,
            }
        }

    async def on_startup(self):
        """Called when the pipeline starts up"""
        logger.info(f"Starting up {self.name}")
        self._update_environment()

    async def on_shutdown(self):
        """Called when the pipeline shuts down"""
        logger.info(f"Shutting down {self.name}")

    async def on_valves_updated(self):
        """Called when valve values are updated"""
        logger.info("Valves updated, updating environment")
        self._update_environment()

    def pipe(
        self, 
        user_message: str, 
        model_id: str, 
        messages: List[dict], 
        body: dict,
        __event_emitter__: Optional[Callable[[Any], Awaitable[None]]] = None
    ) -> Union[str, Generator, Iterator]:
        """
        Main pipeline function that performs deep research
        
        Args:
            user_message: The latest user message
            model_id: The model identifier 
            messages: Full conversation history
            body: Request body containing stream settings etc.
            __event_emitter__: Event emitter for status updates
            
        Returns:
            Research results as string or generator
        """
        try:
            # Check if the researcher is available
            if not self.is_available:
                return "❌ Local Deep Researcher is not available. Please check the module installation and path configuration."
            
            # Log event emitter status for debugging
            logger.info(f"Event emitter provided: {__event_emitter__ is not None}")
            if __event_emitter__:
                logger.info(f"Event emitter type: {type(__event_emitter__)}")
            
            # Extract the research topic from user input
            research_topic = self._extract_research_topic(messages)
            
            # Update environment variables
            self._update_environment()
            
            # Create the input state for the research graph
            input_state = SummaryStateInput(research_topic=research_topic)
            
            # Create configuration
            config = self._create_config()
            
            # Check if streaming is requested
            stream = body.get("stream", True)
            
            if stream:
                return self._stream_research(input_state, config, __event_emitter__)
            else:
                return self._batch_research(input_state, config, __event_emitter__)
                
        except Exception as e:
            error_msg = f"Error in Local Deep Researcher: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    def _stream_research(self, input_state: SummaryStateInput, config: dict, event_emitter: Optional[Callable[[Any], Awaitable[None]]] = None) -> Generator[str, None, None]:
        """Stream the research process with loading states via event emitter and return only final result"""
        import asyncio
        
        def run_async_event(event_data):
            """Helper to run async event emitter in sync context"""
            if event_emitter and callable(event_emitter):
                logger.info(f"Emitting event: {event_data}")
                try:
                    # Check if we're in an async context
                    try:
                        loop = asyncio.get_running_loop()
                        # If we have a running loop, create a task
                        task = loop.create_task(event_emitter(event_data))
                        logger.info("Event task created successfully")
                        # Don't await the task since we're in a sync context
                    except RuntimeError:
                        # No running loop, create a new one
                        logger.info("Creating new event loop for event emission")
                        asyncio.run(event_emitter(event_data))
                        logger.info("Event emitted successfully via new loop")
                except Exception as e:
                    logger.error(f"Could not emit event: {e}", exc_info=True)
            else:
                logger.warning("No event emitter available or not callable")
        
        try:
            # Emit initial status and yield a small status update
            run_async_event({
                "type": "status",
                "data": {
                    "description": "🚀 Starting deep research process...",
                    "done": False,
                }
            })
            yield ""  # Small yield to trigger status emission
            
            # Convert dataclass to dict for the graph
            input_dict = asdict(input_state)
            
            # Execute the graph and track status without yielding intermediate results
            for step in self.research_graph.stream(input_dict, config=config):
                for node_name, node_output in step.items():
                    current_status = ""
                    
                    if node_name == "generate_query":
                        current_status = "🔍 Generating search queries..."
                    elif node_name == "web_research":
                        research_count = node_output.get("research_loop_count", 0)
                        current_status = f"🌐 Research loop {research_count + 1}: Gathering information..."
                    elif node_name == "summarize_sources":
                        current_status = "📊 Analyzing and summarizing sources..."
                    elif node_name == "reflect_on_summary":
                        current_status = "🤔 Identifying knowledge gaps..."
                    elif node_name == "finalize_summary":
                        current_status = "✅ Finalizing research summary..."
                        # Only yield the final summary
                        if "running_summary" in node_output:
                            run_async_event({
                                "type": "status", 
                                "data": {
                                    "description": "Research complete!",
                                    "done": True,
                                }
                            })
                            yield f"# Deep Research Results\n\n**Topic:** {input_state.research_topic}\n\n{node_output['running_summary']}"
                            return
                    
                    # Update status via event emitter and yield empty string to trigger status emission
                    if current_status:
                        run_async_event({
                            "type": "status",
                            "data": {
                                "description": current_status,
                                "done": False,
                            }
                        })
                        yield ""  # Small yield to trigger status emission
            
            # Fallback if no final summary was found
            run_async_event({
                "type": "status",
                "data": {
                    "description": "✅ Research complete!",
                    "done": True,
                }
            })
            yield f"# Deep Research Results\n\n**Topic:** {input_state.research_topic}\n\nResearch completed but no summary was generated."
            
        except Exception as e:
            run_async_event({
                "type": "status",
                "data": {
                    "description": f"❌ Error during research: {str(e)}",
                    "done": True,
                }
            })
            yield f"❌ **Error during research:** {str(e)}"

    def _batch_research(self, input_state: SummaryStateInput, config: dict, event_emitter: Optional[Callable[[Any], Awaitable[None]]] = None) -> str:
        """Perform research in batch mode and return final result"""
        import asyncio
        
        def run_async_event(event_data):
            """Helper to run async event emitter in sync context"""
            if event_emitter and callable(event_emitter):
                logger.info(f"Emitting event: {event_data}")
                try:
                    # Check if we're in an async context
                    try:
                        loop = asyncio.get_running_loop()
                        # If we have a running loop, create a task
                        task = loop.create_task(event_emitter(event_data))
                        logger.info("Event task created successfully")
                        # Don't await the task since we're in a sync context
                    except RuntimeError:
                        # No running loop, create a new one
                        logger.info("Creating new event loop for event emission")
                        asyncio.run(event_emitter(event_data))
                        logger.info("Event emitted successfully via new loop")
                except Exception as e:
                    logger.error(f"Could not emit event: {e}", exc_info=True)
            else:
                logger.warning("No event emitter available or not callable")
        
        try:
            run_async_event({
                "type": "status",
                "data": {
                    "description": "🚀 Starting deep research process...",
                    "done": False,
                }
            })
            
            # Convert dataclass to dict for the graph
            input_dict = asdict(input_state)
            
            # Execute the research graph
            result = self.research_graph.invoke(input_dict, config=config)
            
            # Extract the final summary
            final_summary = result.get("running_summary", "No summary generated")
            
            run_async_event({
                "type": "status",
                "data": {
                    "description": "✅ Research complete!",
                    "done": True,
                }
            })
            
            return f"# Deep Research Results\n\n**Topic:** {input_state.research_topic}\n\n{final_summary}"
            
        except Exception as e:
            run_async_event({
                "type": "status",
                "data": {
                    "description": f"❌ Error during research: {str(e)}",
                    "done": True,
                }
            })
            return f"Error during batch research: {str(e)}"