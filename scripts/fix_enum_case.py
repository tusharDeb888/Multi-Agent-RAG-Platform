"""
Fix Enum Case Mismatch for Users table.
Converts 'internal' to 'INTERNAL', etc.
"""
from sqlalchemy import create_engine, text
from app.core.config import get_settings

def fix_enum_case():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    
    print(f"Fixing Enum Case in {settings.database_url}...")
    
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Check current values
            res = conn.execute(text("SELECT id, username, clearance_level FROM users")).fetchall()
            print("Current Data:")
            for row in res:
                print(row)
                
            # Update to Upper Case
            print("Updating 'internal' -> 'INTERNAL'...")
            conn.execute(text("UPDATE users SET clearance_level = 'INTERNAL' WHERE clearance_level = 'internal'"))
            conn.execute(text("UPDATE users SET clearance_level = 'PUBLIC' WHERE clearance_level = 'public'"))
            conn.execute(text("UPDATE users SET clearance_level = 'CONFIDENTIAL' WHERE clearance_level = 'confidential'"))
            conn.execute(text("UPDATE users SET clearance_level = 'RESTRICTED' WHERE clearance_level = 'restricted'"))
            
            trans.commit()
            print("Update complete.")
            
        except Exception as e:
            trans.rollback()
            print(f"Update failed: {e}")

if __name__ == "__main__":
    fix_enum_case()
