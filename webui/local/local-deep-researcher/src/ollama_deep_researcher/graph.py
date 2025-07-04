import json
import asyncio

from typing_extensions import Literal

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama
from langgraph.graph import START, END, StateGraph

from ollama_deep_researcher.configuration import Configuration, SearchAPI
from ollama_deep_researcher.utils import deduplicate_and_format_sources, format_sources, searxng_search, strip_thinking_tokens, get_config_value, analyze_user_input, fetch_url_content_directly, parallel_search_coordinator
from ollama_deep_researcher.intent_classifier import classify_query_intent, intent_rule_based
from ollama_deep_researcher.state import SummaryState, SummaryStateInput, SummaryStateOutput
from ollama_deep_researcher.prompts import query_writer_instructions, summarizer_instructions, reflection_instructions, report_generation_instructions, chain_of_verification_instructions, verification_synthesis_instructions, get_current_date
from ollama_deep_researcher.openai_compatible import ChatOpenAICompatible
from ollama_deep_researcher.tool_manager import (
    tool_manager, 
    get_tools_for_llm, 
    execute_tool_call,
    initialize_openwebui_tools,
    is_openwebui_initialized
)

# Nodes
def classify_intent(state: SummaryState, config: RunnableConfig):
    """Simplified LangGraph node that analyzes user input for web search.
    
    Uses simplified intent classification to determine the search approach:
    - 'web_search': For general research queries using SearXNG
    - 'url_fetch': For direct content extraction from URLs
    
    Args:
        state: Current graph state containing the research topic
        config: Configuration for the runnable, including LLM provider settings
        
    Returns:
        Dictionary with state update, including input_analysis, search_strategy, and intent_result
    """
    
    # Analyze user input to detect URLs and direct fetch needs
    input_analysis = analyze_user_input(state.research_topic)
    
    print(f"🔍 Input analysis: {input_analysis['input_type']}")
    
    # Determine search strategy based on input analysis
    if input_analysis['input_type'] == 'url':
        if input_analysis['direct_fetch']:
            search_strategy = "url_fetch"  # Fetch URL content first for direct requests
        else:
            search_strategy = "web_search"  # Regular web search
        
        # Create a simple intent result for URL cases
        intent_result = {
            "intent": "Direct Content Request",
            "confidence": 0.95,
            "routing_strategy": search_strategy,
            "classification_method": "url_analysis"
        }
    else:
        # Use simplified intent classifier for general queries
        try:
            configurable = Configuration.from_runnable_config(config)
            intent_result = classify_query_intent(state.research_topic, configurable)
            
            # Always use web search for simplicity
            search_strategy = "web_search"
            
            print(f"🧠 Intent: {intent_result.get('intent', 'Unknown')} (confidence: {intent_result.get('confidence', 0.0):.2f})")
            print(f"🎯 Strategy: {search_strategy}")
            
        except Exception as e:
            print(f"⚠️ Intent classifier failed, using fallback: {str(e)}")
            # Fallback to web search
            intent_result = intent_rule_based(state.research_topic)
            search_strategy = "web_search"
    
    return {
        "input_analysis": input_analysis,
        "search_strategy": search_strategy,
        "intent_result": intent_result
    }

