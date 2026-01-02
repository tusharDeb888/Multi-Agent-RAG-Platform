"""
Test splitter.
"""
from app.document_processing.splitter import RecursiveCharacterTextSplitter

def test_recursive_splitter():
    text = "Paragraph 1.\n\nParagraph 2 is longer and has more words to test the splitting capability of our new splitter class. It should hopefully work well.\n\nParagraph 3."
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=50,
        chunk_overlap=10
    )
    
    chunks = splitter.split_text(text)
    
    print(f"Original text length: {len(text)}")
    print(f"Number of chunks: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        print(f"Chunk {i}: {len(chunk)} chars")
        print(f"---\n{chunk}\n---")
        
    assert len(chunks) > 0
    assert all(len(c) <= 50 for c in chunks)
    
if __name__ == "__main__":
    test_recursive_splitter()
