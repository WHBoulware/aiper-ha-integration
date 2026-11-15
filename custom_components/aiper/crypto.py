"""Request crypto for the Aiper cloud API.

Reconstructed from ``AINetworkCryptoUtils.swift`` in the Aiper iOS app.

Scheme (best reconstruction — confirm with a live capture):

* A random 16-byte AES key is generated per request.
* The JSON request body is encrypted with AES (see ``AES_MODE``) and placed,
  base64-encoded, in the ``content`` field of the outer JSON envelope.
* The AES key is encrypted with the app's embedded RSA public key
  (PKCS#1 v1.5) and placed, base64-encoded, in the ``aesKey`` field.
* Responses come back in the same envelope and are decrypted with the same
  AES key that was sent.

The two things most likely to differ from a real capture are the AES mode
(CBC vs ECB) and the padding / IV handling. Both are isolated here so you
can flip ``AES_MODE`` / ``AES_IV_MODE`` after one capture instead of
touching the client. ``api.py`` can also run fully unencrypted (plain JSON)
if ``encrypt=False`` — some endpoints in the app are not encrypted.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad

from .const import APP_RSA_PUBLIC_KEY_B64

# "CBC" or "ECB". The app links CryptoSwift; CBC with a zero/prefixed IV is
# the most common choice in this family of apps. Flip to "ECB" if a capture
# shows no IV.
AES_MODE = "CBC"
# "ZERO_IV"  -> 16 zero bytes, not transmitted
# "PREFIX"   -> random IV generated and prepended to ciphertext
AES_IV_MODE = "ZERO_IV"

_BLOCK = 16


def _load_rsa_public() -> RSA.RsaKey:
    der = base64.b64decode(APP_RSA_PUBLIC_KEY_B64)
    return RSA.import_key(der)


def generate_aes_key() -> bytes:
    """A fresh 16-byte AES key for one request."""
    return os.urandom(16)


def rsa_wrap_key(aes_key: bytes) -> str:
    """RSA-encrypt the AES key with the app public key -> base64 str."""
    cipher = PKCS1_v1_5.new(_load_rsa_public())
    return base64.b64encode(cipher.encrypt(aes_key)).decode()


def _aes_encrypt(aes_key: bytes, plaintext: bytes) -> bytes:
    if AES_MODE == "ECB":
        cipher = AES.new(aes_key, AES.MODE_ECB)
        return cipher.encrypt(pad(plaintext, _BLOCK))
    # CBC
    if AES_IV_MODE == "PREFIX":
        iv = os.urandom(_BLOCK)
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        return iv + cipher.encrypt(pad(plaintext, _BLOCK))
    iv = b"\x00" * _BLOCK
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    return cipher.encrypt(pad(plaintext, _BLOCK))


def _aes_decrypt(aes_key: bytes, ciphertext: bytes) -> bytes:
    if AES_MODE == "ECB":
        cipher = AES.new(aes_key, AES.MODE_ECB)
        return unpad(cipher.decrypt(ciphertext), _BLOCK)
    if AES_IV_MODE == "PREFIX":
        iv, ciphertext = ciphertext[:_BLOCK], ciphertext[_BLOCK:]
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ciphertext), _BLOCK)
    iv = b"\x00" * _BLOCK
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ciphertext), _BLOCK)


def encrypt_payload(body: dict[str, Any]) -> tuple[dict[str, str], bytes]:
    """Return (envelope, aes_key).

    ``envelope`` is the dict to POST; ``aes_key`` is kept so the response can
    be decrypted with the same key.
    """
    aes_key = generate_aes_key()
    plaintext = json.dumps(body, separators=(",", ":")).encode()
    content = base64.b64encode(_aes_encrypt(aes_key, plaintext)).decode()
    from .const import ENV_AESKEY, ENV_CONTENT

    envelope = {ENV_CONTENT: content, ENV_AESKEY: rsa_wrap_key(aes_key)}
    return envelope, aes_key


def decrypt_content(aes_key: bytes, content_b64: str) -> dict[str, Any]:
    """Decrypt a base64 ``content`` field back into a dict."""
    raw = _aes_decrypt(aes_key, base64.b64decode(content_b64))
    return json.loads(raw.decode())