async def _tool_enhanced_research_async(state: SummaryState, config: RunnableConfig):
    """Async helper for tool-enhanced research"""
    
    print("🛠️ Starting tool-enhanced research...")
    
    # Configure LLM with tool calling support
    configurable = Configuration.from_runnable_config(config)
    
    # Initialize OpenWebUI integration if not already done
    if not is_openwebui_initialized():
        print("🔧 Initializing OpenWebUI integration...")
        try:
            await initialize_openwebui_tools("http://192.168.19.61:9937")
            if is_openwebui_initialized():
                print("✅ OpenWebUI integration initialized successfully")
            else:
                print("⚠️ OpenWebUI integration failed to initialize")
        except Exception as e:
            print(f"⚠️ OpenWebUI initialization error: {str(e)}")
    
    # Get available tools for LLM
    available_tools = get_tools_for_llm()
    
    if not available_tools:
        print("⚠️ No tools available, skipping tool-enhanced research")
        return {"tool_results": [], "enhanced_context": ""}
    
    # Choose the appropriate LLM based on the provider
    if configurable.llm_provider == "openai_compatible":
        llm = ChatOpenAICompatible(
            base_url=configurable.openai_compatible_base_url,
            model=configurable.local_llm,
            temperature=0.1,
            api_key=configurable.openai_compatible_api_key,
        )
    else:  # Default to Ollama
        llm = ChatOllama(
            base_url=configurable.ollama_base_url, 
            model=configurable.local_llm, 
            temperature=0.1
        )
    
    # Prepare tool calling prompt with more specific instructions
    tool_prompt = f"""You are a research assistant with access to various tools. Your task is to gather comprehensive information about: {state.research_topic}

Available tools: {[tool['function']['name'] for tool in available_tools]}

For comprehensive research, you should typically use BOTH web search AND academic search tools:
1. Use 'web_search' to find current information, news, and general resources
2. Use 'arxiv_search' to find academic papers and research publications
3. You may also use other specialized tools if available

Research topic: {state.research_topic}
Current research context: {state.running_summary if state.running_summary else 'Starting fresh research'}

Please use multiple tools to gather comprehensive information from different sources."""

    try:
        # Use manual tool calling approach (OpenWebUI pattern)
        # Format tools as text for the LLM to choose from
        tools_description = "Available tools:\n"
        for tool in available_tools:
            func_info = tool["function"]
            tools_description += f"- {func_info['name']}: {func_info['description']}\n"
            
        enhanced_tool_prompt = f"""{tool_prompt}

{tools_description}

Analyze the research topic and determine which tools are actually needed:

- Use 'web_search' for: general information, current events, news, tutorials, factual queries, company/university info, "what is" questions
- Use 'arxiv_search' ONLY for: research papers, scientific studies, academic research, algorithm research, cutting-edge technology research
- For simple greetings or basic questions, use no tools

IMPORTANT: Be selective with tools. Don't use arxiv_search for basic factual questions about organizations, people, or general topics.

Respond with a JSON object in this format:
{{"tool_calls": [{{"name": "tool_name", "arguments": {{"param": "value"}}}}]}}

Examples:
- "What is quantum computing research?": {{"tool_calls": [{{"name": "web_search", "arguments": {{"query": "quantum computing research", "max_results": 3}}}}, {{"name": "arxiv_search", "arguments": {{"query": "quantum computing", "max_results": 5}}}}]}}
- "What is MIT university?": {{"tool_calls": [{{"name": "web_search", "arguments": {{"query": "MIT university", "max_results": 3}}}}]}}
- "Hello": {{"tool_calls": []}}

Respond ONLY with the JSON object, no other text."""

        # Invoke LLM with enhanced prompt
        response = llm.invoke([
            SystemMessage(content="You are a helpful research assistant. You can use tools by responding with JSON tool calls."),
            HumanMessage(content=enhanced_tool_prompt)
        ])
        
        tool_results = []
        enhanced_context = ""
        
        # Parse response for tool calls
        response_content = response.content.strip()
        tool_calls_made = False
        
        # Debug: Print LLM response
        print(f"🤖 LLM Response: {response_content[:300]}...")
        
        # Try to extract JSON tool calls from response
        try:
            import re
            
            # Multiple patterns to catch different JSON formats
            patterns = [
                r'\{.*?"tool_calls".*?\[.*?\].*?\}',  # Most flexible first
                r'```json\s*(\{.*?"tool_calls".*?\})\s*```',  # Markdown code blocks
                r'```\s*(\{.*?"tool_calls".*?\})\s*```',  # Generic code blocks
                r'\{[^{}]*"tool_calls"[^{}]*\[[^\]]*\][^{}]*\}',  # Standard format
            ]
            
            tool_call_json = None
            for pattern in patterns:
                json_match = re.search(pattern, response_content, re.DOTALL)
                if json_match:
                    try:
                        # Extract the JSON part (use group 1 if it exists, otherwise group 0)
                        json_text = json_match.group(1) if json_match.groups() else json_match.group(0)
                        tool_call_json = json.loads(json_text)
                        break
                    except json.JSONDecodeError:
                        continue
            
            # Also try parsing the entire response as JSON
            if not tool_call_json:
                try:
                    tool_call_json = json.loads(response_content)
                except json.JSONDecodeError as e:
                    print(f"🔍 JSON parsing failed for response: {str(e)}")
                    pass
            
            if tool_call_json and "tool_calls" in tool_call_json:
                tool_calls = tool_call_json.get("tool_calls", [])
                
                if isinstance(tool_calls, list):
                    if len(tool_calls) > 0:
                        print(f"🔧 Executing {len(tool_calls)} tool calls...")
                        print(f"🔍 Tool calls parsed: {[tc.get('name', 'unknown') for tc in tool_calls]}")
                        tool_calls_made = True
                    else:
                        print("🤖 LLM decided no tools needed for this query")
                        tool_calls_made = True  # Mark as successful even with empty list
                        # Return early with empty results
                        return {
                            "tool_results": [],
                            "enhanced_context": f"LLM Analysis: {response_content.strip()}"
                        }
                    
                    for tool_call in tool_calls:
                        tool_name = tool_call.get('name', '')
                        tool_args = tool_call.get('arguments', tool_call.get('args', {}))
                        
                        if not tool_name:
                            print(f"  ⚠️ Skipping tool call with missing name")
                            continue
                            
                        print(f"  📞 Calling tool: {tool_name}")
                        
                        # Execute tool call
                        execution_result = await execute_tool_call(tool_name, tool_args)
                        
                        if execution_result.success:
                            tool_results.append({
                                "tool_name": tool_name,
                                "parameters": tool_args,
                                "result": execution_result.result,
                                "execution_time": execution_result.execution_time
                            })
                            
                            # Add to enhanced context
                            enhanced_context += f"\n--- Tool: {tool_name} ---\n"
                            enhanced_context += f"Parameters: {tool_args}\n"
                            enhanced_context += f"Result: {str(execution_result.result)[:1000]}...\n"
                            
                            print(f"  ✅ Tool {tool_name} executed successfully")
                        else:
                            print(f"  ❌ Tool {tool_name} failed: {execution_result.error}")
                            
        except Exception as e:
            print(f"📝 Tool call parsing failed: {str(e)}, using response as regular content")
            
        # If no tool calls were made, use intelligent fallback
        if not tool_calls_made:
            print("🤖 No tool calls detected, using intelligent fallback...")
            
            # Determine appropriate tools based on research topic
            topic_lower = state.research_topic.lower()
            
            # Always try web search for general information
            try:
                print("  📞 Fallback: Executing web search")
                web_search_result = await execute_tool_call("web_search", {
                    "query": state.research_topic,
                    "max_results": 3
                })
                
                if web_search_result.success:
                    tool_results.append({
                        "tool_name": "web_search",
                        "parameters": {"query": state.research_topic},
                        "result": web_search_result.result,
                        "execution_time": web_search_result.execution_time
                    })
                    enhanced_context += f"\n--- Fallback Tool: web_search ---\n"
                    enhanced_context += f"Query: {state.research_topic}\n"
                    enhanced_context += f"Results: {web_search_result.result.get('results_count', 0)} found\n"
                    print(f"  ✅ Fallback web search successful")
                
            except Exception as e:
                print(f"  ❌ Fallback web search failed: {str(e)}")
            
            # Always try ArXiv search for any research topic (expanded criteria)
            try:
                print("  📞 Fallback: Executing ArXiv search for academic topic")
                arxiv_search_result = await execute_tool_call("arxiv_search", {
                    "query": state.research_topic,
                    "max_results": 3
                })
                
                if arxiv_search_result.success:
                    tool_results.append({
                        "tool_name": "arxiv_search",
                        "parameters": {"query": state.research_topic},
                        "result": arxiv_search_result.result,
                        "execution_time": arxiv_search_result.execution_time
                    })
                    enhanced_context += f"\n--- Fallback Tool: arxiv_search ---\n"
                    enhanced_context += f"Query: {state.research_topic}\n"
                    enhanced_context += f"Papers: {arxiv_search_result.result.get('results_count', 0)} found\n"
                    print(f"  ✅ Fallback ArXiv search successful")
                
            except Exception as e:
                print(f"  ❌ Fallback ArXiv search failed: {str(e)}")
            
            # Include original LLM response as additional context
            if response_content.strip():
                enhanced_context += f"\n--- LLM Analysis ---\n{response_content}\n"
            
        return {
            "tool_results": tool_results,
            "enhanced_context": enhanced_context
        }
        
    except Exception as e:
        print(f"❌ Tool-enhanced research failed: {str(e)}")
        return {"tool_results": [], "enhanced_context": ""}
    
    finally:
        # Don't clean up sessions here - they might be needed for subsequent calls
        # Sessions will be cleaned up when the process ends or explicitly called
        pass

