"""
Test Upload Hardening (MIME Validation).
"""
import requests
import os

# Assuming running locally
API_URL = "http://localhost:8000/api/v1" 
# Note: This script assumes auth token is handled or we use a lower level unit test?
# Since we need a running server, unit test is better if we can't auth easily.
# Let's write a unit test style script that imports the validator directly, 
# as running a full HTTP request requires a Token which is hard to get in a script without login flow.

from app.core.scanner import FileValidator, MalwareScanner

def test_validator():
    print("Testing FileValidator...")
    
    # 1. Create a dummy PDF (header %PDF)
    pdf_header = b'%PDF-1.4\n...'
    valid, mime = FileValidator.validate_mime_type(pdf_header, "test.pdf")
    if valid:
        print(f"✅ Safe PDF accepted ({mime})")
    else:
        print(f"❌ Safe PDF Rejected ({mime})")
        
    # 2. Create a spoofed file (EXE header renamed to .pdf)
    # MZ header is for DOS/Windows PE
    exe_header = b'MZ\x90\x00\x03\x00\x00\x00'
    valid, mime = FileValidator.validate_mime_type(exe_header, "report.pdf")
    if not valid:
        print(f"✅ Spoofed EXE correctly blocked ({mime})")
    else:
        print(f"❌ Spoofed EXE allowed! ({mime})")

    # 3. Text file
    txt_header = b'Hello world this is text'
    valid, mime = FileValidator.validate_mime_type(txt_header, "note.txt")
    if valid:
        print(f"✅ Text file accepted ({mime})")
        
    # 4. CSV file (often tricky)
    csv_header = b'col1,col2,col3\nval1,val2,val3'
    valid, mime = FileValidator.validate_mime_type(csv_header, "data.csv")
    if valid:
        print(f"✅ CSV file accepted ({mime})")
        
if __name__ == "__main__":
    test_validator()
