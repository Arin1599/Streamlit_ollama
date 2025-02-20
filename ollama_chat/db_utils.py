# db_utils.py
import sqlite3
from datetime import datetime
from sentence_transformers import SentenceTransformer
import numpy as np
from uuid import uuid4

class ChatDatabase:
    def __init__(self, db_path="E:\Python\LLM\Streamlit_ollama\ollama_chat\chat_history.db"):
        self.db_path = db_path
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.init_db()
        self.purge_old_data()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY,
                    unique_chat_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    model TEXT NOT NULL,
                    image BLOB,
                    embedding BLOB,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_id_timestamp 
                ON chat_history(unique_chat_id, timestamp)
            """)
            conn.commit()

    def get_embedding(self, text):
        try:
            return self.model.encode(text, convert_to_numpy=True)
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return None

    def store_message(self, unique_chat_id, role, content, model, image=None):
        try:
            # Get embedding and convert to bytes if successful
            embedding = self.get_embedding(content)
            embedding_bytes = embedding.tobytes() if embedding is not None else None
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO chat_history (unique_chat_id, role, content, model, image, embedding) VALUES (?, ?, ?, ?, ?, ?)",
                    (unique_chat_id, role, content, model, image, embedding_bytes)
                )
                conn.commit()
        except Exception as e:
            print(f"Error storing message: {e}")
            # Store message without embedding if there's an error
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO chat_history (unique_chat_id, role, content, model, image) VALUES (?, ?, ?, ?, ?)",
                    (unique_chat_id, role, content, model, image)
                )
                conn.commit()

    def get_chat_history(self, unique_chat_id):
        """
        Get complete chat history for a specific chat ID
        Returns list of tuples: (role, content, image, timestamp)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT role, content, image, timestamp 
                FROM chat_history 
                WHERE unique_chat_id = ? 
                ORDER BY timestamp ASC
                """,
                (unique_chat_id,)
            )
            return cursor.fetchall()

    def get_all_chat_ids(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT DISTINCT ch1.unique_chat_id, 
                       ch1.timestamp,
                       (SELECT content 
                        FROM chat_history ch2 
                        WHERE ch2.unique_chat_id = ch1.unique_chat_id 
                        AND ch2.role = 'user' 
                        ORDER BY ch2.timestamp ASC 
                        LIMIT 1) as first_message
                FROM chat_history ch1
                GROUP BY ch1.unique_chat_id
                ORDER BY ch1.timestamp DESC
            """)
            return cursor.fetchall()

    def get_relevant_context(self, query, unique_chat_id, limit=5):
        try:
            query_embedding = self.get_embedding(query)
            if query_embedding is None:
                return []
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT role, content, embedding FROM chat_history WHERE unique_chat_id = ?",
                    (unique_chat_id,)
                )
                
                results = []
                for row in cursor.fetchall():
                    role, content, emb_bytes = row
                    if emb_bytes:
                        try:
                            emb_array = np.frombuffer(emb_bytes, dtype=np.float32)
                            similarity = np.dot(query_embedding, emb_array) / (
                                np.linalg.norm(query_embedding) * np.linalg.norm(emb_array)
                            )
                            results.append((similarity, role, content))
                        except Exception as e:
                            print(f"Error processing embedding: {e}")
                            continue
                
                results.sort(reverse=True)
                return [(role, content) for _, role, content in results[:limit]]
        except Exception as e:
            print(f"Error getting relevant context: {e}")
            return []
    
    def purge_old_data(self, days=30):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                DELETE FROM chat_history 
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            """, (days,))
            conn.commit()