def tool_enhanced_research(state: SummaryState, config: RunnableConfig):
    """LangGraph node that performs tool-enhanced research using dynamic tool calling.
    
    Uses LLM with tool calling capabilities to dynamically select and execute
    appropriate tools for research based on the topic and current context.
    
    Args:
        state: Current graph state containing research topic and context
        config: Configuration for the runnable, including LLM provider settings
        
    Returns:
        Dictionary with state update, including tool_results and enhanced_context
    """
    # Run the async function synchronously
    return asyncio.run(_tool_enhanced_research_async(state, config))

def generate_query(state: SummaryState, config: RunnableConfig):
    """LangGraph node that generates a search query based on the research topic.
    
    Uses an LLM to create an optimized search query for web research based on
    the user's research topic. If URL content was fetched first, generates
    queries to find related/supporting information.
    
    Args:
        state: Current graph state containing the research topic
        config: Configuration for the runnable, including LLM provider settings
        
    Returns:
        Dictionary with state update, including search_query key containing the generated query
    """

    # Check if we already have URL content to inform the query
    has_url_content = len(state.web_research_results) > 0
    
    # Format the enhanced prompt with full context
    current_date = get_current_date()
    
    if has_url_content:
        # Extract key information from the fetched content to inform the query
        fetched_content = state.web_research_results[0][:2000]  # First 2000 chars of fetched content
        
        # Create a more informed research context while maintaining original topic focus
        research_context = f"""Find additional information related to: {state.research_topic}

Based on the content already fetched, generate a focused search query to find complementary information about the SAME topic.

FETCHED CONTENT SUMMARY:
{fetched_content}

IMPORTANT: Stay focused on the original research topic: {state.research_topic}"""
        
        formatted_prompt = query_writer_instructions.format(
            current_date=current_date,
            research_topic=research_context
        )
    else:
        # Standard query generation with topic focus
        formatted_prompt = query_writer_instructions.format(
            current_date=current_date,
            research_topic=state.research_topic
        )

    # Generate a query
    configurable = Configuration.from_runnable_config(config)
    
    # Choose the appropriate LLM based on the provider
    if configurable.llm_provider == "openai_compatible":
        llm_json_mode = ChatOpenAICompatible(
            base_url=configurable.openai_compatible_base_url,
            model=configurable.local_llm,
            temperature=0,
            format="json",
            api_key=configurable.openai_compatible_api_key,
            # max_tokens=8192
        )
    else: # Default to Ollama
        llm_json_mode = ChatOllama(
            base_url=configurable.ollama_base_url, 
            model=configurable.local_llm, 
            temperature=0, 
            format="json"
        )
    
    result = llm_json_mode.invoke(
        [SystemMessage(content=formatted_prompt),
        HumanMessage(content=f"Generate a query for web search:")]
    )
    
    # Get the content
    content = result.content

    # Parse the JSON response and get the query
    try:
        # Clean the content first - remove any leading/trailing whitespace
        content = content.strip()
        # Try to extract JSON if it's embedded in other text
        if content and not content.startswith('{'):
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                content = content[json_start:json_end]
        
        query = json.loads(content)
        search_query = query['query']
    except (json.JSONDecodeError, KeyError, TypeError):
        # If parsing fails or the key is not found, use a fallback query
        if configurable.strip_thinking_tokens:
            content = strip_thinking_tokens(content)
        search_query = content
    return {"search_query": search_query}

def fetch_url_content(state: SummaryState, config: RunnableConfig):
    """LangGraph node that fetches content from URLs to inform research.
    
    Fetches content from provided URLs first, then this content is used
    to generate better search queries for the research loop.
    
    Args:
        state: Current graph state containing input analysis with URL
        config: Configuration for the runnable
        
    Returns:
        Dictionary with state update, including web_research_results and sources_gathered
    """
    
    if not state.input_analysis.get('url'):
        print("❌ No URL found for content fetch")
        return {"web_research_results": [], "sources_gathered": []}
    
    url = state.input_analysis['url']
    is_arxiv = state.input_analysis.get('is_arxiv', False)
    arxiv_id = state.input_analysis.get('arxiv_id')
    
    print(f"📄 Fetching content from: {url}")
    
    try:
        # Fetch content from URL
        url_content = fetch_url_content_directly(url, is_arxiv=is_arxiv, arxiv_id=arxiv_id)
        
        if url_content:
            # Format as search results for consistency with rest of pipeline
            search_results = {"results": [url_content]}
            
            search_str = deduplicate_and_format_sources(
                search_results, 
                max_tokens_per_source=2000,  # More content for primary source
                fetch_full_page=True
            )
            
            sources = format_sources(search_results)
            
            print(f"✅ Content extracted ({len(url_content.get('content', ''))[:50]}...)")
            
            # Store the URL content as the first research result
            # The research loop will continue to gather additional related information
            return {
                "web_research_results": [search_str],
                "sources_gathered": [sources],
                "research_loop_count": 0  # Keep at 0 so research loop continues
            }
        else:
            print(f"❌ Failed to extract content from {url}")
            return {"web_research_results": [], "sources_gathered": []}
            
    except Exception as e:
        print(f"❌ Error fetching URL content: {str(e)}")
        return {"web_research_results": [], "sources_gathered": []}

