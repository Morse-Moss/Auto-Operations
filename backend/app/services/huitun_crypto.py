from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

HUITUN_EXT_DATA_AES_KEY = b"N7xP4mK9sQ2vL8cD"
HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE = "灰豚候选词解密失败，请先使用手工导入。"


def _unpad_pkcs7(value: bytes) -> bytes:
    if not value:
        raise ValueError("empty padded payload")
    padding_length = value[-1]
    if padding_length < 1 or padding_length > 16:
        raise ValueError("invalid padding length")
    if value[-padding_length:] != bytes([padding_length]) * padding_length:
        raise ValueError("invalid padding bytes")
    return value[:-padding_length]


def decrypt_huitun_ext_data(ext_data: str) -> Any:
    """Decrypt Huitun encrypted extData returned by xhsapi.huitun.com.

    Huitun's web client decrypts encrypted responses with AES-ECB/PKCS7 and a
    UTF-8 key embedded in the front-end bundle. Keep this function narrow: it
    only accepts the encrypted extData string and returns the decoded JSON.
    """

    encrypted_text = ext_data.strip().replace(" ", "+")
    if not encrypted_text:
        raise ValueError(HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE)
    try:
        ciphertext = base64.b64decode(encrypted_text)
        decryptor = Cipher(algorithms.AES(HUITUN_EXT_DATA_AES_KEY), modes.ECB()).decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        plaintext = _unpad_pkcs7(padded_plaintext).decode("utf-8")
        return json.loads(plaintext)
    except Exception as exc:
        raise ValueError(HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE) from exc
