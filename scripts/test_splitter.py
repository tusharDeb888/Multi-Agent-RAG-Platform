from app.document_processing.splitter import RecursiveCharacterTextSplitter

def test_splitter():
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    
    # 1. Simple text
    text1 = "Hello world. " * 100 # 1300 chars
    chunks1 = splitter.split_text(text1)
    print(f"Test 1 (Simple 1300 chars): {len(chunks1)} chunks")
    for i, c in enumerate(chunks1):
        print(f"  Chunk {i}: len={len(c)}")
        
    # 2. Markdown Table simulation (text with newlines)
    text2 = ("| Header 1 | Header 2 |\n" + "| --- | --- |\n" + "| Val 1 | Val 2 |\n") * 500
    # 500 lines. Each line ~20 chars. Total ~10k chars.
    print(f"\nTest 2 (Table 10k chars): Input Len={len(text2)}")
    chunks2 = splitter.split_text(text2)
    print(f"Test 2 chunks: {len(chunks2)}")
    
    # 3. Massive single word (garbage case?) - though is_garbage should catch, check splitter robustness
    text3 = "A" * 1000
    chunks3 = splitter.split_text(text3)
    print(f"\nTest 3 (Single word 1000 chars): {len(chunks3)} chunks")

if __name__ == "__main__":
    test_splitter()