def web_research(state: SummaryState, config: RunnableConfig):
    """LangGraph node that performs web research using multiple search strategies.
    
    Uses either SearXNG for web search or MCP for ArXiv paper search to gather
    comprehensive information for research reports.
    
    Args:
        state: Current graph state containing search query, strategy, and research loop count
        config: Configuration for the runnable, including search API settings
        
    Returns:
        Dictionary with state update, including sources_gathered, research_loop_count, and web_research_results
    """

    # Log research initiation
    print(f"🔄 Research Loop {state.research_loop_count + 1} - {state.search_strategy}")
    print(f"🔍 Query: {state.search_query}")
    
    # Configure
    configurable = Configuration.from_runnable_config(config)
    
    try:
        # Determine search strategy based on configuration
        search_api = get_config_value(configurable.search_api)
        
        if search_api == "mcp":
            print("🔬 Using MCP search for ArXiv papers")
            search_results = parallel_search_coordinator(
                state.search_query,
                search_strategy="mcp",
                max_results=8,
                fetch_full_page=configurable.fetch_full_page,
                mcp_server_url=configurable.arxiv_mcp_server_url
            )
        else:
            print("🌐 Using SearXNG web search")
            search_results = parallel_search_coordinator(
                state.search_query,
                search_strategy="web_search",
                max_results=8,
                fetch_full_page=configurable.fetch_full_page
            )
        
        # Format search results
        search_str = deduplicate_and_format_sources(
            search_results, 
            max_tokens_per_source=1000, 
            fetch_full_page=configurable.fetch_full_page
        )
        # Process results for return
        sources = format_sources(search_results)
        
        print(f"✅ Research loop {state.research_loop_count + 1} completed")
        
        return {
            "sources_gathered": [sources], 
            "research_loop_count": state.research_loop_count + 1, 
            "web_research_results": [search_str]
        }
        
    except Exception as e:
        print(f"❌ Search failed, using fallback: {str(e)}")
        # Fallback to basic SearXNG
        search_results = searxng_search(state.search_query, max_results=3, fetch_full_page=configurable.fetch_full_page)
        search_str = deduplicate_and_format_sources(search_results, max_tokens_per_source=1000, fetch_full_page=configurable.fetch_full_page)
        
        return {
            "sources_gathered": [format_sources(search_results)], 
            "research_loop_count": state.research_loop_count + 1, 
            "web_research_results": [search_str]
        }

def summarize_sources(state: SummaryState, config: RunnableConfig):
    """LangGraph node that summarizes web research results and tool outputs.
    
    Uses an LLM to create or update a running summary based on the newest web research 
    results and tool execution results, integrating them with any existing summary.
    
    Args:
        state: Current graph state containing research topic, running summary,
              web research results, and tool results
        config: Configuration for the runnable, including LLM provider settings
        
    Returns:
        Dictionary with state update, including running_summary key containing the updated summary
    """

    print("📝 Summarizing research findings and tool results...")
    
    # Existing summary
    existing_summary = state.running_summary

    # Most recent web research
    most_recent_web_research = state.web_research_results[-1] if state.web_research_results else ""
    
    # Include tool results and enhanced context
    tool_context = ""
    if state.tool_results:
        tool_context += "\n<Tool Results>\n"
        for tool_result in state.tool_results:
            tool_context += f"Tool: {tool_result.get('tool_name', 'Unknown')}\n"
            tool_context += f"Result: {str(tool_result.get('result', ''))[:500]}...\n\n"
        tool_context += "</Tool Results>\n"
    
    if state.enhanced_context:
        tool_context += f"\n<Enhanced Context>\n{state.enhanced_context}\n</Enhanced Context>\n"

    # Build the human message
    if existing_summary:
        human_message_content = (
            f"<Existing Summary> \n {existing_summary} \n <Existing Summary>\n\n"
            f"<New Web Research> \n {most_recent_web_research} \n </New Web Research>\n\n"
            f"{tool_context}"
            f"Update the Existing Summary with the New Web Research and Tool Results on this topic: \n <User Input> \n {state.research_topic} \n <User Input>\n\n"
        )
    else:
        human_message_content = (
            f"<Web Research Context> \n {most_recent_web_research} \n </Web Research Context>\n\n"
            f"{tool_context}"
            f"Create a Summary using the Web Research Context and Tool Results on this topic: \n <User Input> \n {state.research_topic} \n <User Input>\n\n"
        )

    # Run the LLM
    configurable = Configuration.from_runnable_config(config)
    
    # Choose the appropriate LLM based on the provider
    if configurable.llm_provider == "openai_compatible":
        llm = ChatOpenAICompatible(
            base_url=configurable.openai_compatible_base_url,
            model=configurable.local_llm,
            temperature=0,
            api_key=configurable.openai_compatible_api_key,
            # max_tokens=8192
        )
    else:  # Default to Ollama
        llm = ChatOllama(
            base_url=configurable.ollama_base_url, 
            model=configurable.local_llm, 
            temperature=0
        )
    
    # Format the summarizer instructions with research topic for language detection
    formatted_summarizer_instructions = summarizer_instructions.format(
        research_topic=state.research_topic
    )
    
    result = llm.invoke(
        [SystemMessage(content=formatted_summarizer_instructions),
        HumanMessage(content=human_message_content)]
    )

    # Strip thinking tokens if configured
    running_summary = result.content
    if configurable.strip_thinking_tokens:
        running_summary = strip_thinking_tokens(running_summary)

    return {"running_summary": running_summary}

