"""
Verify Encryption Service Integration.
"""
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
from app.domain.models import DocumentChunk
from app.domain.repositories.chunk_repository import ChunkRepository
from app.core.encryption import EncryptionService

def test_encryption_flow():
    settings = get_settings()
    print(f"Encryption Enabled: {settings.enable_encryption}")
    if not settings.enable_encryption:
        print("Skipping test: Encryption disabled.")
        return

    # 1. Test Service Directly
    service = EncryptionService()
    plaintext = "This is a Top Secret Message!"
    print(f"Original: {plaintext}")
    
    ciphertext = service.encrypt(plaintext)
    print(f"Encrypted: {ciphertext[:20]}... (Len: {len(ciphertext)})")
    
    assert ciphertext != plaintext
    assert "Top Secret" not in ciphertext
    
    decrypted = service.decrypt(ciphertext)
    print(f"Decrypted: {decrypted}")
    assert decrypted == plaintext
    print("✅ Service Layer Verified")

    # 2. Test Repository Integration (Mock DB not vital, just method check)
    # We can't easily spin up Oracle here, but we can verify the logic
    # by checking if repo.encryption_service is set.
    
    # Mock session
    class MockSession:
        def add(self, obj): pass
        def commit(self): pass
        def query(self, *args): return self
        def filter(self, *args): return self
        def order_by(self, *args): return self
        def all(self): return []
    
    repo = ChunkRepository(MockSession())
    assert repo.encryption_service is not None
    print("✅ Repository Initialized with EncryptionService")
    
    # Test Add Logic
    chunk = DocumentChunk(
        document_id=1, chunk_index=0, content="Sensitive Data", 
        content_hash="abc"
    )
    repo.add(chunk)
    # Check modification in place
    print(f"Chunk Content in Memory after Add: {chunk.content}")
    assert chunk.content != "Sensitive Data"
    assert len(chunk.content) > 20
    
    # Test Decrypt Helper
    repo._decrypt_chunk(chunk)
    print(f"Chunk Content after Decrypt: {chunk.content}")
    assert chunk.content == "Sensitive Data"
    print("✅ Repository Encrypt/Decrypt Flow Verified")

if __name__ == "__main__":
    try:
        test_encryption_flow()
        print("\nAll Encryption Tests Passed!")
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        sys.exit(1)
