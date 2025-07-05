"""
Memory client for integrating with memoer-mcp service via MCP protocol.
Provides functions to capture research data as memories.
"""

import json
import asyncio
import subprocess
import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

def find_memoer_mcp_path() -> str:
    """Auto-detect the memoer-mcp server path"""
    import pathlib
    
    # Start from current file and go up to find memoer-mcp
    current_path = pathlib.Path(__file__).resolve()
    
    # Look for memoer-mcp in common locations relative to this file
    search_paths = [
        # Same level as local-deep-researcher (../../memoer-mcp)
        current_path.parents[4] / "memoer-mcp",
        # In services directory (../../../memoer-mcp) 
        current_path.parents[3] / "memoer-mcp",
        # In MonkeyResearcher root (../../../../memoer-mcp)
        current_path.parents[5] / "memoer-mcp",
    ]
    
    for path in search_paths:
        if path.exists() and (path / "dist" / "index.js").exists():
            print(f"[DEBUG] Found memoer-mcp at: {path}")
            return str(path)
    
    # Fallback to environment variable or default
    env_path = os.environ.get('MEMOER_MCP_PATH')
    if env_path and pathlib.Path(env_path).exists():
        print(f"[DEBUG] Using MEMOER_MCP_PATH: {env_path}")
        return env_path
        
    # Last resort - return a reasonable default
    default_path = str(current_path.parents[4] / "memoer-mcp")
    print(f"[DEBUG] Using default memoer-mcp path: {default_path}")
    return default_path

@dataclass
class MemoryCapture:
    """Configuration for memory capture"""
    enabled: bool = True
    mcp_server_path: str = ""  # Will be auto-detected if empty
    app_name: str = "local-deep-researcher"
    capture_level: str = "essential"  # "minimal", "essential", "comprehensive"
    
    def __post_init__(self):
        if not self.mcp_server_path:
            self.mcp_server_path = find_memoer_mcp_path()
            print(f"[DEBUG] Auto-detected memoer-mcp path: {self.mcp_server_path}")

