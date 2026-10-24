"""Sealing an API key inside a TA package.

This is obfuscation, not strong secrecy: the app must be able to unlock the key on the TA's
computer in order to use it, so a determined person with the app could recover it. It keeps the
key out of sight (it never appears in plain text in the package, the workspace or the interface)
and stops casual copying. Real limits belong on the OpenAI side: a separate key per TA in a
project with a small budget, revoked at the end of the semester.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

# Fixed application secret mixed with a random per-package salt.
_APP_SECRET = b"MATH241Grader/keyshare/v1/7f3c9a1e5b2d48c6a0e4f1b7d9c3e5a2"


def _stream(salt: bytes, n: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < n:
        out += hashlib.sha256(_APP_SECRET + salt + counter.to_bytes(4, "big")).digest()
        counter += 1
    return out[:n]


def seal(key: str) -> dict:
    salt = os.urandom(16)
    data = key.encode("utf-8")
    ct = bytes(a ^ b for a, b in zip(data, _stream(salt, len(data))))
    tag = hmac.new(_APP_SECRET + salt, ct, hashlib.sha256).digest()[:16]
    return {"salt": base64.b64encode(salt).decode(), "blob": base64.b64encode(ct).decode(),
            "tag": base64.b64encode(tag).decode()}


def unseal(sealed: dict) -> str:
    salt = base64.b64decode(sealed["salt"])
    ct = base64.b64decode(sealed["blob"])
    tag = base64.b64decode(sealed["tag"])
    if not hmac.compare_digest(tag, hmac.new(_APP_SECRET + salt, ct, hashlib.sha256).digest()[:16]):
        raise ValueError("The AI access in this package is damaged.")
    return bytes(a ^ b for a, b in zip(ct, _stream(salt, len(ct)))).decode("utf-8")
