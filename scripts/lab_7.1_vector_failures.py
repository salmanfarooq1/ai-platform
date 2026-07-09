import asyncio
import httpx
import json
import asyncpg
from api.services.cache import embed_query

QUERIES = [
    "GDPR Article 5 data minimization principle",
    "what is the maximum fine under CCPA section 1798.155",
    "HIPAA does NOT apply to which entities",
    "legitimate interest assessment under GDPR recital 47",
    "data breach notification within 72 hours regulatory requirement",
]

API_URL = "http://localhost:8000/search"

async def main():
    # Connect to the DB to simulate exactly what the API does internally
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/rag_platform")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for q in QUERIES:
            print(f"\n{'='*80}\nQUERY: {q}\n{'='*80}")
            
            # --- BOUNDARY 1: DB RETRIEVAL (What the LLM receives) ---
            print(">>> 1. RAW DB RETRIEVAL (`db_chunks` passed to LLM):")
            try:
                query_embedding = await embed_query(q)
                vec_str = '[' + ','.join(map(str, query_embedding)) + ']'
                query_sql = """
                    SELECT document_id, content,
                           embedding <=> $1::vector AS distance
                    FROM documents
                    WHERE namespace = $2
                    ORDER BY distance ASC
                    LIMIT $3;
                """
                records = await conn.fetch(query_sql, vec_str, "legal", 5)
                
                db_chunks = []
                for r in records:
                    db_chunks.append({
                        "document_id": r["document_id"],
                        "content": r["content"],
                        "score": 1.0 - float(r["distance"])
                    })
                
                # Print raw JSON, exactly what goes into `generate_with_routing`
                print(json.dumps(db_chunks, indent=2))
                
            except Exception as e:
                print(f"DB Retrieval Failed: {e}")

            # --- BOUNDARY 2: FINAL API RESPONSE (What the client sees) ---
            print("\n>>> 2. FINAL API RESPONSE (`SearchResponse` from the endpoint):")
            try:
                resp = await client.post(API_URL, json={"query": q, "namespace": "legal", "top_k": 5})
                # Print raw JSON, exactly what the API returns
                print(json.dumps(resp.json(), indent=2))
            except Exception as e:
                print(f"API Failed: {e}")
                
            if q != QUERIES[-1]:
                input("\nPress Enter to run the next query...")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
