import os
import httpx
import requests
import aiohttp
import asyncio
import urllib.parse
import re
from typing import Dict, Any, List, Union, Optional
from bs4 import BeautifulSoup

from markdownify import markdownify
from langsmith import traceable

from langchain_community.utilities import SearxSearchWrapper
from ollama_deep_researcher.mcp_client import create_mcp_client, search_papers_mcp, MCPClient

def get_config_value(value: Any) -> str:
    """
    Convert configuration values to string format, handling both string and enum types.
    
    Args:
        value (Any): The configuration value to process. Can be a string or an Enum.
    
    Returns:
        str: The string representation of the value.
        
    Examples:
        >>> get_config_value("tavily")
        'tavily'
        >>> get_config_value(SearchAPI.TAVILY)
        'tavily'
    """
    return value if isinstance(value, str) else value.value

def strip_thinking_tokens(text: str) -> str:
    """
    Remove <think> and </think> tags and their content from the text.
    
    Iteratively removes all occurrences of content enclosed in thinking tokens.
    
    Args:
        text (str): The text to process
        
    Returns:
        str: The text with thinking tokens and their content removed
    """
    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>") + len("</think>")
        text = text[:start] + text[end:]
    return text

def deduplicate_and_format_sources(
    search_response: Union[Dict[str, Any], List[Dict[str, Any]]], 
    max_tokens_per_source: int, 
    fetch_full_page: bool = False
) -> str:
    """
    Format and deduplicate search responses from SearXNG API.
    
    Takes either a single search response or list of responses from search APIs,
    deduplicates them by URL, and formats them into a structured string.
    
    Args:
        search_response (Union[Dict[str, Any], List[Dict[str, Any]]]): Either:
            - A dict with a 'results' key containing a list of search results
            - A list of dicts, each containing search results
        max_tokens_per_source (int): Maximum number of tokens to include for each source's content
        fetch_full_page (bool, optional): Whether to include the full page content. Defaults to False.
            
    Returns:
        str: Formatted string with deduplicated sources
        
    Raises:
        ValueError: If input is neither a dict with 'results' key nor a list of search results
    """
    # Convert input to list of results
    if isinstance(search_response, dict):
        sources_list = search_response['results']
    elif isinstance(search_response, list):
        sources_list = []
        for response in search_response:
            if isinstance(response, dict) and 'results' in response:
                sources_list.extend(response['results'])
            else:
                sources_list.extend(response)
    else:
        raise ValueError("Input must be either a dict with 'results' or a list of search results")
    
    # Deduplicate by URL
    unique_sources = {}
    for source in sources_list:
        if source['url'] not in unique_sources:
            unique_sources[source['url']] = source
    
    # Format output
    formatted_text = "Sources:\n\n"
    for i, source in enumerate(unique_sources.values(), 1):
        formatted_text += f"Source: {source['title']}\n===\n"
        
        # Add content if available
        content_key = 'raw_content' if fetch_full_page and 'raw_content' in source else 'content'
        content = source.get(content_key, "No content available")
        
        # Limit content length
        if len(content) > max_tokens_per_source:
            content = content[:max_tokens_per_source] + "..."
        
        formatted_text += f"{content}\n\n"
    
    return formatted_text

def format_sources(search_results: Dict[str, Any]) -> str:
    """
    Format search results into a bullet-point list of sources with URLs.
    
    Args:
        search_results (Dict[str, Any]): Search response containing a 'results' key
        
    Returns:
        str: Formatted bullet-point string of sources with titles and URLs
    """
    sources = search_results.get("results", [])
    if not sources:
        return "No sources found."
    
    formatted_sources = []
    for i, source in enumerate(sources, 1):
        title = source.get("title", "Unknown Title")
        url = source.get("url", "No URL")
        formatted_sources.append(f"• {title}: {url}")
    
    return "\n".join(formatted_sources)

