"""
MCP Client for ArXiv MCP Server Integration

Based on OpenWebUI's external tool integration patterns, this module provides
MCP (Model Context Protocol) client functionality for connecting to ArXiv MCP servers.
"""

import json
import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class MCPToolType(Enum):
    """MCP Tool Types based on ArXiv MCP Server"""
    SEARCH_PAPERS = "search_papers"
    DOWNLOAD_PAPER = "download_paper"
    LIST_PAPERS = "list_papers"
    READ_PAPER = "read_paper"

@dataclass
class MCPToolSpec:
    """MCP Tool Specification"""
    name: str
    description: str
    parameters: Dict[str, Any]
    required: List[str] = None

@dataclass
class MCPServerConfig:
    """MCP Server Configuration"""
    url: str
    timeout: int = 30
    max_retries: int = 3
    auth_token: Optional[str] = None

class MCPClient:
    """
    MCP Client for ArXiv MCP Server integration
    
    Based on OpenWebUI's external tool server patterns, this client handles:
    - HTTP-based communication with MCP servers
    - Tool discovery and specification parsing
    - Request/response handling with error management
    - Authentication and session management
    """
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.tools: Dict[str, MCPToolSpec] = {}
        self.connected = False
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
        
    async def connect(self):
        """
        Establish connection to MCP server
        Similar to OpenWebUI's tool server connection pattern
        """
        try:
            # Create session with timeout configuration
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'DeepResearcher-MCP-Client/1.0'
            }
            
            if self.config.auth_token:
                headers['Authorization'] = f'Bearer {self.config.auth_token}'
                
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers=headers
            )
            
            # Test connection and discover tools
            await self._discover_tools()
            self.connected = True
            logger.info(f"Connected to MCP server at {self.config.url}")
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {str(e)}")
            raise ConnectionError(f"MCP server connection failed: {str(e)}")
            
    async def disconnect(self):
        """Close connection to MCP server"""
        if self.session:
            await self.session.close()
            self.session = None
        self.connected = False
        logger.info("Disconnected from MCP server")
        
    async def _discover_tools(self):
        """
        Discover available tools from MCP server
        Based on OpenWebUI's tool discovery pattern
        """
        try:
            # Get tools endpoint (standard MCP pattern)
            async with self.session.get(f"{self.config.url}/tools") as response:
                if response.status == 200:
                    tools_data = await response.json()
                    await self._parse_tools_spec(tools_data)
                else:
                    # Fallback: Define ArXiv MCP tools manually
                    await self._load_default_arxiv_tools()
                    
        except Exception as e:
            logger.warning(f"Tool discovery failed, using default ArXiv tools: {str(e)}")
            await self._load_default_arxiv_tools()
            
    async def _parse_tools_spec(self, tools_data: Dict[str, Any]):
        """Parse tools specification from MCP server response"""
        for tool_name, tool_spec in tools_data.get("tools", {}).items():
            self.tools[tool_name] = MCPToolSpec(
                name=tool_name,
                description=tool_spec.get("description", ""),
                parameters=tool_spec.get("parameters", {}),
                required=tool_spec.get("required", [])
            )
            
    async def _load_default_arxiv_tools(self):
        """Load default ArXiv MCP tools specification"""
        self.tools = {
            "search_papers": MCPToolSpec(
                name="search_papers",
                description="Search for academic papers on ArXiv",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for papers"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 10
                        },
                        "sort_by": {
                            "type": "string",
                            "enum": ["relevance", "lastUpdatedDate", "submittedDate"],
                            "default": "relevance"
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date for search (YYYY-MM-DD)"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date for search (YYYY-MM-DD)"
                        },
                        "categories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "ArXiv categories to search in"
                        }
                    },
                    "required": ["query"]
                }
            ),
            "download_paper": MCPToolSpec(
                name="download_paper",
                description="Download a paper by ArXiv ID",
                parameters={
                    "type": "object",
                    "properties": {
                        "paper_id": {
                            "type": "string",
                            "description": "ArXiv paper ID (e.g., '2401.12345')"
                        }
                    },
                    "required": ["paper_id"]
                }
            ),
            "list_papers": MCPToolSpec(
                name="list_papers",
                description="List all locally downloaded papers",
                parameters={
                    "type": "object",
                    "properties": {}
                }
            ),
            "read_paper": MCPToolSpec(
                name="read_paper",
                description="Read content of a downloaded paper",
                parameters={
                    "type": "object",
                    "properties": {
                        "paper_id": {
                            "type": "string",
                            "description": "ArXiv paper ID to read"
                        }
                    },
                    "required": ["paper_id"]
                }
            )
        }
        
    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the MCP server
        Based on OpenWebUI's external tool execution pattern
        """
        if not self.connected:
            raise RuntimeError("MCP client not connected")
            
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not available")
            
        try:
            # Prepare request payload
            payload = {
                "tool": tool_name,
                "parameters": parameters
            }
            
            # Execute tool call with retry logic
            for attempt in range(self.config.max_retries):
                try:
                    async with self.session.post(
                        f"{self.config.url}/call",
                        json=payload
                    ) as response:
                        
                        if response.status == 200:
                            result = await response.json()
                            logger.info(f"Tool '{tool_name}' executed successfully")
                            return result
                        else:
                            error_text = await response.text()
                            logger.error(f"Tool call failed: {response.status} - {error_text}")
                            
                            if attempt == self.config.max_retries - 1:
                                raise RuntimeError(f"Tool call failed after {self.config.max_retries} attempts")
                                
                except asyncio.TimeoutError:
                    logger.warning(f"Tool call timeout, attempt {attempt + 1}/{self.config.max_retries}")
                    if attempt == self.config.max_retries - 1:
                        raise RuntimeError("Tool call timed out")
                        
                except Exception as e:
                    logger.error(f"Tool call error: {str(e)}")
                    if attempt == self.config.max_retries - 1:
                        raise
                        
                # Wait before retry
                await asyncio.sleep(2 ** attempt)
                
        except Exception as e:
            logger.error(f"Failed to call tool '{tool_name}': {str(e)}")
            raise
            
    def get_available_tools(self) -> List[str]:
        """Get list of available tool names"""
        return list(self.tools.keys())
        
    def get_tool_spec(self, tool_name: str) -> Optional[MCPToolSpec]:
        """Get specification for a specific tool"""
        return self.tools.get(tool_name)
        
    def get_all_tool_specs(self) -> Dict[str, MCPToolSpec]:
        """Get all tool specifications"""
        return self.tools.copy()

# Utility functions for integration with the research pipeline

async def create_mcp_client(server_url: str, **kwargs) -> MCPClient:
    """
    Create and connect MCP client
    
    Args:
        server_url: URL of the MCP server
        **kwargs: Additional configuration options
        
    Returns:
        Connected MCP client instance
    """
    config = MCPServerConfig(
        url=server_url.rstrip('/'),
        timeout=kwargs.get('timeout', 30),
        max_retries=kwargs.get('max_retries', 3),
        auth_token=kwargs.get('auth_token')
    )
    
    client = MCPClient(config)
    await client.connect()
    return client

async def search_papers_mcp(client: MCPClient, query: str, max_results: int = 10, **kwargs) -> Dict[str, Any]:
    """
    Search papers using MCP client
    
    Args:
        client: Connected MCP client
        query: Search query
        max_results: Maximum number of results
        **kwargs: Additional search parameters
        
    Returns:
        Search results from ArXiv MCP server
    """
    parameters = {
        "query": query,
        "max_results": max_results,
        **kwargs
    }
    
    return await client.call_tool("search_papers", parameters)

async def download_paper_mcp(client: MCPClient, paper_id: str) -> Dict[str, Any]:
    """
    Download paper using MCP client
    
    Args:
        client: Connected MCP client
        paper_id: ArXiv paper ID
        
    Returns:
        Download result
    """
    return await client.call_tool("download_paper", {"paper_id": paper_id})

async def read_paper_mcp(client: MCPClient, paper_id: str) -> Dict[str, Any]:
    """
    Read paper content using MCP client
    
    Args:
        client: Connected MCP client
        paper_id: ArXiv paper ID
        
    Returns:
        Paper content
    """
    return await client.call_tool("read_paper", {"paper_id": paper_id})