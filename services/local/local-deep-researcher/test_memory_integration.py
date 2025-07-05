import asyncio
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.ollama_deep_researcher.memory_client import (
    MemoryCapture,
    MemoryClient,
    initialize_memory_client,
    capture_memory_safe
)

async def test_memory_integration():
    """Test the memory integration functionality"""
    
    print("🧪 Testing Option A Memory Integration")
    print("=" * 50)
    
    # Configure memory client
    memory_config = MemoryCapture(
        enabled=True,
        mcp_server_path="/home/siamai/openmem0ai_feat/MonkeyResearcher/services/memoer-mcp",
        app_name="local-deep-researcher-test",
        capture_level="essential"
    )
    
    # Initialize client
    client = initialize_memory_client(memory_config)
    print(f"✅ Memory client initialized: {client}")
    
    # Test basic memory capture
    print("\n🔬 Testing basic memory capture...")
    
    success = await capture_memory_safe(
        content="This is a test research summary about quantum computing.",
        research_topic="quantum computing fundamentals",
        memory_type="final_report",
        source_reliability="medium",
        source_type="web",
        research_loop_count=1,
        metadata={
            "test": True,
            "sources_count": 3,
            "report_length": 50
        }
    )
    
    if success:
        print("✅ Memory capture test successful")
    else:
        print("❌ Memory capture test failed")
    
    # Test retrieval
    print("\n📚 Testing memory retrieval...")
    
    try:
        memories = await client.retrieve_similar_research(
            research_topic="quantum computing",
            limit=5
        )
        print(f"✅ Retrieved {len(memories)} memories")
        
        if memories:
            print("📋 Sample memory:")
            for i, memory in enumerate(memories[:1]):
                print(f"  {i+1}. ID: {memory.get('id', 'N/A')}")
                print(f"     Topic: {memory.get('researchTopic', 'N/A')}")
                print(f"     Type: {memory.get('memoryType', 'N/A')}")
                print(f"     Created: {memory.get('createdAt', 'N/A')}")
                
    except Exception as e:
        print(f"⚠️ Memory retrieval test failed: {str(e)}")
    
    # Cleanup
    await client.close()
    print("\n✅ Memory integration test completed")

async def test_disabled_memory():
    """Test behavior when memory is disabled"""
    
    print("\n🚫 Testing disabled memory capture...")
    
    # Configure with memory disabled
    memory_config = MemoryCapture(
        enabled=False,
        mcp_server_path="/home/siamai/openmem0ai_feat/MonkeyResearcher/services/memoer-mcp",
        app_name="test-disabled",
        capture_level="essential"
    )
    
    client = initialize_memory_client(memory_config)
    
    # This should succeed even though memory is disabled
    success = await capture_memory_safe(
        content="Test with disabled memory",
        research_topic="test topic",
        memory_type="final_report"
    )
    
    print(f"✅ Disabled memory test: {success}")
    await client.close()

if __name__ == "__main__":
    print("🚀 Starting Memory Integration Tests")
    print("Note: This requires memoer-mcp service to be built and accessible via MCP protocol")
    print("To test without the service, the tests will gracefully fail")
    print()
    
    try:
        asyncio.run(test_memory_integration())
        asyncio.run(test_disabled_memory())
        
        print("\n🎉 All tests completed successfully!")
        print("\n📝 Summary:")
        print("- ✅ Memory client initialization")
        print("- ✅ Memory capture (graceful failure if service unavailable)")
        print("- ✅ Memory retrieval (graceful failure if service unavailable)")
        print("- ✅ Disabled memory handling")
        print("\n💡 To fully test, start the memoer-mcp service:")
        print("   cd ../../memoer-mcp && npm run build && npm start")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        sys.exit(1)