def generate_verification_questions(state: SummaryState, config: RunnableConfig):
    """LangGraph node that generates verification questions for chain of verification.
    
    Analyzes the current research summary to generate specific verification questions
    that can help validate key claims and findings through targeted searches.
    
    Args:
        state: Current graph state containing the research topic and running summary
        config: Configuration for the runnable, including LLM provider settings
        
    Returns:
        Dictionary with state update, including verification_questions
    """
    
    # Temporarily disable verification to avoid irrelevant questions
    print(f"Skipping verification questions generation for now...")
    return {"verification_questions": []}
    
    # Only generate verification questions if we have a summary and haven't done verification yet
    if not state.running_summary or state.verification_questions:
        return {"verification_questions": []}
    
    print(f"Generating verification questions for topic: {state.research_topic}")
    print(f"Summary length: {len(state.running_summary)} chars")
    print(f"Summary preview: {state.running_summary[:200]}...")
    
    # Configure LLM
    configurable = Configuration.from_runnable_config(config)
    
    # Choose the appropriate LLM based on the provider
    if configurable.llm_provider == "openai_compatible":
        llm_json_mode = ChatOpenAICompatible(
            base_url=configurable.openai_compatible_base_url,
            model=configurable.local_llm,
            temperature=0,
            format="json",
            api_key=configurable.openai_compatible_api_key,
        )
    else: # Default to Ollama
        llm_json_mode = ChatOllama(
            base_url=configurable.ollama_base_url, 
            model=configurable.local_llm, 
            temperature=0, 
            format="json"
        )
    
    # Format the prompt
    formatted_prompt = chain_of_verification_instructions.format(
        research_topic=state.research_topic,
        current_summary=state.running_summary
    )
    
    result = llm_json_mode.invoke([
        SystemMessage(content=formatted_prompt),
        HumanMessage(content="Generate verification questions for the research summary.")
    ])
    
    # Parse the JSON response
    try:
        content = result.content.strip()
        # Try to extract JSON if it's embedded in other text
        if content and not content.startswith('{'):
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                content = content[json_start:json_end]
        
        verification_data = json.loads(content)
        questions = verification_data.get('verification_questions', [])
        
        return {"verification_questions": questions}
        
    except (json.JSONDecodeError, KeyError, TypeError):
        print("Failed to parse verification questions, skipping verification")
        return {"verification_questions": []}

def verify_research_claims(state: SummaryState, config: RunnableConfig):
    """LangGraph node that conducts targeted searches to verify research claims.
    
    Takes verification questions and conducts focused searches to validate
    key claims and findings from the research summary.
    
    Args:
        state: Current graph state containing verification questions
        config: Configuration for the runnable, including search API settings
        
    Returns:
        Dictionary with state update, including verification_results
    """
    
    # Skip verification claims for direct content requests to prevent background processing
    if state.search_strategy == "url_fetch" and state.input_analysis.get('direct_fetch', False):
        print(f"Direct content request: skipping verification claims to prevent background searches")
        return {"verification_results": []}
    
    if not state.verification_questions:
        return {"verification_results": []}
    
    configurable = Configuration.from_runnable_config(config)
    verification_results = []
    
    # Limit to first 3 verification questions to avoid excessive searches
    for i, question in enumerate(state.verification_questions[:3]):
        try:
            print(f"Verifying claim {i+1}: {question}")
            
            # Use parallel search for verification with focused results
            search_results = parallel_search_coordinator(
                question, 
                "web_search",  # Use web search for verification
                max_results=2,  # Fewer results for verification
                fetch_full_page=configurable.fetch_full_page
            )
            
            # Format verification result
            search_str = deduplicate_and_format_sources(
                search_results, 
                max_tokens_per_source=500,  # Shorter content for verification
                fetch_full_page=configurable.fetch_full_page
            )
            
            verification_result = {
                "question": question,
                "search_results": search_str,
                "sources": format_sources(search_results)
            }
            
            verification_results.append(verification_result)
            
        except Exception as e:
            print(f"Verification search failed for question {i+1}: {str(e)}")
            # Continue with other questions even if one fails
            continue
    
    return {"verification_results": verification_results}

def synthesize_with_verification(state: SummaryState, config: RunnableConfig):
    """LangGraph node that synthesizes research with verification results.
    
    Uses Chain of Verification approach to update the research summary by
    incorporating verification results, correcting inaccuracies, and adding
    confidence indicators to claims.
    
    Args:
        state: Current graph state containing original summary and verification results
        config: Configuration for the runnable, including LLM provider settings
        
    Returns:
        Dictionary with state update, including updated running_summary
    """
    
    # Skip verification synthesis for direct content requests to prevent background processing
    if state.search_strategy == "url_fetch" and state.input_analysis.get('direct_fetch', False):
        print(f"Direct content request: skipping verification synthesis to prevent background chat completions")
        return {"running_summary": state.running_summary}
    
    # Skip if no verification results
    if not state.verification_results:
        return {"running_summary": state.running_summary}
    
    # Configure LLM
    configurable = Configuration.from_runnable_config(config)
    
    # Choose the appropriate LLM based on the provider
    if configurable.llm_provider == "openai_compatible":
        llm = ChatOpenAICompatible(
            base_url=configurable.openai_compatible_base_url,
            model=configurable.local_llm,
            temperature=0.1,
            api_key=configurable.openai_compatible_api_key,
        )
    else:  # Default to Ollama
        llm = ChatOllama(
            base_url=configurable.ollama_base_url, 
            model=configurable.local_llm, 
            temperature=0.1
        )
    
    # Format verification results for context
    verification_context = ""
    for i, result in enumerate(state.verification_results, 1):
        verification_context += f"\n--- Verification {i} ---\n"
        verification_context += f"Question: {result['question']}\n"
        verification_context += f"Findings: {result['search_results']}\n"
    
    # Format the system prompt
    formatted_prompt = verification_synthesis_instructions.format(
        research_topic=state.research_topic,
        summary_length=len(state.running_summary)
    )
    
    # Create human message with original summary and verification results
    human_message_content = f"""
<ORIGINAL_SUMMARY>
{state.running_summary}
</ORIGINAL_SUMMARY>

<VERIFICATION_RESULTS>
{verification_context}
</VERIFICATION_RESULTS>

Please synthesize the original summary with the verification results to create an improved, more accurate summary with appropriate confidence indicators.
"""

    result = llm.invoke([
        SystemMessage(content=formatted_prompt),
        HumanMessage(content=human_message_content)
    ])

    # Strip thinking tokens if configured
    verified_summary = result.content
    if configurable.strip_thinking_tokens:
        verified_summary = strip_thinking_tokens(verified_summary)

    return {"running_summary": verified_summary}

