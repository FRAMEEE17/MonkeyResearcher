"""
OpenWebUI Tool Integration Module

This module implements OpenWebUI's tool integration patterns for the deep research pipeline,
enabling seamless integration with OpenWebUI tool servers including the ArXiv MCP server.
"""

import json
import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import time
import re

logger = logging.getLogger(__name__)

@dataclass
class ToolServerConfig:
    """Tool Server Configuration based on OpenWebUI patterns"""
    url: str
    name: str
    auth_type: str = "bearer"  # "bearer" or "session"
    auth_token: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3
    enabled: bool = True
    access_control: Optional[Dict[str, Any]] = None

@dataclass
class ToolServerData:
    """Tool Server Data structure matching OpenWebUI format"""
    idx: int
    name: str
    url: str
    openapi: Dict[str, Any]
    auth: Dict[str, Any]
    config: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ToolSpec:
    """Tool Specification in OpenAI function format"""
    type: str = "function"
    function: Dict[str, Any] = field(default_factory=dict)

class OpenWebUIToolIntegration:
    """
    OpenWebUI Tool Integration Manager
    
    Implements OpenWebUI's tool server integration patterns for:
    - Tool server discovery and connection
    - OpenAPI specification processing
    - Dynamic function creation and execution
    - Authentication and session management
    """
    
    def __init__(self):
        self.tool_servers: Dict[str, ToolServerData] = {}
        self.tool_functions: Dict[str, Callable] = {}
        self.tool_specs: Dict[str, ToolSpec] = {}
        self.sessions: Dict[str, aiohttp.ClientSession] = {}
        
    async def register_tool_server(self, server_config: ToolServerConfig) -> bool:
        """
        Register a tool server using OpenWebUI patterns
        
        Args:
            server_config: Tool server configuration
            
        Returns:
            True if registration successful, False otherwise
        """
        try:
            # Create server data structure
            server_data = await self._get_tool_server_data(server_config)
            
            if server_data:
                server_idx = len(self.tool_servers)
                server_data.idx = server_idx
                self.tool_servers[f"server:{server_idx}"] = server_data
                
                # Create dynamic functions for each tool
                await self._create_tool_functions(server_data)
                
                logger.info(f"Successfully registered tool server: {server_config.name}")
                return True
            else:
                logger.error(f"Failed to get tool server data for: {server_config.name}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to register tool server {server_config.name}: {str(e)}")
            return False
    
    async def _get_tool_server_data(self, config: ToolServerConfig) -> Optional[ToolServerData]:
        """
        Get tool server data from OpenAPI endpoint
        Based on OpenWebUI's get_tool_server_data function
        """
        try:
            # Create session for this server
            timeout = aiohttp.ClientTimeout(total=config.timeout)
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'DeepResearcher-OpenWebUI/1.0'
            }
            
            # Add authentication
            if config.auth_type == "bearer" and config.auth_token:
                headers['Authorization'] = f'Bearer {config.auth_token}'
            elif config.auth_type == "session" and config.auth_token:
                headers['X-Session-Token'] = config.auth_token
            
            session = aiohttp.ClientSession(timeout=timeout, headers=headers)
            
            # Try to get OpenAPI spec
            # For ArXiv MCP server, use the specific server path
            if "arxiv" in config.name.lower():
                openapi_url = f"{config.url.rstrip('/')}/arxiv-mcp-server/openapi.json"
            else:
                openapi_url = f"{config.url.rstrip('/')}/openapi.json"
            
            async with session.get(openapi_url) as response:
                if response.status == 200:
                    openapi_spec = await response.json()
                    
                    # Store session for later use
                    self.sessions[config.name] = session
                    
                    return ToolServerData(
                        idx=0,  # Will be set by caller
                        name=config.name,
                        url=config.url,
                        openapi=openapi_spec,
                        auth={
                            "type": config.auth_type,
                            "token": config.auth_token
                        },
                        config={
                            "timeout": config.timeout,
                            "max_retries": config.max_retries,
                            "access_control": config.access_control
                        }
                    )
                else:
                    logger.error(f"Failed to fetch OpenAPI spec from {openapi_url}: {response.status}")
                    await session.close()
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting tool server data: {str(e)}")
            if 'session' in locals():
                await session.close()
            return None
    
    async def _create_tool_functions(self, server_data: ToolServerData):
        """
        Create dynamic tool functions from OpenAPI specification
        Based on OpenWebUI's tool creation patterns
        """
        try:
            openapi_spec = server_data.openapi
            
            # Convert OpenAPI spec to tool specifications
            tool_specs = self._convert_openapi_to_tool_payload(openapi_spec)
            
            # Create functions for each tool
            for spec in tool_specs:
                function_name = spec.function["name"]
                server_key = f"server:{server_data.idx}"
                
                # Create dynamic function
                tool_function = self._make_tool_function(
                    function_name,
                    server_data.auth.get("token"),
                    server_data
                )
                
                # Store function and spec
                self.tool_functions[f"{server_key}_{function_name}"] = tool_function
                self.tool_specs[f"{server_key}_{function_name}"] = spec
                
                logger.info(f"Created tool function: {function_name}")
                
        except Exception as e:
            logger.error(f"Failed to create tool functions: {str(e)}")
    
    def _convert_openapi_to_tool_payload(self, openapi_spec: Dict[str, Any]) -> List[ToolSpec]:
        """
        Convert OpenAPI specification to OpenAI function format
        Based on OpenWebUI's convert_openapi_to_tool_payload function
        """
        tools = []
        
        try:
            paths = openapi_spec.get("paths", {})
            
            for path, path_spec in paths.items():
                for method, operation in path_spec.items():
                    if method.lower() not in ["get", "post", "put", "delete", "patch"]:
                        continue
                    
                    # Extract operation details
                    operation_id = operation.get("operationId", f"{method}_{path.replace('/', '_')}")
                    description = operation.get("description", operation.get("summary", ""))
                    
                    # Build parameters schema
                    parameters = {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                    
                    # Add path parameters
                    if "parameters" in operation:
                        for param in operation["parameters"]:
                            param_name = param.get("name")
                            param_schema = param.get("schema", {})
                            param_required = param.get("required", False)
                            
                            parameters["properties"][param_name] = {
                                "type": param_schema.get("type", "string"),
                                "description": param.get("description", "")
                            }
                            
                            if param_required:
                                parameters["required"].append(param_name)
                    
                    # Add request body parameters for POST/PUT
                    if method.lower() in ["post", "put", "patch"]:
                        request_body = operation.get("requestBody", {})
                        content = request_body.get("content", {})
                        
                        if "application/json" in content:
                            schema = content["application/json"].get("schema", {})
                            
                            # Handle direct schema properties
                            if "properties" in schema:
                                parameters["properties"].update(schema["properties"])
                                parameters["required"].extend(schema.get("required", []))
                            
                            # Handle schema references ($ref)
                            elif "$ref" in schema:
                                ref_path = schema["$ref"]
                                # Extract schema from components (e.g., #/components/schemas/search_papers_form_model)
                                if ref_path.startswith("#/components/schemas/"):
                                    schema_name = ref_path.split("/")[-1]
                                    components = openapi_spec.get("components", {})
                                    schemas = components.get("schemas", {})
                                    
                                    if schema_name in schemas:
                                        ref_schema = schemas[schema_name]
                                        if "properties" in ref_schema:
                                            parameters["properties"].update(ref_schema["properties"])
                                            parameters["required"].extend(ref_schema.get("required", []))
                    
                    # Create tool specification
                    tool_spec = ToolSpec(
                        type="function",
                        function={
                            "name": operation_id,
                            "description": description,
                            "parameters": parameters
                        }
                    )
                    
                    tools.append(tool_spec)
                    
        except Exception as e:
            logger.error(f"Failed to convert OpenAPI to tool payload: {str(e)}")
            
        return tools
    
    def _make_tool_function(self, function_name: str, token: Optional[str], server_data: ToolServerData) -> Callable:
        """
        Create dynamic tool function
        Based on OpenWebUI's make_tool_function
        """
        async def tool_function(**kwargs):
            return await self._execute_tool_server(function_name, token, server_data, kwargs)
        
        tool_function.__name__ = function_name
        return tool_function
    
    async def _execute_tool_server(self, function_name: str, token: Optional[str], 
                                 server_data: ToolServerData, parameters: Dict[str, Any]) -> Any:
        """
        Execute tool server function
        Based on OpenWebUI's execute_tool_server function
        """
        try:
            # Check if event loop is available and not closed
            try:
                loop = asyncio.get_running_loop()
                if loop.is_closed():
                    raise RuntimeError("Event loop is closed")
            except RuntimeError as e:
                if "no running event loop" in str(e).lower() or "event loop is closed" in str(e).lower():
                    logger.warning(f"Skipping tool execution - event loop not available: {str(e)}")
                    raise RuntimeError("Event loop is closed or not available")
                # Re-raise other RuntimeErrors
                raise
            
            # Find the operation in OpenAPI spec
            operation_info = self._find_operation_by_id(server_data.openapi, function_name)
            
            if not operation_info:
                raise ValueError(f"Operation {function_name} not found in OpenAPI spec")
            
            path, method, operation = operation_info
            
            # Build request URL
            # For ArXiv MCP server, prepend the server path
            if "arxiv" in server_data.name.lower():
                url = f"{server_data.url.rstrip('/')}/arxiv-mcp-server{path}"
            else:
                url = f"{server_data.url.rstrip('/')}{path}"
            
            # Replace path parameters
            path_params = {}
            for param_name, param_value in parameters.items():
                if f"{{{param_name}}}" in path:
                    url = url.replace(f"{{{param_name}}}", str(param_value))
                    path_params[param_name] = param_value
            
            # Remove path parameters from body parameters
            body_params = {k: v for k, v in parameters.items() if k not in path_params}
            
            # Debug: Print request data
            # print(f"===========================================================")
            # print(f"🔍 OpenWebUI Request Debug:")
            # print(f"  Function: {function_name}")
            # print(f"  URL: {url}")
            # print(f"  Method: {method.upper()}")
            # print(f"  Path params: {path_params}")
            # print(f"  Body params: {body_params}")
            # print(f"===========================================================")
            
            # Prepare request
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'DeepResearcher-OpenWebUI/1.0'
            }
            
            if token:
                if server_data.auth.get("type") == "bearer":
                    headers['Authorization'] = f'Bearer {token}'
                elif server_data.auth.get("type") == "session":
                    headers['X-Session-Token'] = token
            
            # Always create a fresh session for ArXiv to avoid event loop issues
            session = self.sessions.get(server_data.name)
            session_needs_recreation = True
            
            if session_needs_recreation:
                # Close old session if it exists
                if session and not session.closed:
                    try:
                        await session.close()
                    except Exception as e:
                        logger.warning(f"Error closing old session: {str(e)}")
                
                # Recreate session
                timeout = aiohttp.ClientTimeout(total=server_data.config.get("timeout", 30))
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'DeepResearcher-OpenWebUI/1.0'
                }
                
                if token:
                    if server_data.auth.get("type") == "bearer":
                        headers['Authorization'] = f'Bearer {token}'
                    elif server_data.auth.get("type") == "session":
                        headers['X-Session-Token'] = token
                        
                session = aiohttp.ClientSession(timeout=timeout, headers=headers)
                self.sessions[server_data.name] = session
            
            # Execute request
            print(f"  Headers: {headers}")
            if method.lower() in ["post", "put", "patch"] and body_params:
                print(f"  JSON payload: {body_params}")
            elif method.lower() == "get":
                print(f"  Query params: {body_params}")
            
            # Final check before making request - ensure event loop is still running
            try:
                loop = asyncio.get_running_loop()
                if loop.is_closed():
                    raise RuntimeError("Event loop closed before request")
            except RuntimeError as e:
                logger.warning(f"Event loop check failed before request: {str(e)}")
                raise RuntimeError("Event loop is closed")
            
            try:
                async with session.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    json=body_params if method.lower() in ["post", "put", "patch"] and body_params else None,
                    params=body_params if method.lower() == "get" else None
                ) as response:
                    
                    print(f"📡 Response Status: {response.status}")
                    
                    if response.status >= 400:
                        error_text = await response.text()
                        print(f"❌ Error response: {error_text}")
                        raise RuntimeError(f"Tool server request failed: {response.status} - {error_text}")
                    
                    result = await response.json()
                    print(f"✅ Response data: {result}")
                    
                    # Close session immediately after successful request
                    try:
                        await session.close()
                        # Remove from sessions dict since we closed it
                        if server_data.name in self.sessions:
                            del self.sessions[server_data.name]
                    except Exception as e:
                        logger.warning(f"Error closing session after request: {str(e)}")
                    
                    return result
                    
            except RuntimeError as e:
                # Check if it's an event loop issue
                if "event loop" in str(e).lower() or "cannot write request body" in str(e).lower():
                    logger.warning(f"Event loop or connection issue during HTTP request: {str(e)}")
                    raise RuntimeError("Event loop is closed during request")
                else:
                    # Re-raise other RuntimeErrors
                    raise
            except Exception as e:
                # Catch any other async/connection errors that might indicate event loop issues
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ["event loop", "cannot write", "connection", "closed", "asyncio"]):
                    logger.warning(f"Connection/async error (likely event loop issue): {str(e)}")
                    raise RuntimeError("Event loop or connection issue during request")
                else:
                    # Re-raise unexpected errors
                    logger.error(f"Unexpected error during HTTP request: {str(e)}")
                    raise
                
        except Exception as e:
            logger.error(f"Failed to execute tool server function {function_name}: {str(e)}")
            
            # Clean up session on any error
            try:
                session = self.sessions.get(server_data.name)
                if session and not session.closed:
                    await session.close()
                if server_data.name in self.sessions:
                    del self.sessions[server_data.name]
            except Exception as cleanup_error:
                logger.warning(f"Error during session cleanup: {str(cleanup_error)}")
            
            raise
    
    def _find_operation_by_id(self, openapi_spec: Dict[str, Any], operation_id: str) -> Optional[tuple]:
        """Find operation in OpenAPI spec by operation ID"""
        paths = openapi_spec.get("paths", {})
        
        for path, path_spec in paths.items():
            for method, operation in path_spec.items():
                if operation.get("operationId") == operation_id:
                    return path, method, operation
        
        return None
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tool names"""
        return list(self.tool_functions.keys())
    
    def get_tool_specs_for_llm(self) -> List[Dict[str, Any]]:
        """Get tool specifications formatted for LLM"""
        return [spec.__dict__ for spec in self.tool_specs.values()]
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Execute a tool by name"""
        if tool_name not in self.tool_functions:
            raise ValueError(f"Tool {tool_name} not found")
        
        # Check if event loop is closed/closing
        try:
            loop = asyncio.get_running_loop()
            if loop.is_closed():
                raise RuntimeError("Event loop is closed")
        except RuntimeError:
            # No event loop or loop is closed
            raise RuntimeError("Event loop is closed or not available")
        
        tool_function = self.tool_functions[tool_name]
        return await tool_function(**parameters)
    
    async def cleanup(self):
        """Clean up sessions and connections"""
        for session in self.sessions.values():
            if session and not session.closed:
                await session.close()
        self.sessions.clear()
        
    def __del__(self):
        """Cleanup when object is garbage collected"""
        # Note: This is a backup cleanup, proper cleanup should be done explicitly
        if hasattr(self, 'sessions') and self.sessions:
            import asyncio
            import warnings
            try:
                loop = asyncio.get_running_loop()
                for session in self.sessions.values():
                    if session and not session.closed:
                        loop.create_task(session.close())
            except RuntimeError:
                # No event loop running
                pass
            except Exception as e:
                warnings.warn(f"Failed to cleanup sessions: {e}")

