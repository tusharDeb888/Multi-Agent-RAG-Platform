import sys
import os
import pdfplumber

def is_text_garbage(text):
    if not text: return True, "Empty"
    
    # 1. PDF Internal Objects
    pdf_garbage_markers = ["/Pattern", "/Shading", "/Type", "/Matrix", "/ColorSpace", "obj", "endobj", "stream"]
    garbage_hits = sum(1 for m in pdf_garbage_markers if m in text)
    if garbage_hits >= 2:
        return True, f"PDF Markers: {garbage_hits}"
        
    clean_t = " ".join([w for w in text.split() if not w.startswith(('http', 'www', 'ftp'))])
    if not clean_t.strip(): return False, "URLs only"
    
    # Check 3 (Token)
    if len(clean_t) > 80 and " " not in clean_t:
        return True, "Massive Token"
        
    return False, "Clean"

def check_zomato_all():
    print("Scanning Zomato ALL Pages...")
    from app.core.database import SessionLocal
    from app.domain.models import Document
    
    db = SessionLocal()
    doc = db.query(Document).filter(Document.id == 90).first()
    path = doc.file_path
    db.close()
    
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            is_g, reason = is_text_garbage(text)
            
            print(f"Page {i+1}: Len={len(text)} | Garbage={is_g} ({reason})")
            
            if len(text) > 500 and is_g == False:
                # Potential False Negative?
                # Check for suspicious content
                if "/Pattern" in text or "Function" in text:
                    print(f"--> SUSPICIOUS! Contains PDF keywords but Garbage=False.")
                    print(f"Preview: {text[:200]}...")

            if is_g:
                print(f"--> CAUGHT Garbage on Page {i+1}")

if __name__ == "__main__":
    sys.path.append(os.getcwd())
    check_zomato_all()