def fetch_raw_content(url: str) -> Optional[str]:
    """
    Fetch HTML content from a URL and convert it to markdown format.
    
    Args:
        url (str): The URL to fetch content from
        
    Returns:
        Optional[str]: Markdown-formatted content or None if fetching fails
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Convert HTML to markdown using markdownify
        markdown_content = markdownify(response.content, heading_style="ATX")
        return markdown_content
    except Exception as e:
        print(f"Error fetching content from {url}: {str(e)}")
        return None

@traceable
def searxng_search(query: str, max_results: int = 3, fetch_full_page: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search the web using SearXNG for comprehensive web results.
    
    Performs a web search using SearXNG metasearch engine to gather information
    from multiple search engines simultaneously.
    
    Args:
        query (str): The search query to execute
        max_results (int, optional): Maximum number of results to return. Defaults to 3.
        fetch_full_page (bool, optional): Whether to fetch the full page content for each result.
                                         Defaults to False.
        
    Returns:
        Dict[str, List[Dict[str, Any]]]: Search response containing:
            - results (list): List of search result dictionaries from SearXNG, each containing:
                - title (str): Title of the search result
                - url (str): URL of the search result
                - content (str): Snippet/summary of the content
                - raw_content (str): Full page content if fetch_full_page is True
    """
    
    # Perform SearXNG search
    searxng_results = []
    try:
        # Use SearxSearchWrapper from langchain
        searx = SearxSearchWrapper(
            searx_host="http://localhost:8001",  # Default SearXNG host
            engines=["google", "bing", "duckduckgo"]  # Multiple engines for better coverage
        )
        
        results = searx.results(query, num_results=max_results)
        
        # Process and format results
        for result in results:
            processed_result = {
                "title": result.get("title", "Unknown Title"),
                "url": result.get("link", "No URL"),
                "content": result.get("snippet", "No content available")
            }
            
            # Fetch full page content if requested
            if fetch_full_page:
                raw_content = fetch_content_with_beautifulsoup(result.get("link", ""))
                processed_result["raw_content"] = raw_content or processed_result["content"]
            else:
                processed_result["raw_content"] = processed_result["content"]
            
            searxng_results.append(processed_result)
            
    except Exception as e:
        print(f"Warning: SearXNG search failed: {str(e)}")
    
    return {"results": searxng_results}

def analyze_user_input(user_input: str) -> Dict[str, Any]:
    """
    Analyze user input to detect URLs and direct content requests.
    
    Determines if the user is asking for analysis of specific content (URLs)
    or making a general research query.
    
    Args:
        user_input (str): The user's input text
        
    Returns:
        Dict[str, Any]: Analysis result containing:
            - input_type: 'url' or 'general_query'
            - url: extracted URL if found
            - direct_fetch: whether this is a direct content request
            - search_query: optimized query for search
    """
    
    # URL pattern matching
    url_pattern = r'https?://[^\s<>"\'{}|\\^`\[\]]+'
    url_match = re.search(url_pattern, user_input)
    
    # Check for direct content request indicators
    direct_indicators = [
        r'\b(?:analyze|explain|summarize|review|examine)\s+(?:this\s+)?(?:url|link|page|website|article)',
        r'\b(?:what|how)\s+(?:is|does|are)\s+(?:this|that)',
        r'\btell\s+me\s+about\s+(?:this|that)',
        r'\b(?:analyze|explain|summarize)\s+(?:https?://|www\.)',
    ]
    
    direct_fetch = any(re.search(pattern, user_input, re.IGNORECASE) for pattern in direct_indicators)
    
    if url_match:
        url = url_match.group(0)
        return {
            'input_type': 'url',
            'url': url,
            'direct_fetch': direct_fetch,
            'search_query': user_input if not direct_fetch else f"information about {url}"
        }
    
    # No URL found - general query
    return {
        'input_type': 'general_query',
        'url': None,
        'direct_fetch': False,
        'search_query': user_input
    }

