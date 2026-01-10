import re

def test_split():
    text = "Dr. Kalam was a great scientist. Mr. Smith agrees with him."
    # Updated Robust Regex (Composite)
    # 1. Dot preceded by 2-letter titles (Mr, Dr, etc) -> Negative Lookbehind
    # 2. Dot preceded by 3-letter (Mrs) -> Negative
    # 3. Dot preceded by 4-letter (Prof) -> Negative
    # 4. Dot lookbehind
    # OR 5. ? or ! lookbehind
    split_pattern = r'(?:(?<!\b(?:Mr|Ms|Dr|Sr|Jr|vs|ex)\.)(?<!\bMrs\.)(?<!\bProf\.)(?<=\.)|(?<=[?!]))\s+(?=[A-Z])'
    sentences = re.split(split_pattern, text)
    
    print(f"Original: {text}")
    print(f"Split result: {sentences}")
    
    if "Dr." in sentences:
        print("❌ BREAKAGE CONFIRMED: Split on 'Dr.'")
    else:
        print("✅ Safe.")

if __name__ == "__main__":
    test_split()
