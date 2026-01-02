
import sys
import os
from sqlalchemy import text
from app.core.database import SessionLocal, engine, Base
from app.domain.models import Department

def migrate():
    # Ensure new tables exist (Departments)
    print("Creating new tables (if missing)...")
    Base.metadata.create_all(bind=engine)
    
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            print("Checking schema...")
            
            # 1. Populate Departments from existing data (if any)
            # We use raw SQL because the ORM model for User no longer has 'department' string field
            print("Migrating department names to Departments table...")
            
            # Get distinct departments from Users
            try:
                result = conn.execute(text("SELECT DISTINCT department FROM users WHERE department IS NOT NULL"))
                user_depts = {row[0] for row in result}
            except Exception as e:
                print(f"Could not read users.department: {e}")
                user_depts = set()

            # Get distinct departments from Documents
            try:
                result = conn.execute(text("SELECT DISTINCT department FROM documents WHERE department IS NOT NULL"))
                doc_depts = {row[0] for row in result}
            except Exception as e:
                print(f"Could not read documents.department: {e}")
                doc_depts = set()
                
            all_depts = user_depts.union(doc_depts)
            
            for dept_name in all_depts:
                # Check if exists
                exists = conn.execute(text("SELECT 1 FROM departments WHERE name = :name"), {"name": dept_name}).first()
                if not exists:
                    print(f"Creating Department: {dept_name}")
                    conn.execute(text("INSERT INTO departments (name, description, created_at) VALUES (:name, 'Migrated', CURRENT_TIMESTAMP)"), {"name": dept_name})
            
            # 2. Add department_id columns
            def add_column_if_missing(table, column, col_type):
                try:
                    conn.execute(text(f"SELECT {column} FROM {table} FETCH FIRST 1 ROWS ONLY"))
                except Exception:
                    print(f"Adding column {column} to {table}...")
                    conn.execute(text(f"ALTER TABLE {table} ADD {column} {col_type}"))
            
            # Oracle syntax for ALTER TABLE might vary, but standard SQL usually works.
            # However, adding a Foreign Key constraint usually requires separate step or named constraint.
            # Simplified: Add integer column first.
            
            add_column_if_missing("users", "department_id", "NUMBER")
            add_column_if_missing("documents", "department_id", "NUMBER")
            add_column_if_missing("document_access_policies", "department_id", "NUMBER")
            add_column_if_missing("chunk_access_policies", "department_id", "NUMBER")
            
            # 3. Update department_id values
            print("Updating User department_ids...")
            conn.execute(text("""
                UPDATE users u
                SET department_id = (SELECT d.id FROM departments d WHERE d.name = u.department)
                WHERE department_id IS NULL AND department IS NOT NULL
            """))
            
            print("Updating Document department_ids...")
            conn.execute(text("""
                UPDATE documents doc
                SET department_id = (SELECT d.id FROM departments d WHERE d.name = doc.department)
                WHERE department_id IS NULL AND department IS NOT NULL
            """))

            # 4. Update Policies (simplified - exact logic depends on implementation)
            print("Updating Policy department_ids...")
            conn.execute(text("""
                UPDATE document_access_policies dap
                SET department_id = (SELECT d.id FROM departments d WHERE d.name = dap.department)
                WHERE department_id IS NULL AND department IS NOT NULL
            """))
            
            # 5. Drop old department columns (Cleanup)
            print("Dropping old department columns...")
            def drop_column_if_exists(table, column):
                try:
                    conn.execute(text(f"SELECT {column} FROM {table} FETCH FIRST 1 ROWS ONLY"))
                    print(f"Dropping {column} from {table}...")
                    conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
                except Exception:
                    print(f"Column {column} does not exist in {table} (already dropped).")

            drop_column_if_exists("users", "department")
            drop_column_if_exists("documents", "department")
            drop_column_if_exists("document_access_policies", "department")
            drop_column_if_exists("chunk_access_policies", "department")
             
            trans.commit()
            print("Migration completed successfully!")
            
        except Exception as e:
            trans.rollback()
            print(f"Migration failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    migrate()