class MemoryClient:
    """Client for capturing research memories via MCP protocol"""
    
    def __init__(self, config: MemoryCapture):
        self.config = config
    
    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call MCP tool via subprocess with proper initialization sequence"""
        
        if not self.config.enabled:
            logger.debug("Memory capture disabled")
            return {"success": True, "message": "Memory disabled"}
        
        try:
            # Prepare MCP initialization sequence followed by tool call
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "local-deep-researcher", "version": "1.0.0"}
                }
            }
            
            initialized_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialized",
                "params": {}
            }
            
            tool_request = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            print(f"[DEBUG] Sending MCP tool request: {tool_name} with args: {arguments}")
            
            # Call MCP server directly with proper environment
            env = {
                **os.environ,
                "DATABASE_URL": f"file:{self.config.mcp_server_path}/prisma/memoer.db"
            }
            
            process = await asyncio.create_subprocess_exec(
                'node',
                'dist/index.js',
                cwd=self.config.mcp_server_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,  # Capture stderr separately
                env=env
            )
            
            # Send MCP initialization sequence with line separation
            requests = [
                json.dumps(init_request) + '\n',
                json.dumps(initialized_request) + '\n', 
                json.dumps(tool_request) + '\n'
            ]
            
            request_data = ''.join(requests).encode('utf-8')
            
            # Add timeout to handle potential hanging
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=request_data), 
                    timeout=10.0  # 10 second timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return {"success": False, "error": "MCP server timeout"}
            
            if process.returncode == 0:
                try:
                    stdout_text = stdout.decode('utf-8').strip()
                    stderr_text = stderr.decode('utf-8').strip() if stderr else ""
                    
                    print(f"[DEBUG] MCP stdout: {stdout_text}")
                    if stderr_text:
                        print(f"[DEBUG] MCP stderr: {stderr_text}")
                    
                    # Parse each JSON response line from stdout only
                    response_lines = stdout_text.split('\n')
                    tool_response = None
                    
                    for line in response_lines:
                        line = line.strip()
                        if line and line.startswith('{'): # Valid JSON line
                            try:
                                response = json.loads(line)
                                print(f"[DEBUG] Parsed response: {response}")
                                # Look for our tool call response (id=3)
                                if response.get("id") == 3:
                                    tool_response = response
                                    break
                            except json.JSONDecodeError as e:
                                print(f"[DEBUG] JSON decode error for line: {line}, error: {e}")
                                continue
                    
                    if tool_response:
                        if "result" in tool_response:
                            return {"success": True, "response": tool_response}
                        elif "error" in tool_response:
                            return {"success": False, "error": tool_response["error"].get("message", "Tool call failed")}
                    
                    logger.warning(f"No tool response (id=3) found in output: {stdout_text}")
                    return {"success": False, "error": "No tool response found"}
                    
                except Exception as e:
                    logger.warning(f"Error parsing MCP response: {str(e)}")
                    return {"success": False, "error": f"Parse error: {str(e)}"}
            else:
                error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
                logger.warning(f"MCP server returned non-zero exit code: {process.returncode}, error: {error_msg}")
                return {"success": False, "error": f"Server error (exit code: {process.returncode})"}
                    
        except Exception as e:
            logger.warning(f"MCP call failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def capture_research_memory(
        self,
        content: str,
        research_topic: str,
        memory_type: str,
        source_reliability: Optional[str] = None,
        source_type: Optional[str] = None,
        research_loop_count: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Capture research memory via MCP
        
        Args:
            content: The research content to store
            research_topic: The main research topic
            memory_type: Type of memory (research_summary, search_query, web_results, final_report)
            source_reliability: Reliability rating (high, medium, low)
            source_type: Type of source (academic, web, technical, cybersecurity)
            research_loop_count: Number of research loops
            metadata: Additional metadata
            
        Returns:
            bool: True if successful, False otherwise
        """
        
        if not self.config.enabled:
            logger.debug("Memory capture disabled")
            return True
        
        # Prepare arguments for MCP tool
        arguments = {
            "content": content,
            "researchTopic": research_topic,
            "memoryType": memory_type,
            "appName": self.config.app_name
        }
        
        # Add optional fields
        if source_reliability:
            arguments["sourceReliability"] = source_reliability
        if source_type:
            arguments["sourceType"] = source_type
        if research_loop_count is not None:
            arguments["researchLoopCount"] = research_loop_count
        if metadata:
            arguments["metadata"] = json.dumps(metadata)
        
        # Call MCP tool
        result = await self._call_mcp_tool("createResearchMemory", arguments)
        
        if result["success"]:
            logger.info(f"Memory captured successfully: {memory_type} for topic '{research_topic}'")
            return True
        else:
            logger.warning(f"Memory capture failed: {result.get('error', 'Unknown error')}")
            return False
    
    async def retrieve_similar_research(
        self,
        research_topic: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve similar research memories via MCP
        
        Args:
            research_topic: The research topic to search for
            limit: Maximum number of results
            
        Returns:
            List of memory records
        """
        
        if not self.config.enabled:
            return []
        
        arguments = {
            "researchTopic": research_topic,
            "limit": limit
        }
        
        result = await self._call_mcp_tool("getResearchMemories", arguments)
        
        if result["success"] and "response" in result:
            try:
                response = result["response"]
                if "result" in response and "content" in response["result"]:
                    content_text = response["result"]["content"][0].get("text", "[]")
                    memories = json.loads(content_text)
                    logger.info(f"Retrieved {len(memories)} similar research memories")
                    return memories
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.warning(f"Failed to parse memory retrieval response: {str(e)}")
        
        return []
    
    async def close(self):
        """Cleanup resources (no persistent connections in MCP)"""
        pass

# Global memory client instance
_memory_client: Optional[MemoryClient] = None

def get_memory_client() -> Optional[MemoryClient]:
    """Get the global memory client instance"""
    return _memory_client

def initialize_memory_client(config: MemoryCapture) -> MemoryClient:
    """Initialize the global memory client"""
    global _memory_client
    _memory_client = MemoryClient(config)
    return _memory_client

async def cleanup_memory_client():
    """Cleanup memory client resources"""
    global _memory_client
    if _memory_client:
        await _memory_client.close()
        _memory_client = None

# Convenience functions for easy integration
async def capture_memory_safe(
    content: str,
    research_topic: str,
    memory_type: str,
    **kwargs
) -> bool:
    """
    Safely capture memory with error handling
    
    Args:
        content: Content to store
        research_topic: Research topic
        memory_type: Type of memory
        **kwargs: Additional arguments
        
    Returns:
        bool: True if successful or memory disabled, False on error
    """
    try:
        client = get_memory_client()
        if client:
            return await client.capture_research_memory(
                content=content,
                research_topic=research_topic,
                memory_type=memory_type,
                **kwargs
            )
        else:
            logger.debug("Memory client not initialized")
            return True  # Return True when disabled to avoid pipeline failures
            
    except Exception as e:
        logger.warning(f"Memory capture failed safely: {str(e)}")
        return True  # Return True to avoid pipeline failures