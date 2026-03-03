from pwdlib import PasswordHash


pwd_context = PasswordHash.recommended()


def hash(password: str):
    """returns a argon2 hashed string of the input string"""
    return pwd_context.hash(password)


def verifyPwd(plaintext_pwd, hashed_pwd):
    return pwd_context.verify(plaintext_pwd, hashed_pwd)
