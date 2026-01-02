
def is_garbage(t):
    if not t: return True
    # 0. Massive single-word garbage (e.g. Base64, Encrypted stream)
    if len(t) > 50 and " " not in t:
        print(f"   -> Detected massive single-word (Len={len(t)})")
        return True
        
    # 1. Repeating chars (e.g. VVV, LLL) - common in lined paper OCR
    import re
    if re.search(r'(.)\1{3,}', t): # 4+ repeated chars (relaxed from 10)
        print("   -> Detected repeated chars")
        return True
        
    # 2. Dictionary check (very basic)
    words = t.lower().split()
    if len(words) > 20:
        common = {'the', 'and', 'a', 'of', 'to', 'in', 'is', 'it', 'for', 'on', 'with', 'as', 'at'}
        hit_rate = sum(1 for w in words if w in common) / len(words)
        if hit_rate < 0.1: # Less than 10% common words = likely garbage/gibberish
            print(f"   -> Low word hit rate: {hit_rate}")
            return True
    return False

garbage_sample = "XJLP5Fj1CrX8SHHNnxUSrSRyVRZ3yPT33R2V7TbKMhpLKOKRafC880h2An3vmMLMCg2iRBvC9xc5wa01UOvJdH_XSttOpfFGGhUk"
garbage_with_newlines = "XJLP5Fj1CrX8SH\nHNnxUSrSRyVRZ3yPT33R2V7TbKMhpLKOKRafC880h2An3vmMLMCg2iRBvC9xc5wa01UOvJdH_XSttOpfFGGhUk"

print(f"Testing Sample 1 (Normal): {is_garbage(garbage_sample)}")
print(f"Testing Sample 2 (Newlines): {is_garbage(garbage_with_newlines)}")