def reflect_on_summary(state: SummaryState, config: RunnableConfig):
    """LangGraph node that identifies knowledge gaps and generates follow-up queries.
    
    Analyzes the current summary to identify areas for further research and generates
    a new search query to address those gaps. Uses structured output to extract
    the follow-up query in JSON format.
    
    Args:
        state: Current graph state containing the running summary and research topic
        config: Configuration for the runnable, including LLM provider settings
        
    Returns:
        Dictionary with state update, including search_query key containing the generated follow-up query
    """

    # Skip reflection for direct content requests to prevent background processing
    if state.search_strategy == "url_fetch" and state.input_analysis.get('direct_fetch', False):
        print(f"📋 Skipping reflection for direct content request")
        return {"search_query": ""}
    
    # Generate a query
    configurable = Configuration.from_runnable_config(config)
    
    # Choose the appropriate LLM based on the provider
    if configurable.llm_provider == "openai_compatible":
        llm_json_mode = ChatOpenAICompatible(
            base_url=configurable.openai_compatible_base_url,
            model=configurable.local_llm,
            temperature=0,
            format="json",
            api_key=configurable.openai_compatible_api_key,
            # max_tokens=8192
        )
    else: # Default to Ollama
        llm_json_mode = ChatOllama(
            base_url=configurable.ollama_base_url, 
            model=configurable.local_llm, 
            temperature=0, 
            format="json"
        )
    
    # Format the reflection prompt with summaries
    formatted_reflection_prompt = reflection_instructions.format(
        research_topic=state.research_topic,
        summaries=state.running_summary
    )
    
    result = llm_json_mode.invoke(
        [SystemMessage(content=formatted_reflection_prompt),
        HumanMessage(content=f"Analyze the summary and generate a follow-up query that stays focused on the original research topic: {state.research_topic}")]
    )
    
    # Strip thinking tokens if configured
    try:
        # Clean the content first - remove any leading/trailing whitespace
        content = result.content.strip()
        # Try to extract JSON if it's embedded in other text
        if content and not content.startswith('{'):
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                content = content[json_start:json_end]
        
        # Try to parse as JSON first
        reflection_content = json.loads(content)
        
        # Check if more research is needed
        is_sufficient = reflection_content.get('is_sufficient', False)
        if is_sufficient:
            return {"search_query": ""}  # No more research needed
        
        # Get the follow-up queries (can be list or single query)
        follow_up_queries = reflection_content.get('follow_up_queries', [])
        if isinstance(follow_up_queries, list) and follow_up_queries:
            query = follow_up_queries[0]  # Take the first query
        elif isinstance(follow_up_queries, str):
            query = follow_up_queries
        else:
            query = None
        
        # Check if query is None or empty
        if not query:
            # Use a fallback query focused on original topic
            return {"search_query": f"More information about {state.research_topic}"}
        return {"search_query": query}
    except (json.JSONDecodeError, KeyError, AttributeError, TypeError):
        # If parsing fails or the key is not found, use a fallback query
        return {"search_query": f"Tell me more about {state.research_topic}"}
        
