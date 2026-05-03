# make_hash.py

import hashlib


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


default_password = "knh1234"

print(hash_password(default_password))