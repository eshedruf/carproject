import sqlite3
import hashlib
from Crypto import Random

class UserDB:
    def __init__(self, db_name='users.db'):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                salt BLOB,
                hashed_password BLOB,
                age INTEGER
            )
        ''')
        self.conn.commit()

    def user_exists(self, username):
        self.cursor.execute('SELECT 1 FROM users WHERE username = ?', (username,))
        return self.cursor.fetchone() is not None

    def add_user(self, username, password, age):
        if self.user_exists(username):
            return False
        salt = Random.get_random_bytes(16)
        hashed_password = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        self.cursor.execute('INSERT INTO users (username, salt, hashed_password, age) VALUES (?, ?, ?, ?)',
                            (username, salt, hashed_password, age))
        self.conn.commit()
        return True

    def verify_user(self, username, password):
        self.cursor.execute('SELECT salt, hashed_password FROM users WHERE username = ?', (username,))
        row = self.cursor.fetchone()
        if row is None:
            return False
        salt, stored_hash = row
        hashed_password = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return hashed_password == stored_hash

    def close(self):
        self.conn.close()