def finalize_summary(state: SummaryState, config: RunnableConfig):
    """LangGraph node that generates a comprehensive research report.
    
    Uses an LLM to create a professional research report based on all gathered
    research data, running summary, and sources. The report includes executive
    summary, key findings, methodology, and properly formatted sources.
    
    Args:
        state: Current graph state containing research data and sources
        config: Configuration for the runnable, including LLM provider settings
        
    Returns:
        Dictionary with state update, including running_summary key containing the final report
    """

    print("📊 Generating final research report...")
    
    # Debug: Print what data is being sent to final report generation
    print("=" * 80)
    print("🔍 FINAL REPORT GENERATION DEBUG:")
    print(f"📊 Research Topic: {state.research_topic}")
    print(f"📊 Running Summary Length: {len(state.running_summary) if state.running_summary else 0} chars")
    print(f"📊 Web Research Results: {len(state.web_research_results)} rounds")
    print(f"📊 Sources Gathered: {len(state.sources_gathered)} sources")
    print(f"📊 Tool Results: {len(state.tool_results) if state.tool_results else 0} results")
    
    # Deduplicate sources before processing
    seen_sources = set()
    unique_sources = []
    
    for source in state.sources_gathered:
        # Split the source into lines and process each individually
        for line in source.split('\n'):
            # Only process non-empty lines
            if line.strip() and line not in seen_sources:
                seen_sources.add(line)
                unique_sources.append(line)
    
    print(f"📊 Unique Sources After Deduplication: {len(unique_sources)}")
    
    # Show first few sources for debugging
    if unique_sources:
        print("📊 First 3 Sources:")
        for i, source in enumerate(unique_sources[:3]):
            print(f"  {i+1}. {source}")
    
    # Show tool results if any
    if state.tool_results:
        print("📊 Tool Results:")
        for i, result in enumerate(state.tool_results):
            print(f"  Tool {i+1}: {type(result)} - {str(result)[:100]}...")
    
    # Extract sources from tool results (especially ArXiv)
    tool_sources = []
    if state.tool_results:
        print("🔍 Processing tool results for sources...")
        for i, result in enumerate(state.tool_results):
            print(f"  Tool result {i}: {type(result)}")
            
            # Handle different result structures
            if isinstance(result, dict):
                # Check for direct sources key
                if "sources" in result:
                    print(f"    Found 'sources' key with {len(result['sources'])} sources")
                    for source in result["sources"]:
                        if isinstance(source, dict):
                            # Format ArXiv source
                            title = source.get("title", "ArXiv Paper")
                            url = source.get("url", "")
                            source_type = source.get("type", "unknown")
                            if url:
                                if source_type == "arxiv":
                                    formatted_source = f"**{title}**: [{url}]({url}) (ArXiv Paper)"
                                else:
                                    formatted_source = f"**{title}**: [{url}]({url})"
                                tool_sources.append(formatted_source)
                                print(f"      Added ArXiv source: {title}")
                
                # Check for papers with URLs (direct ArXiv result format)
                elif "papers" in result:
                    print(f"    Found 'papers' key with {len(result['papers'])} papers")
                    for paper in result["papers"]:
                        if isinstance(paper, dict) and "url" in paper:
                            title = paper.get("title", "ArXiv Paper")
                            url = paper["url"]
                            formatted_source = f"**{title}**: [{url}]({url}) (ArXiv Paper)"
                            tool_sources.append(formatted_source)
                            print(f"      Added ArXiv paper: {title}")
                
                # Check for ToolExecution result format
                elif "result" in result:
                    print(f"    Checking 'result' key...")
                    inner_result = result["result"]
                    if isinstance(inner_result, dict):
                        if "sources" in inner_result:
                            print(f"      Found nested 'sources' with {len(inner_result['sources'])} sources")
                            for source in inner_result["sources"]:
                                if isinstance(source, dict):
                                    title = source.get("title", "ArXiv Paper")
                                    url = source.get("url", "")
                                    source_type = source.get("type", "unknown")
                                    if url:
                                        if source_type == "arxiv":
                                            formatted_source = f"**{title}**: [{url}]({url}) (ArXiv Paper)"
                                        else:
                                            formatted_source = f"**{title}**: [{url}]({url})"
                                        tool_sources.append(formatted_source)
                                        print(f"        Added nested ArXiv source: {title}")
                        elif "papers" in inner_result:
                            print(f"      Found nested 'papers' with {len(inner_result['papers'])} papers")
                            for paper in inner_result["papers"]:
                                if isinstance(paper, dict) and "url" in paper:
                                    title = paper.get("title", "ArXiv Paper")
                                    url = paper["url"]
                                    formatted_source = f"**{title}**: [{url}]({url}) (ArXiv Paper)"
                                    tool_sources.append(formatted_source)
                                    print(f"        Added nested ArXiv paper: {title}")
                
                print(f"    Tool result keys: {list(result.keys())}")
            else:
                print(f"    Non-dict result: {str(result)[:100]}")
    
    # Add tool sources to unique sources
    for tool_source in tool_sources:
        if tool_source not in seen_sources:
            unique_sources.append(tool_source)
            seen_sources.add(tool_source)
    
    print(f"📊 Tool Sources Found: {len(tool_sources)}")
    if tool_sources:
        print("📊 Tool Sources:")
        for i, source in enumerate(tool_sources):
            print(f"  {i+1}. {source}")
    
    print("=" * 80)
    
    # Prepare context for the LLM
    current_date = get_current_date()
    
    # Format all web research results for context
    all_research_context = "\n\n".join([
        f"<Research Round {i+1}>\n{result}\n</Research Round {i+1}>"
        for i, result in enumerate(state.web_research_results)
    ])
    
    # Format sources for context (now includes tool sources)
    sources_context = "\n".join(unique_sources) if unique_sources else "No specific sources available."
    
    # Create the human message with all research context
    human_message_content = f"""
<RESEARCH_SUMMARY>
{state.running_summary}
</RESEARCH_SUMMARY>

<WEB_RESEARCH_RESULTS>
{all_research_context}
</WEB_RESEARCH_RESULTS>

<SOURCES>
{sources_context}
</SOURCES>

Please generate a comprehensive research report based on this information. The report should synthesize all the research data into a professional document with proper analysis and insights.
"""

    # Format the system prompt
    formatted_prompt = report_generation_instructions.format(
        research_topic=state.research_topic,
        current_date=current_date,
        research_loop_count=state.research_loop_count
    )

    # Get the LLM configuration
    configurable = Configuration.from_runnable_config(config)
    
    # Choose the appropriate LLM based on the provider
    if configurable.llm_provider == "openai_compatible":
        llm = ChatOpenAICompatible(
            base_url=configurable.openai_compatible_base_url,
            model=configurable.local_llm,
            temperature=0.3,
            api_key=configurable.openai_compatible_api_key,
        )
    else:  # Default to Ollama
        llm = ChatOllama(
            base_url=configurable.ollama_base_url, 
            model=configurable.local_llm, 
            temperature=0.3
        )
    
    # Generate the report using the LLM
    result = llm.invoke([
        SystemMessage(content=formatted_prompt),
        HumanMessage(content=human_message_content)
    ])

    # Strip thinking tokens if configured
    generated_report = result.content
    if configurable.strip_thinking_tokens:
        generated_report = strip_thinking_tokens(generated_report)

    # Ensure sources section is properly formatted for artifact display
    # Check for various source section formats and standardize them
    sources_patterns = ["### Sources:", "## Sources", "Sources & References", "### Sources & References", "Sources:", "## Sources:"]
    
    # Standardize sources section format
    for pattern in sources_patterns:
        if pattern in generated_report:
            generated_report = generated_report.replace(pattern, "### Sources:")
            break
    
    # Use only the LLM-generated content (now with standardized sources format)
    final_report_sections = []
    final_report_sections.append(generated_report)
    
    # If no sources section exists but we have sources to add
    if not any(pattern in generated_report for pattern in ["### Sources:"]) and unique_sources:
        final_report_sections.append("")
        final_report_sections.append("### Sources:")
        final_report_sections.append("")
        
        # Format sources properly for artifact display
        for source in unique_sources:
            if source.strip():
                source_line = source.strip()
                if ':' in source_line and any(protocol in source_line for protocol in ['http://', 'https://', 'www.']):
                    parts = source_line.split(':', 1)
                    if len(parts) == 2:
                        title = parts[0].strip()
                        url = parts[1].strip()
                        
                        # Determine reliability and source type based on URL
                        reliability = "Medium"
                        source_type = "Web Source"
                        
                        if 'arxiv.org' in url:
                            reliability = "High"
                            source_type = "Peer-Reviewed Preprint"
                        elif any(domain in url for domain in ['ieee.org', 'acm.org', 'nature.com', 'science.org']):
                            reliability = "High" 
                            source_type = "Academic Publication"
                        elif any(domain in url for domain in ['github.com', 'docs.', 'readthedocs.']):
                            reliability = "Medium"
                            source_type = "Technical Documentation"
                        elif any(domain in url for domain in ['medium.com', 'blog']):
                            reliability = "Medium"
                            source_type = "Blog Post"
                        elif any(domain in url for domain in ['news', 'reuters', 'bloomberg']):
                            reliability = "Medium"
                            source_type = "News Source"
                        
                        final_report_sections.append(f"* **{title}**: {url} (Reliability: {reliability} - {source_type})")
                    else:
                        final_report_sections.append(f"* {source_line}")
                else:
                    final_report_sections.append(f"* {source_line}")
    
    # Add report footer if not already included
    if "---" not in generated_report:
        final_report_sections.append("")
        final_report_sections.append("---")
        final_report_sections.append("")
        final_report_sections.append("*This research report was generated using automated deep research techniques. ")
        final_report_sections.append("The information presented is based on publicly available sources and should be ")
        final_report_sections.append("verified for critical applications.*")
    
    # Join all sections
    final_report = '\n'.join(final_report_sections)
    
    return {"running_summary": final_report}

