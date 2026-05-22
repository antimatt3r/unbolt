import os
import threading
from typing import List

PRIMARY_PASSWORDS_FILE = "/data/primary_passwords.txt"
USER_PASSWORDS_FILE = "/data/user_passwords.txt"

# Ensure directories and files exist upon initialization
for path in [PRIMARY_PASSWORDS_FILE, USER_PASSWORDS_FILE]:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'a').close()

class PasswordManager:
    def __init__(self):
        # A threading lock to prevent file corruption during parallel requests
        self.lock = threading.Lock()

    def get_all_passwords(self) -> List[str]:
        """Reads and deduplicates passwords from both password files."""
        passwords = []
        for path in [PRIMARY_PASSWORDS_FILE, USER_PASSWORDS_FILE]:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    # Strip whitespace and ignore empty lines
                    passwords.extend([line.strip() for line in f if line.strip()])
        
        # Deduplicate while preserving order
        return list(dict.fromkeys(passwords))

    def add_user_password(self, password: str):
        """Thread-safely appends a new password to the user dictionary."""
        if not password:
            return
            
        with self.lock:
            existing_passwords = self.get_all_passwords()
            if password not in existing_passwords:
                with open(USER_PASSWORDS_FILE, 'a', encoding='utf-8') as f:
                    f.write(password + '\n')

password_manager = PasswordManager()
