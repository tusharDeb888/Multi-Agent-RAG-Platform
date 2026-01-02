"""
Air-gap Verification Script.
Scans codebase for external network calls and checks offline configuration.
"""
import os
import re
import sys
from dotenv import load_dotenv

# Load env vars
load_dotenv()

SAFE_DOMAINS = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "w3.org", # XML namespaces
    "schemas.openxmlformats.org" # Office schemas
]

def is_safe_url(url):
    for domain in SAFE_DOMAINS:
        if domain in url:
            return True
    return False

def scan_files(directory, extensions):
    leaks = []
    url_pattern = re.compile(r'https?://[^\s"\'<>]+')
    
    for root, _, files in os.walk(directory):
        if "node_modules" in root or "venv" in root or "__pycache__" in root:
            continue
            
        for file in files:
            if not any(file.endswith(ext) for ext in extensions):
                continue
            
            # Skip build configs and test scripts that might contain dummy URLs
            if file in ["vite.config.js", "verify_security.py", "verify_airgap.py"]:
                continue
                
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    matches = url_pattern.findall(content)
                    for url in matches:
                        if not is_safe_url(url):
                            leaks.append((path, url))
            except Exception as e:
                print(f"Error reading {path}: {e}")
                
    return leaks

def check_env_vars():
    required_vars = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1"
    }
    
    missing = []
    for var, expected in required_vars.items():
        val = os.getenv(var)
        if val != expected:
            missing.append(f"{var} (Expected: {expected}, Got: {val})")
            
    return missing

def main():
    print(">>> STARTING AIR-GAP VERIFICATION <<<")
    
    # 1. Check Codebase
    print("\n[1/2] Scanning Codebase for External URLs...")
    extensions = ['.py', '.js', '.jsx', '.html', '.css']
    leaks = scan_files(".", extensions)
    
    if leaks:
        print(f"⚠️ FOUND {len(leaks)} POTENTIAL EXTERNAL LINKS:")
        for path, url in leaks:
            print(f"  - {path}: {url}")
    else:
        print("✅ No external URLs found in source code.")
        
    # 2. Check Environment
    print("\n[2/2] Checking Offline Environment Configuration...")
    env_issues = check_env_vars()
    
    if env_issues:
        print("⚠️ OFFLINE MODE NOT FULLY ENFORCED:")
        for issue in env_issues:
            print(f"  - {issue}")
        print("Action: Add these to your .env file.")
    else:
        print("✅ Environment is configured for offline mode.")
        
    if not leaks and not env_issues:
        print("\n>>> VERIFICATION PASSED: SYSTEM IS AIR-GAP READY <<<")
    else:
        print("\n>>> VERIFICATION FAILED: ADDRESS ISSUES ABOVE <<<")
        sys.exit(1)

if __name__ == "__main__":
    main()
