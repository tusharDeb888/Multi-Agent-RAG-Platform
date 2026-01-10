import asyncio
import sys
import os
from loguru import logger

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import Individual Test Modules (to be created)
# from scripts.qa_tests import test_ingestion, test_retrieval, test_rag

async def run_suite():
    print("==================================================")
    print("       🚀 STARING DEEP QA AUDIT SUITE 🚀        ")
    print("==================================================\n")
    
    results = {}
    
    # --- Phase 1: Ingestion Stability ---
    print("\n--- Phase 1: Ingestion Stability ---")
    try:
        from scripts import test_splade_memory
        print(">> Running SPLADE Memory Stress Test...")
        test_splade_memory.test_splade_memory()
        results["SPLADE_OOM_Check"] = "PASS"
    except Exception as e:
        print(f"❌ SPLADE Test Failed: {e}")
        results["SPLADE_OOM_Check"] = "FAIL"

    # --- Phase 2: Vector Store Contract ---
    print("\n--- Phase 2: Vector Store Contract ---")
    try:
        from scripts import verify_rag_fix
        print(">> Running Milvus Exact Subset Check...")
        await verify_rag_fix.verify_milvus_fix()
        results["Milvus_Exact_Subset"] = "PASS"
    except Exception as e:
        print(f"❌ Milvus Test Failed: {e}")
        results["Milvus_Exact_Subset"] = "FAIL"

    # --- Phase 3: End-to-End RAG ---
    print("\n--- Phase 3: End-to-End RAG ---")
    try:
        from scripts import verify_zomato_rag
        print(">> Running Zomato Query Verification...")
        await verify_zomato_rag.verify()
        results["RAG_E2E_Zomato"] = "PASS"
    except Exception as e:
        print(f"❌ RAG Test Failed: {e}")
        results["RAG_E2E_Zomato"] = "FAIL"

    print("\n==================================================")
    print("                  📢 FINAL REPORT                 ")
    print("==================================================")
    for test, status in results.items():
        icon = "✅" if status == "PASS" else "❌"
        print(f"{icon} {test}: {status}")
    
    if all(s == "PASS" for s in results.values()):
        print("\n🎉 ALL SYSTEMS GO! The System is BUG FREE regarding recent issues.")
    else:
        print("\n⚠️ SOME TESTS FAILED. Please review logs.")

if __name__ == "__main__":
    asyncio.run(run_suite())
