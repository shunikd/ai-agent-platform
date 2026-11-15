import sqlite3, os, json
db_path = os.path.join(os.path.dirname(__file__), 'core', 'adapters', 'data.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute('SELECT role, content FROM short_term_memories WHERE user_id=? AND chat_id=?', ('test_user', 'test_chat'))
rows = cur.fetchall()
print('Short‑term memories:')
for row in rows:
    print(f"{row[0]}: {row[1]}")
conn.close()
