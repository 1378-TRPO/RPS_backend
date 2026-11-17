from pwdlib import PasswordHash
from pwdlib.exceptions import HashVerificationError, UnknownHashError

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password, password_hash)
    except (HashVerificationError, UnknownHashError):
        return False
