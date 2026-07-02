import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.services.llm import classify_query_complexity, generate_with_routing
from config import LLM_CONFIG

async def test():
    print("=== Testing LLM Generation directly ===")
    print(f"Primary model (Complex): {LLM_CONFIG['model']}")
    print(f"Fallback model (Simple): {LLM_CONFIG.get('fallbacks', [])}")
    
    # Test simple (Ollama)
    print("\n[1] Testing SIMPLE query (routing to fallback/Ollama)...")
    try:
        # Empty chunks is fine, just tests the generation
        ans, usage = await generate_with_routing("What is 2+2?", chunks=[])
        print(f"  -> Success!")
        print(f"  -> Model routed to: {usage.get('routed_model')}")
        print(f"  -> Answer: {ans.answer}")
    except Exception as e:
        print(f"  -> FAILED: {e}")
        
    # Test complex (Groq/OpenAI)
    print("\n[2] Testing COMPLEX query (routing to primary model)...")
    try:
        ans, usage = await generate_with_routing("Explain and compare the philosophical implications of 2+2=4.", chunks=[])
        print(f"  -> Success!")
        print(f"  -> Model routed to: {usage.get('routed_model')}")
        print(f"  -> Answer: {ans.answer}")
    except Exception as e:
        print(f"  -> FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test())