def fetch_url_content_directly(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetch content directly from any URL.
    
    Args:
        url (str): The URL to fetch content from
        
    Returns:
        Optional[Dict[str, Any]]: Dictionary containing:
            - title: Page title
            - content: Page content in markdown format
            - url: Original URL
            - source: Content source indicator
        Returns None if fetching fails.
    """
    try:
        content = fetch_content_with_beautifulsoup(url)
        
        if content:
            # Extract title from content or use URL
            title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            title = title_match.group(1) if title_match else f"Content from {url}"
            
            return {
                'title': title,
                'content': content,
                'url': url,
                'source': 'direct_fetch'
            }
        else:
            return None
            
    except Exception as e:
        print(f"Error fetching URL content: {str(e)}")
        return None

def fetch_content_with_beautifulsoup(url: str) -> Optional[str]:
    """
    Fetch content from URL using Beautiful Soup for parsing.
    
    Args:
        url (str): The URL to fetch content from
        
    Returns:
        Optional[str]: Markdown-formatted content or None if fetching fails
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        # Limit content length for processing
        if len(text) > 50000:
            text = text[:50000] + "..."
        
        return text
        
    except Exception as e:
        print(f"Error fetching content with BeautifulSoup from {url}: {str(e)}")
        return None

def web_search_only(query: str, max_results: int = 3, fetch_full_page: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    """
    Perform web search using only SearXNG.
    
    Simplified search function that uses only SearXNG for web search,
    removing complexity from multi-source coordination.
    
    Args:
        query (str): Search query
        max_results (int): Maximum results to return
        fetch_full_page (bool): Whether to fetch full page content
        
    Returns:
        Dict containing search results from SearXNG only
    """
    try:
        return searxng_search(query, max_results, fetch_full_page)
    except Exception as e:
        print(f"Web search failed: {str(e)}")
        return {"results": []}

async def mcp_search(query: str, max_results: int = 10, server_url: str = "http://localhost:9937", **kwargs) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search ArXiv papers using MCP client.
    
    Args:
        query (str): Search query for academic papers
        max_results (int): Maximum number of results to return
        server_url (str): MCP server URL
        **kwargs: Additional search parameters (sort_by, start_date, end_date, categories)
        
    Returns:
        Dict containing search results formatted for the research pipeline
    """
    try:
        # Create MCP client connection
        async with create_mcp_client(server_url) as client:
            # Search papers using MCP
            mcp_results = await search_papers_mcp(
                client=client,
                query=query,
                max_results=max_results,
                **kwargs
            )
            
            # Format results for compatibility with existing pipeline
            formatted_results = []
            papers = mcp_results.get('papers', [])
            
            for paper in papers:
                formatted_result = {
                    "title": paper.get('title', 'Unknown Title'),
                    "url": paper.get('url', f"https://arxiv.org/abs/{paper.get('id', '')}"),
                    "content": paper.get('summary', 'No summary available'),
                    "raw_content": paper.get('summary', 'No summary available'),
                    "source": "ArXiv MCP",
                    "arxiv_id": paper.get('id', ''),
                    "published": paper.get('published', ''),
                    "authors": paper.get('authors', []),
                    "categories": paper.get('categories', [])
                }
                formatted_results.append(formatted_result)
            
            return {"results": formatted_results}
            
    except Exception as e:
        print(f"MCP search failed: {str(e)}")
        return {"results": []}

def mcp_search_sync(query: str, max_results: int = 10, server_url: str = "http://localhost:9937", **kwargs) -> Dict[str, List[Dict[str, Any]]]:
    """
    Synchronous wrapper for MCP search.
    
    Args:
        query (str): Search query for academic papers
        max_results (int): Maximum number of results to return
        server_url (str): MCP server URL
        **kwargs: Additional search parameters
        
    Returns:
        Dict containing search results formatted for the research pipeline
    """
    try:
        return asyncio.run(mcp_search(query, max_results, server_url, **kwargs))
    except Exception as e:
        print(f"MCP search sync failed: {str(e)}")
        return {"results": []}

def parallel_search_coordinator(
    query: str, 
    search_strategy: str = "web_search",
    max_results: int = 8,
    fetch_full_page: bool = False,
    mcp_server_url: str = "http://localhost:9937"
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Coordinate parallel search across different sources based on strategy.
    
    Args:
        query (str): Search query
        search_strategy (str): Search strategy ("web_search" or "mcp")
        max_results (int): Maximum results to return
        fetch_full_page (bool): Whether to fetch full page content
        mcp_server_url (str): MCP server URL for ArXiv search
        
    Returns:
        Dict containing search results from the selected strategy
    """
    try:
        if search_strategy == "mcp":
            print(f"🔬 Using MCP search for ArXiv papers")
            return mcp_search_sync(query, max_results, mcp_server_url)
        else:
            print(f"🌐 Using web search")
            return web_search_only(query, max_results, fetch_full_page)
            
    except Exception as e:
        print(f"Search coordination failed: {str(e)}")
        # Fallback to web search
        return web_search_only(query, max_results, fetch_full_page)