# Global integration instance
openwebui_integration = OpenWebUIToolIntegration()

# Utility functions for easy integration

async def register_arxiv_mcp_server(server_url: str = "http://localhost:9937", 
                                   auth_token: Optional[str] = None) -> bool:
    """
    Register ArXiv MCP server using OpenWebUI patterns
    
    Args:
        server_url: URL of the ArXiv MCP server
        auth_token: Optional authentication token
        
    Returns:
        True if registration successful
    """
    config = ToolServerConfig(
        url=server_url,
        name="arxiv_mcp_server",
        auth_type="bearer",
        auth_token=auth_token,
        timeout=30,
        max_retries=3
    )
    
    return await openwebui_integration.register_tool_server(config)

async def get_available_tools() -> List[str]:
    """Get list of available tools"""
    return openwebui_integration.get_available_tools()

async def get_tool_specs_for_llm() -> List[Dict[str, Any]]:
    """Get tool specifications for LLM"""
    return openwebui_integration.get_tool_specs_for_llm()

async def execute_tool(tool_name: str, parameters: Dict[str, Any]) -> Any:
    """Execute a tool by name"""
    return await openwebui_integration.execute_tool(tool_name, parameters)

async def cleanup_integration():
    """Clean up integration resources"""
    await openwebui_integration.cleanup()

def ensure_session_health():
    """Ensure sessions are healthy, recreate if needed"""
    # This can be called periodically to maintain session health
    pass
