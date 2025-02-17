import sqlite3
from datetime import datetime
from sentence_transformers import SentenceTransformer
import numpy as np

class ChatDatabase:
    def __init__(self, db_path="ollama_chat\chat_history.db"):
        self.db_path = db_path
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.init_db()
        self.purge_old_data()  # This will run automatically when the database is initialized

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    role TEXT,
                    content TEXT,
                    model TEXT,
                    image BLOB NULL,
                    embedding BLOB
                )
            """)
            conn.commit()

    def get_embedding(self, text):
        return self.model.encode(text)

    def store_message(self, role, content, model, image=None):
        embedding = self.get_embedding(content)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO chat_history (role, content, model, image, embedding) VALUES (?, ?, ?, ?, ?)",
                (role, content, model, image, embedding.tobytes())
            )
            conn.commit()

    def get_relevant_context(self, query, limit=5):
        query_embedding = self.get_embedding(query)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT role, content, embedding FROM chat_history")
            results = []
            
            for row in cursor.fetchall():
                role, content, emb_bytes = row
                emb_array = np.frombuffer(emb_bytes, dtype=np.float32)
                similarity = np.dot(query_embedding, emb_array) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb_array))
                results.append((similarity, role, content))
            
            # Sort by similarity and get top results
            results.sort(reverse=True)
            return [(role, content) for _, role, content in results[:limit]]
    
    def purge_old_data(self, days=30):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                DELETE FROM chat_history 
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            """, (days,))
            conn.commit()
