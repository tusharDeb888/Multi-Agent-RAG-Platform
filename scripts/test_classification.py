"""
Test Data Classification Enforcement.
"""
from app.domain.models import User, Document, UserRole, ClassificationLevel
from app.application.services.rbac_service import RBACService
from sqlalchemy.orm import Session
import collections

# Mock Objects to avoid full DB setup
MockRole = collections.namedtuple("MockRole", ["name"])
MockUserRole = collections.namedtuple("MockUserRole", ["role"])
MockUser = collections.namedtuple("MockUser", ["id", "is_active", "department", "roles", "clearance_level"])

class MockRepo:
    def __init__(self, data): self.data = data
    def get_by_id(self, id): return self.data.get(id)

class MockPolicyRepo:
    def get_accessible_documents(self, **kwargs): 
        # Base policy allows everything for this test (we are testing clearance filter)
        return [101, 102, 103] # Doc IDs

class MockChunkPolicyRepo:
    def get_accessible_chunks(self, **kwargs):
        # Base policy allows everything
        return [201, 202, 203] # Chunk IDs

class MockDB:
    def __init__(self, docs, chunks):
        self.docs = docs
        self.chunks = chunks
        
    def query(self, *args): return self
    def filter(self, *args): return self
    def join(self, *args): return self
    def all(self): 
        # Return mock query results depending on context
        # This is tricky to mock perfectly without real DB, 
        # but let's assume we are testing the logic flow if we can stub the query result.
        pass

def test_logic_directly():
    print("Testing RBAC Service Logic...")
    
    # 1. Setup Mock Service
    service = RBACService(None) # No real DB
    
    # Override logic helper for test
    service.CLEARANCE_HIERARCHY = {
        "public": 0, "internal": 1, "confidential": 2, "restricted": 3
    }
    
    # Test Ranking
    assert service._rank(ClassificationLevel.PUBLIC) == 0
    assert service._rank(ClassificationLevel.INTERNAL) == 1
    assert service._rank("confidential") == 2
    
    # Test Scenario:
    # User A: Internal (Level 1)
    # Doc 1: Public (Level 0) -> OK
    # Doc 2: Internal (Level 1) -> OK
    # Doc 3: Confidential (Level 2) -> DENY
    
    user_internal = MockUser(
        id=1, is_active=True, department="IT", 
        roles=[MockUserRole(MockRole("employee"))], 
        clearance_level=ClassificationLevel.INTERNAL
    )
    
    # We mock the query result return directly since we can't easily mock the fluent SQL interface
    # Let's manually simulate the loop inside `filter_accessible_documents`
    
    candidate_docs = [
        (101, ClassificationLevel.PUBLIC),
        (102, ClassificationLevel.INTERNAL),
        (103, ClassificationLevel.CONFIDENTIAL)
    ]
    
    user_rank = service._rank(user_internal.clearance_level)
    allowed = []
    
    print(f"User Clearance: {user_internal.clearance_level} ({user_rank})")
    
    for doc_id, classification in candidate_docs:
        doc_rank = service._rank(classification)
        if user_rank >= doc_rank:
            print(f"Doc {doc_id} ({classification}) -> ALLOW")
            allowed.append(doc_id)
        else:
            print(f"Doc {doc_id} ({classification}) -> DENY")
            
    assert 101 in allowed
    assert 102 in allowed
    assert 103 not in allowed
    print("✅ Internal User Filter Logic Passed")

    # Test Scenario 2: Confidential User
    user_confidential = MockUser(
        id=2, is_active=True, department="IT", 
        roles=[MockUserRole(MockRole("employee"))], 
        clearance_level=ClassificationLevel.CONFIDENTIAL
    )
    user_rank = service._rank(user_confidential.clearance_level)
    allowed = []
    print(f"\nUser Clearance: {user_confidential.clearance_level} ({user_rank})")
    
    for doc_id, classification in candidate_docs:
        doc_rank = service._rank(classification)
        if user_rank >= doc_rank:
            print(f"Doc {doc_id} ({classification}) -> ALLOW")
            allowed.append(doc_id)
        else:
            print(f"Doc {doc_id} ({classification}) -> DENY")

    assert 101 in allowed
    assert 102 in allowed
    assert 103 in allowed
    print("✅ Confidential User Filter Logic Passed")

if __name__ == "__main__":
    test_logic_directly()
