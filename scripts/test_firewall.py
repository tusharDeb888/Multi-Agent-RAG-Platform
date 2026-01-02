"""
Test Prompt Firewall Redaction.
"""
from app.core.prompt_firewall import PromptFirewall

def test_firewall():
    fw = PromptFirewall()
    
    # Test Cases
    cases = [
        ("My email is bob@example.com", "My email is [EMAIL REDACTED]"),
        ("Call me at 9876543210", "Call me at [PHONE REDACTED]"),
        ("My PAN is ABCDE1234F", "My PAN is [PAN REDACTED]"),
        ("Aadhaar: 1234 5678 9012", "Aadhaar: [UID REDACTED]"), # regex expects space
        ("CC: 1234-1234-1234-1234", "CC: [CREDIT_CARD REDACTED]"),
        ("Safe text here", "Safe text here")
    ]
    
    print("Running Prompt Firewall Tests...")
    failures = 0
    for original, expected in cases:
        sanitized = fw.sanitize(original)
        if sanitized != expected:
            print(f"❌ FAIL: '{original}' -> '{sanitized}' (Expected: '{expected}')")
            failures += 1
        else:
            print(f"✅ PASS: '{original}' -> '{sanitized}'")
            
    if failures == 0:
        print("\nAll Firewall Tests Passed!")
    else:
        print(f"\n{failures} Tests Failed.")
        exit(1)

if __name__ == "__main__":
    test_firewall()
