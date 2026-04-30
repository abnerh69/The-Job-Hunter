from cryptography.fernet import Fernet


def encrypt(plaintext: str, key: str) -> str:
    """
    Encrypts a plaintext string using the provided Fernet key.

    Args:
        plaintext: The string to encrypt.
        key: The Fernet key as a base64 encoded string.

    Returns:
        The encrypted ciphertext as a string.
    """
    f = Fernet(key.encode())
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: str) -> str:
    """
    Decrypts a Fernet ciphertext using the provided key.

    Args:
        ciphertext: The encrypted ciphertext as a string.
        key: The Fernet key as a base64 encoded string.

    Returns:
        The decrypted plaintext string.
    """
    f = Fernet(key.encode())
    return f.decrypt(ciphertext.encode()).decode()
