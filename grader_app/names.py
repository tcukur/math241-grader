"""Sorting names in Turkish alphabetical order, so Çiçek comes after Can and before Demir, and İnce after Işık.
The database's own ordering only knows the 26 English letters and put every other letter after Z."""
from __future__ import annotations

import unicodedata

_ALPHABET = "abcçdefgğhıijklmnoöpqrsştuüvwxyz"
_RANK = {ch: i for i, ch in enumerate(_ALPHABET)}


def _lower_tr(s: str) -> str:
    # Turkish capitals: I is the capital of dotless ı, İ the capital of i
    return s.replace("I", "ı").replace("İ", "i").lower()


def sort_key(name: str | None) -> tuple:
    s = unicodedata.normalize("NFC", (name or "").strip())
    key = []
    for ch in _lower_tr(s):
        if ch in _RANK:
            key.append((0, _RANK[ch], ""))
        elif ch.isalpha():
            base = unicodedata.normalize("NFD", ch)[0]          # é, á, ñ sort with their base letter
            key.append((0, _RANK.get(base, len(_ALPHABET)), ch))
        elif ch.isdigit():
            key.append((1, int(ch), ""))
        else:
            key.append((-1, 0, ""))                              # spaces and punctuation come first
    return tuple(key)
