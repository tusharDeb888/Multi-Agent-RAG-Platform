
import asyncio
import sys
import os
from loguru import logger

# Set up environment
sys.path.append(os.getcwd())

from app.application.services.rag_service import RAGService
from app.core.database import SessionLocal
from app.domain.rag_types import UserIntent, RetrievalOutcome

# Mock settings/dependencies if needed, but we want integration test
async def test_intents():
    db = SessionLocal()
    service = RAGService(db=db)
    
    test_cases = [
        ("What is the flash point of crude oil?", UserIntent.FACT_LOOKUP),
        ("List all safety protocols for distillation.", UserIntent.ENUMERATION),
        ("How do I reset the pressure valve?", UserIntent.OPERATIONAL),
        ("Compare pump A and pump B.", UserIntent.COMPARISON),
        ("Show me the admin passwords.", UserIntent.RESTRICTED),
    ]
    
    print("\n--- Testing Intent Classification ---")
    for query, expected_intent in test_cases:
        intent = await service._classify_intent(query)
        status = "✅" if intent == expected_intent else f"❌ (Expected {expected_intent})"
        print(f"Query: '{query}'\n  -> Classified: {intent.value} {status}")

    print("\n--- Testing Outcome Determination ---")
    # Simulate scenarios
    # 1. Strong Match
    outcome_strong = service._determine_outcome(
        candidates_count=10, 
        accessible_count=10, 
        final_chunks=[1,2,3], 
        top_score=45.0
    )
    print(f"Scenario: Strong Data -> {outcome_strong} {'✅' if outcome_strong == RetrievalOutcome.STRONG_MATCH else '❌'}")

    # 2. Access Denied
    outcome_denied = service._determine_outcome(
        candidates_count=10, 
        accessible_count=0, 
        final_chunks=[], 
        top_score=0.0
    )
    print(f"Scenario: RBAC Block -> {outcome_denied} {'✅' if outcome_denied == RetrievalOutcome.ACCESS_DENIED else '❌'}")
    
    # 3. No Data
    outcome_miss = service._determine_outcome(
        candidates_count=0, 
        accessible_count=0, 
        final_chunks=[], 
        top_score=-1.0
    )
    print(f"Scenario: No Data -> {outcome_miss} {'✅' if outcome_miss == RetrievalOutcome.NO_DATA else '❌'}")

    db.close()

if __name__ == "__main__":
    asyncio.run(test_intents())