def route_research(state: SummaryState, config: RunnableConfig) -> Literal["finalize_summary", "web_research"]:
    """LangGraph routing function that determines the next step in the research flow.
    
    Controls the research loop by deciding whether to continue gathering information
    or to finalize the summary based on the configured maximum number of research loops.
    For URL fetches, limits research to avoid excessive background processing.
    
    Args:
        state: Current graph state containing the research loop count
        config: Configuration for the runnable, including max_web_research_loops setting
        
    Returns:
        String literal indicating the next node to visit ("web_research" or "finalize_summary")
    """

    configurable = Configuration.from_runnable_config(config)
    
    # For URL fetch strategies, limit research loops to avoid excessive background processing
    if state.search_strategy == "url_fetch":
        # If user provided a direct URL with explanation request, don't do additional research
        if state.input_analysis.get('direct_fetch', False):
            max_loops = 0  # No additional research for direct content requests
            print(f"📋 Direct URL content request: skipping additional research loops")
        else:
            max_loops = min(configurable.max_web_research_loops, 1)  # Limit to 1 loop for URL fetches
            print(f"🔗 URL fetch mode: limiting research to {max_loops} loops (current: {state.research_loop_count})")
    else:
        max_loops = configurable.max_web_research_loops
    
    # Fix loop termination: research_loop_count starts at 0, so check < max_loops instead of <=
    if state.research_loop_count < max_loops:
        print(f"🔄 Continuing research: loop {state.research_loop_count + 1}/{max_loops}")
        return "web_research"
    else:
        print(f"✅ Research complete: {state.research_loop_count}/{max_loops} loops finished")
        return "finalize_summary"

def route_after_intent(state: SummaryState, config: RunnableConfig) -> Literal["fetch_url_content", "tool_enhanced_research"]:
    """Route after intent classification to either fetch URL content first or start with tool-enhanced research."""
    if state.search_strategy in ["url_fetch"]:
        return "fetch_url_content"
    else:
        return "tool_enhanced_research"

def route_after_url_fetch(state: SummaryState, config: RunnableConfig) -> Literal["tool_enhanced_research", "summarize_sources"]:
    """Route after URL fetch to either continue with tool-enhanced research or go straight to summarization."""
    if state.input_analysis.get('direct_fetch', False):
        print("📋 Direct content: proceeding to summarization")
        return "summarize_sources"  # Skip research for direct content requests
    else:
        print("🔗 URL processed: continuing with tool-enhanced research")
        return "tool_enhanced_research"  # Continue with tool-enhanced research for other URL fetches

# Add nodes and edges
builder = StateGraph(SummaryState, input=SummaryStateInput, output=SummaryStateOutput, config_schema=Configuration)
builder.add_node("classify_intent", classify_intent)
builder.add_node("fetch_url_content", fetch_url_content)
builder.add_node("tool_enhanced_research", tool_enhanced_research)
builder.add_node("generate_query", generate_query)
builder.add_node("web_research", web_research)
builder.add_node("summarize_sources", summarize_sources)
builder.add_node("generate_verification_questions", generate_verification_questions)
builder.add_node("verify_research_claims", verify_research_claims)
builder.add_node("synthesize_with_verification", synthesize_with_verification)
builder.add_node("reflect_on_summary", reflect_on_summary)
builder.add_node("finalize_summary", finalize_summary)

def route_after_summarize(state: SummaryState, config: RunnableConfig) -> Literal["generate_verification_questions", "finalize_summary"]:
    """Route after summarization to either do verification or finalize for direct content requests."""
    # Skip verification for URL fetch strategies and direct content requests to prevent background processing
    if (state.search_strategy == "url_fetch" and state.input_analysis.get('direct_fetch', False)) or \
       state.input_analysis.get('direct_fetch', False):
        print("📋 Direct content: proceeding to finalization")
        return "finalize_summary"  # Skip verification for direct content requests
    else:
        return "generate_verification_questions"  # Continue with verification for research

# Add edges with tool-enhanced workflow and chain of verification flow
builder.add_edge(START, "classify_intent")
builder.add_conditional_edges("classify_intent", route_after_intent)
builder.add_conditional_edges("fetch_url_content", route_after_url_fetch)  # Route based on direct_fetch
builder.add_edge("tool_enhanced_research", "generate_query")
builder.add_edge("generate_query", "web_research")
builder.add_edge("web_research", "summarize_sources")
builder.add_conditional_edges("summarize_sources", route_after_summarize)  # Route based on direct_fetch
builder.add_edge("generate_verification_questions", "verify_research_claims")
builder.add_edge("verify_research_claims", "synthesize_with_verification")
builder.add_edge("synthesize_with_verification", "reflect_on_summary")
builder.add_conditional_edges("reflect_on_summary", route_research)
builder.add_edge("finalize_summary", END)

graph = builder.compile()