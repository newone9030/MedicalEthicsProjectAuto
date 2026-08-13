import sqlite3
conn = sqlite3.connect('survey.db')
c = conn.cursor()
cols = [r[1] for r in c.execute('PRAGMA table_info(cases)')]
print('cases cols:', cols)
rows = c.execute("SELECT id, title FROM cases WHERE title='开放文本框验证案例'").fetchall()
print('rows:', rows)
cid = rows[0][0]
print('q count:', c.execute("SELECT COUNT(*) FROM case_questions WHERE case_id=?", (cid,)).fetchone()[0])
print('resp count:', c.execute("SELECT COUNT(*) FROM responses WHERE case_id=?", (cid,)).fetchone()[0])
print('task_cases count:', c.execute("SELECT COUNT(*) FROM task_cases WHERE case_id=?", (cid,)).fetchone()[0])
c.execute("DELETE FROM response_details WHERE question_id IN (SELECT id FROM case_questions WHERE case_id=?)", (cid,))
c.execute("DELETE FROM responses WHERE case_id=?", (cid,))
c.execute("DELETE FROM task_cases WHERE case_id=?", (cid,))
c.execute("DELETE FROM case_questions WHERE case_id=?", (cid,))
c.execute("DELETE FROM cases WHERE id=?", (cid,))
conn.commit()
print('after cleanup cases:', c.execute("SELECT COUNT(*) FROM cases WHERE title='开放文本框验证案例'").fetchone()[0])
conn.close()
