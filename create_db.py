from core.adapters.local_db import SQLiteMemoryStore
store = SQLiteMemoryStore()
store.add_short_term(chat_id='test_chat', user_id='test_user', role='assistant', content='test message')
print('Inserted')