"""
Tool Manager for Dynamic Tool Loading and Execution

Based on OpenWebUI's tool integration patterns, this module provides
dynamic tool loading, execution, and management for the research pipeline.
Now integrates with OpenWebUI tool servers including ArXiv MCP server.
"""

import json
import asyncio
import aiohttp
import importlib.util
import tempfile
import os
import sys
import inspect
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass
from enum import Enum
import logging

# Import OpenWebUI integration
try:
    from .openwebui_integration import (
        openwebui_integration,
        register_arxiv_mcp_server,
        get_available_tools as get_openwebui_tools,
        get_tool_specs_for_llm as get_openwebui_specs,
        execute_tool as execute_openwebui_tool
    )
except ImportError:
    # Fallback for direct execution
    from openwebui_integration import (
        openwebui_integration,
        register_arxiv_mcp_server,
        get_available_tools as get_openwebui_tools,
        get_tool_specs_for_llm as get_openwebui_specs,
        execute_tool as execute_openwebui_tool
    )

logger = logging.getLogger(__name__)

class ToolType(Enum):
    """Tool Types based on OpenWebUI patterns"""
    FUNCTION = "function"
    EXTERNAL_API = "external_api"
    MCP_TOOL = "mcp_tool"
    PYTHON_MODULE = "python_module"
    OPENWEBUI_SERVER = "openwebui_server"  # New type for OpenWebUI tool servers

@dataclass
class ToolSpec:
    """Tool Specification following OpenAI function calling format"""
    name: str
    description: str
    parameters: Dict[str, Any]
    tool_type: ToolType
    source: Optional[str] = None  # Source code for Python modules
    url: Optional[str] = None     # URL for external APIs
    auth: Optional[Dict[str, str]] = None  # Authentication info

@dataclass
class ToolExecution:
    """Tool Execution Result"""
    success: bool
    result: Any
    error: Optional[str] = None
    execution_time: Optional[float] = None

