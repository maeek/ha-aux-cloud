"""Utility functions for AUX cloud services."""

from Crypto.Cipher import AES


def encrypt_aes_cbc_zero_padding(iv: bytes, key: bytes, data: bytes) -> bytes:
    """Encrypt data using AES-CBC zero-padding."""
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_data = data
    padded_data += b"\x00" * (AES.block_size - len(data) % AES.block_size)
    return cipher.encrypt(padded_data)
