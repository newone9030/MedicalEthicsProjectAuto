import sqlite3

conn = sqlite3.connect('c:/PythonProject/survey.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Check tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print('Tables:', tables)

# Check users
cursor.execute("SELECT id, username, role, status FROM users")
print('Users:')
for r in cursor.fetchall():
    print(f"  {dict(r)}")

# Check counts
for tbl in ['cases', 'tasks', 'responses', 'task_cases']:
    if tbl in tables:
        cursor.execute(f"SELECT COUNT(*) as cnt FROM {tbl}")
        print(f"{tbl} count: {cursor.fetchone()[0]}")

# Test dashboard queries specifically
print("\n--- Testing dashboard queries ---")
try:
    cursor.execute("SELECT COUNT(*) FROM cases")
    print(f"  get_case_count: {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT COUNT(*) FROM tasks")
    print(f"  get_task_count: {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'active'")
    print(f"  get_active_task_count: {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT COUNT(*) FROM responses")
    print(f"  get_response_count: {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'student'")
    print(f"  get_student_count: {cursor.fetchone()[0]}")
    print("\nAll queries successful!")
except Exception as e:
    print(f"  ERROR: {e}")

conn.close()