class ToolManager:
    """
    Dynamic Tool Manager for Research Pipeline
    
    Based on OpenWebUI's tool patterns, this manager handles:
    - Dynamic Python module loading from code strings
    - External API tool integration
    - MCP tool management
    - Tool discovery and specification parsing
    - Secure tool execution with error handling
    """
    
    def __init__(self):
        self.tools: Dict[str, ToolSpec] = {}
        self.loaded_modules: Dict[str, Any] = {}
        self.external_clients: Dict[str, Any] = {}
        self.openwebui_initialized = False
        
    def register_tool(self, tool_spec: ToolSpec):
        """Register a new tool"""
        self.tools[tool_spec.name] = tool_spec
        logger.info(f"Registered tool: {tool_spec.name} ({tool_spec.tool_type.value})")
        
    def get_available_tools(self) -> List[str]:
        """Get list of available tool names"""
        local_tools = list(self.tools.keys())
        
        # Add OpenWebUI server tools if initialized
        if self.openwebui_initialized:
            try:
                # Check if we're already in an event loop
                try:
                    loop = asyncio.get_running_loop()
                    # We're in an event loop, so we can't use asyncio.run()
                    # Instead, get tools synchronously from the integration
                    openwebui_tools = openwebui_integration.get_available_tools()
                    return local_tools + openwebui_tools
                except RuntimeError:
                    # No event loop running, safe to use asyncio.run()
                    openwebui_tools = asyncio.run(get_openwebui_tools())
                    return local_tools + openwebui_tools
            except Exception as e:
                logger.warning(f"Failed to get OpenWebUI tools: {str(e)}")
                
        return local_tools
        
    def get_tool_spec(self, tool_name: str) -> Optional[ToolSpec]:
        """Get tool specification"""
        return self.tools.get(tool_name)
        
    def get_tools_by_type(self, tool_type: ToolType) -> List[ToolSpec]:
        """Get tools filtered by type"""
        return [tool for tool in self.tools.values() if tool.tool_type == tool_type]
        
    def load_python_tool(self, tool_name: str, source_code: str) -> bool:
        """
        Load Python tool from source code
        Based on OpenWebUI's dynamic module loading
        """
        try:
            # Create temporary module file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(source_code)
                temp_file = f.name
            
            # Load module dynamically
            spec = importlib.util.spec_from_file_location(f"tool_{tool_name}", temp_file)
            module = importlib.util.module_from_spec(spec)
            
            # Execute module
            spec.loader.exec_module(module)
            
            # Store loaded module
            self.loaded_modules[tool_name] = module
            
            # Clean up temp file
            os.unlink(temp_file)
            
            # Extract tool specifications from module
            self._extract_tool_specs_from_module(tool_name, module)
            
            logger.info(f"Successfully loaded Python tool: {tool_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load Python tool {tool_name}: {str(e)}")
            return False
            
    def _extract_tool_specs_from_module(self, tool_name: str, module: Any):
        """Extract tool specifications from loaded Python module"""
        try:
            # Look for functions with tool decorators or specific naming patterns
            for name, obj in inspect.getmembers(module):
                if inspect.isfunction(obj) and not name.startswith('_'):
                    # Extract function signature and docstring
                    sig = inspect.signature(obj)
                    doc = inspect.getdoc(obj) or f"Function {name} from {tool_name}"
                    
                    # Convert to OpenAI function spec format
                    parameters = {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                    
                    for param_name, param in sig.parameters.items():
                        param_type = "string"  # Default type
                        if param.annotation != inspect.Parameter.empty:
                            if param.annotation == int:
                                param_type = "integer"
                            elif param.annotation == float:
                                param_type = "number"
                            elif param.annotation == bool:
                                param_type = "boolean"
                            elif param.annotation == list:
                                param_type = "array"
                        
                        parameters["properties"][param_name] = {
                            "type": param_type,
                            "description": f"Parameter {param_name}"
                        }
                        
                        if param.default == inspect.Parameter.empty:
                            parameters["required"].append(param_name)
                    
                    # Register function as tool
                    func_tool_spec = ToolSpec(
                        name=f"{tool_name}_{name}",
                        description=doc,
                        parameters=parameters,
                        tool_type=ToolType.PYTHON_MODULE,
                        source=f"{tool_name}.{name}"
                    )
                    
                    self.register_tool(func_tool_spec)
                    
        except Exception as e:
            logger.error(f"Failed to extract tool specs from module {tool_name}: {str(e)}")
            
    async def register_external_api_tool(self, tool_name: str, api_url: str, openapi_spec: Optional[Dict] = None, auth: Optional[Dict] = None):
        """
        Register external API tool
        Based on OpenWebUI's external tool server integration
        """
        try:
            if openapi_spec:
                # Parse OpenAPI specification
                for path, methods in openapi_spec.get("paths", {}).items():
                    for method, spec in methods.items():
                        operation_id = spec.get("operationId", f"{method}_{path.replace('/', '_')}")
                        
                        tool_spec = ToolSpec(
                            name=f"{tool_name}_{operation_id}",
                            description=spec.get("description", f"API call to {path}"),
                            parameters=self._convert_openapi_to_function_params(spec.get("parameters", [])),
                            tool_type=ToolType.EXTERNAL_API,
                            url=f"{api_url}{path}",
                            auth=auth
                        )
                        
                        self.register_tool(tool_spec)
            else:
                # Simple API tool registration
                tool_spec = ToolSpec(
                    name=tool_name,
                    description=f"External API tool: {tool_name}",
                    parameters={
                        "type": "object",
                        "properties": {
                            "endpoint": {"type": "string", "description": "API endpoint path"},
                            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "default": "GET"},
                            "data": {"type": "object", "description": "Request data"}
                        },
                        "required": ["endpoint"]
                    },
                    tool_type=ToolType.EXTERNAL_API,
                    url=api_url,
                    auth=auth
                )
                
                self.register_tool(tool_spec)
                
            logger.info(f"Registered external API tool: {tool_name}")
            
        except Exception as e:
            logger.error(f"Failed to register external API tool {tool_name}: {str(e)}")
            
    def _convert_openapi_to_function_params(self, openapi_params: List[Dict]) -> Dict[str, Any]:
        """Convert OpenAPI parameters to function calling format"""
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        for param in openapi_params:
            param_name = param.get("name")
            param_schema = param.get("schema", {})
            
            parameters["properties"][param_name] = {
                "type": param_schema.get("type", "string"),
                "description": param.get("description", "")
            }
            
            if param.get("required", False):
                parameters["required"].append(param_name)
                
        return parameters
        
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolExecution:
        """
        Execute a tool with given parameters
        Based on OpenWebUI's tool execution patterns
        """
        import time
        start_time = time.time()
        
        try:
            tool_spec = self.get_tool_spec(tool_name)
            
            # If tool not found locally, try OpenWebUI server tools
            if not tool_spec and self.openwebui_initialized:
                try:
                    result = await execute_openwebui_tool(tool_name, parameters)
                    execution_time = time.time() - start_time
                    
                    # Add source links for ArXiv papers
                    if tool_name == "arxiv_search" and isinstance(result, dict) and "papers" in result:
                        sources = []
                        for paper in result["papers"]:
                            if "url" in paper:
                                sources.append({
                                    "title": paper.get("title", "ArXiv Paper"),
                                    "url": paper["url"],
                                    "type": "arxiv"
                                })
                        result["sources"] = sources
                    
                    return ToolExecution(
                        success=True,
                        result=result,
                        execution_time=execution_time
                    )
                except RuntimeError as e:
                    error_msg = str(e).lower()
                    if any(keyword in error_msg for keyword in ["event loop", "cannot write", "connection", "closed"]):
                        logger.warning(f"Skipping {tool_name} execution - event loop/connection issue: {str(e)}")
                        return ToolExecution(
                            success=False,
                            result=None,
                            error=f"Event loop/connection issue - skipping execution: {str(e)}",
                            execution_time=time.time() - start_time
                        )
                    else:
                        logger.error(f"OpenWebUI tool execution failed: {str(e)}")
                        # Continue to local tool execution error
                except Exception as e:
                    logger.error(f"OpenWebUI tool execution failed: {str(e)}")
                    # Continue to local tool execution error
                    
            if not tool_spec:
                return ToolExecution(
                    success=False,
                    result=None,
                    error=f"Tool '{tool_name}' not found"
                )
                
            # Execute based on tool type
            if tool_spec.tool_type == ToolType.PYTHON_MODULE:
                result = await self._execute_python_tool(tool_name, parameters)
            elif tool_spec.tool_type == ToolType.EXTERNAL_API:
                result = await self._execute_external_api_tool(tool_spec, parameters)
            elif tool_spec.tool_type == ToolType.MCP_TOOL:
                result = await self._execute_mcp_tool(tool_spec, parameters)
            elif tool_spec.tool_type == ToolType.FUNCTION:
                # Handle built-in function tools (web_search, etc.)
                result = await self._execute_python_tool(tool_name, parameters)
            elif tool_spec.tool_type == ToolType.OPENWEBUI_SERVER:
                # Handle OpenWebUI server tools - delegate to OpenWebUI integration
                if self.openwebui_initialized:
                    # Map to the actual server tool name
                    server_tool_name = "server:0_tool_search_papers_post"  # Default to search
                    result = await execute_openwebui_tool(server_tool_name, parameters)
                else:
                    return ToolExecution(
                        success=False,
                        result=None,
                        error=f"OpenWebUI integration not initialized for tool: {tool_name}"
                    )
            else:
                return ToolExecution(
                    success=False,
                    result=None,
                    error=f"Unsupported tool type: {tool_spec.tool_type}"
                )
                
            execution_time = time.time() - start_time
            
            return ToolExecution(
                success=True,
                result=result,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Tool execution failed for {tool_name}: {str(e)}")
            
            return ToolExecution(
                success=False,
                result=None,
                error=str(e),
                execution_time=execution_time
            )
            
    async def _execute_python_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Execute Python module tool or built-in function tool"""
        tool_spec = self.get_tool_spec(tool_name)
        if not tool_spec:
            raise ValueError(f"Tool not found: {tool_name}")
            
        # Handle built-in function tools
        if tool_name == "web_search":
            return await self._execute_web_search_tool(parameters)
        elif tool_name == "fetch_url_content":
            return await self._execute_url_fetch_tool(parameters)
        elif tool_name == "arxiv_search":
            return await self._execute_arxiv_search_tool(parameters)
        
        # Handle loaded Python module tools
        if tool_spec.source:
            module_name, func_name = tool_spec.source.split('.', 1)
            
            if module_name not in self.loaded_modules:
                raise ValueError(f"Module not loaded: {module_name}")
                
            module = self.loaded_modules[module_name]
            func = getattr(module, func_name, None)
            
            if not func:
                raise ValueError(f"Function not found: {func_name}")
                
            # Execute function
            if asyncio.iscoroutinefunction(func):
                return await func(**parameters)
            else:
                return func(**parameters)
        else:
            raise ValueError(f"No execution method found for tool: {tool_name}")
            
    async def _execute_web_search_tool(self, parameters: Dict[str, Any]) -> Any:
        """Execute web search tool"""
        try:
            from ollama_deep_researcher.utils import web_search_only
        except ImportError:
            from utils import web_search_only
        
        query = parameters.get("query", "")
        max_results = parameters.get("max_results", 5)
        search_engine = parameters.get("search_engine", "google")
        
        results = web_search_only(query, max_results)
        return {
            "query": query,
            "results_count": len(results.get("results", [])),
            "results": results.get("results", [])[:max_results]
        }
        
    async def _execute_url_fetch_tool(self, parameters: Dict[str, Any]) -> Any:
        """Execute URL content fetch tool"""
        try:
            from ollama_deep_researcher.utils import fetch_url_content_directly
        except ImportError:
            from utils import fetch_url_content_directly
        
        url = parameters.get("url", "")
        format_type = parameters.get("format", "markdown")
        
        content = fetch_url_content_directly(url)
        if content:
            return {
                "url": url,
                "title": content.get("title", ""),
                "content": content.get("content", "")[:2000] + "..." if len(content.get("content", "")) > 2000 else content.get("content", ""),
                "format": format_type
            }
        else:
            return {"error": f"Failed to fetch content from {url}"}
            
    async def _execute_arxiv_search_tool(self, parameters: Dict[str, Any]) -> Any:
        """Execute ArXiv search tool via MCP"""
        try:
            from ollama_deep_researcher.utils import mcp_search
        except ImportError:
            from utils import mcp_search
        
        query = parameters.get("query", "")
        max_results = parameters.get("max_results", 10)
        categories = parameters.get("categories", [])
        
        # Use the existing MCP search function
        results = await mcp_search(
            query=query,
            max_results=max_results,
            server_url="http://192.168.19.61:9937",
            categories=categories
        )
        
        papers = results.get("results", [])[:max_results]
        
        # Add source links for ArXiv papers
        sources = []
        for paper in papers:
            if "url" in paper:
                sources.append({
                    "title": paper.get("title", "ArXiv Paper"),
                    "url": paper["url"],
                    "type": "arxiv"
                })
        
        return {
            "query": query,
            "results_count": len(papers),
            "papers": papers,
            "sources": sources
        }
            
    async def _execute_external_api_tool(self, tool_spec: ToolSpec, parameters: Dict[str, Any]) -> Any:
        """Execute external API tool"""
        if not tool_spec.url:
            raise ValueError("External API tool missing URL")
            
        # Prepare request
        method = parameters.pop("method", "GET")
        endpoint = parameters.pop("endpoint", "")
        data = parameters.pop("data", parameters)  # Use remaining params as data
        
        url = f"{tool_spec.url.rstrip('/')}/{endpoint.lstrip('/')}" if endpoint else tool_spec.url
        
        # Prepare headers
        headers = {"Content-Type": "application/json"}
        if tool_spec.auth:
            if "bearer_token" in tool_spec.auth:
                headers["Authorization"] = f"Bearer {tool_spec.auth['bearer_token']}"
            elif "api_key" in tool_spec.auth:
                headers["X-API-Key"] = tool_spec.auth["api_key"]
                
        # Execute request
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=method,
                url=url,
                headers=headers,
                json=data if method in ["POST", "PUT", "PATCH"] else None,
                params=data if method == "GET" else None
            ) as response:
                if response.status >= 400:
                    raise RuntimeError(f"API request failed: {response.status}")
                
                return await response.json()
                
    async def _execute_mcp_tool(self, tool_spec: ToolSpec, parameters: Dict[str, Any]) -> Any:
        """Execute MCP tool"""
        # Import MCP client here to avoid circular imports
        try:
            from ollama_deep_researcher.mcp_client import create_mcp_client
        except ImportError:
            from mcp_client import create_mcp_client
        
        if not tool_spec.url:
            raise ValueError("MCP tool missing server URL")
            
        # Fix: await the coroutine first, then use as context manager
        client = await create_mcp_client(tool_spec.url)
        async with client:
            return await client.call_tool(tool_spec.name, parameters)
            
    def get_tools_for_llm(self) -> List[Dict[str, Any]]:
        """
        Get tools formatted for LLM function calling
        Returns OpenAI function calling format
        """
        tools = []
        
        # Add local tools
        for tool_name, tool_spec in self.tools.items():
            tool_def = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_spec.description,
                    "parameters": tool_spec.parameters
                }
            }
            tools.append(tool_def)
        
        # Add OpenWebUI server tools if initialized
        if self.openwebui_initialized:
            try:
                # Check if we're already in an event loop
                try:
                    loop = asyncio.get_running_loop()
                    # We're in an event loop, get tools synchronously
                    openwebui_tools = openwebui_integration.get_tool_specs_for_llm()
                    tools.extend(openwebui_tools)
                except RuntimeError:
                    # No event loop running, safe to use asyncio.run()
                    openwebui_tools = asyncio.run(get_openwebui_specs())
                    tools.extend(openwebui_tools)
            except Exception as e:
                logger.warning(f"Failed to get OpenWebUI tool specs: {str(e)}")
                
        return tools
        
    async def initialize_openwebui_integration(self, arxiv_server_url: str = "http://192.168.19.61:9937"):
        """
        Initialize OpenWebUI integration with ArXiv MCP server
        
        Args:
            arxiv_server_url: URL of the ArXiv MCP server
        """
        try:
            success = await register_arxiv_mcp_server(arxiv_server_url)
            if success:
                self.openwebui_initialized = True
                logger.info("OpenWebUI integration initialized successfully")
            else:
                logger.error("Failed to initialize OpenWebUI integration")
        except Exception as e:
            logger.error(f"Error initializing OpenWebUI integration: {str(e)}")
    
    def load_default_research_tools(self):
        """Load default research tools for the pipeline"""
        # Web search tool
        web_search_spec = ToolSpec(
            name="web_search",
            description="Search the web for information using various search engines",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Maximum number of results", "default": 5},
                    "search_engine": {"type": "string", "enum": ["google", "bing", "duckduckgo"], "default": "google"}
                },
                "required": ["query"]
            },
            tool_type=ToolType.FUNCTION
        )
        self.register_tool(web_search_spec)
        
        # URL content fetcher
        url_fetch_spec = ToolSpec(
            name="fetch_url_content",
            description="Fetch and extract content from a URL",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch content from"},
                    "format": {"type": "string", "enum": ["text", "markdown", "html"], "default": "markdown"}
                },
                "required": ["url"]
            },
            tool_type=ToolType.FUNCTION
        )
        self.register_tool(url_fetch_spec)
        
        # ArXiv paper search (OpenWebUI Server Tool)
        # Note: This will be handled by OpenWebUI integration if initialized
        # Keep local fallback for compatibility
        arxiv_search_spec = ToolSpec(
            name="arxiv_search",
            description="Search for academic papers on ArXiv using OpenWebUI server tools",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for papers"},
                    "max_results": {"type": "integer", "description": "Maximum number of results", "default": 10},
                    "categories": {"type": "array", "items": {"type": "string"}, "description": "ArXiv categories to search"}
                },
                "required": ["query"]
            },
            tool_type=ToolType.OPENWEBUI_SERVER,  # Use the new server type
            url="http://192.168.19.61:9937"
        )
        self.register_tool(arxiv_search_spec)

# Global tool manager instance
tool_manager = ToolManager()

# Initialize with default tools
tool_manager.load_default_research_tools()

# Utility functions for integration

def get_available_tools() -> List[str]:
    """Get list of available tools"""
    return tool_manager.get_available_tools()

def get_tools_for_llm() -> List[Dict[str, Any]]:
    """Get tools formatted for LLM function calling"""
    return tool_manager.get_tools_for_llm()

async def execute_tool_call(tool_name: str, parameters: Dict[str, Any]) -> ToolExecution:
    """Execute a tool call"""
    return await tool_manager.execute_tool(tool_name, parameters)

def register_custom_tool(tool_spec: ToolSpec):
    """Register a custom tool"""
    tool_manager.register_tool(tool_spec)

async def load_tool_from_code(tool_name: str, source_code: str) -> bool:
    """Load a tool from Python source code"""
    return tool_manager.load_python_tool(tool_name, source_code)

async def initialize_openwebui_tools(arxiv_server_url: str = "http://192.168.19.61:9937") -> bool:
    """Initialize OpenWebUI integration with ArXiv MCP server"""
    await tool_manager.initialize_openwebui_integration(arxiv_server_url)
    return tool_manager.openwebui_initialized

def is_openwebui_initialized() -> bool:
    """Check if OpenWebUI integration is initialized"""
    return tool_manager.openwebui_initialized