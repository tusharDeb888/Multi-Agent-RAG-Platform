"""
Check Oracle DB Version.
"""
from sqlalchemy import create_engine, text
from app.core.config import get_settings

def check_version():
    settings = get_settings()
    db_url = settings.database_url
    print(f"Connecting to: {db_url}")
    
    engine = create_engine(db_url)
    with engine.connect() as conn:
        try:
            res = conn.execute(text("SELECT banner FROM v$version")).fetchall()
            print("Oracle Version Banner:")
            for row in res:
                print(row[0])
                
            # Check specifically for 23
            full_ver = "".join([str(r) for r in res])
            if "23c" in full_ver or "23ai" in full_ver or "23." in full_ver:
                print("✅ Likely Oracle 23ai/23c.")
            else:
                print("⚠️ WARNING: Doesn't look like Oracle 23ai.")
        except Exception as e:
            print(f"Error checking version: {e}")

if __name__ == "__main__":
    check_version()
