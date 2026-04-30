import pytest
from cryptography.fernet import Fernet
from jobhunter.crypto import encrypt, decrypt


def test_encrypt_decrypt_roundtrip() -> None:
    key = Fernet.generate_key().decode()
    plaintext = "super secret message"

    ciphertext = encrypt(plaintext, key)
    assert ciphertext != plaintext

    decrypted = decrypt(ciphertext, key)
    assert decrypted == plaintext


def test_decrypt_with_wrong_key() -> None:
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()
    plaintext = "sensitive data"

    ciphertext = encrypt(plaintext, key1)

    from cryptography.fernet import InvalidToken

    with pytest.raises(InvalidToken):
        decrypt(ciphertext, key2)


def test_encrypt_returns_different_ciphertexts() -> None:
    key = Fernet.generate_key().decode()
    plaintext = "same message"

    c1 = encrypt(plaintext, key)
    c2 = encrypt(plaintext, key)

    # Fernet includes a timestamp and IV, so identical plaintexts
    # result in different ciphertexts
    assert c1 != c2
    assert decrypt(c1, key) == plaintext
    assert decrypt(c2, key) == plaintext
