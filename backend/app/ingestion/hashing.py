import hashlib
import re


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_fingerprint(text: str) -> str:
    """Hash of the text ignoring case and whitespace.

    Catches the same resume exported twice as different PDFs, where the
    bytes differ but the content does not.
    """
    canonical = re.sub(r"\s+", " ", text).strip().casefold()
    return sha256_bytes(canonical.encode("utf-8"))
