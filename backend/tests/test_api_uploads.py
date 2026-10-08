import asyncio
import hashlib
import io
import re

import pytest
from starlette.datastructures import UploadFile

from app.api.uploads import UploadError, sanitize_display_name, stored_uploads


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("cv.pdf", "cv.pdf"),
        ("../../something.pdf", "something.pdf"),
        ("../../../etc/passwd", "etc/passwd"),
        ("/etc/passwd", "etc/passwd"),
        ("..\\..\\windows\\system32\\x.pdf", "windows/system32/x.pdf"),
        ("C:\\Users\\me\\cv.pdf", "Users/me/cv.pdf"),
        ("folder/./sub//cv.pdf", "folder/sub/cv.pdf"),
        ("evil\x00name\n.pdf", "evilname.pdf"),
        ("..", "upload_3"),
        ("", "upload_3"),
        (None, "upload_3"),
    ],
)
def test_display_names_are_sanitised(raw, expected):
    assert sanitize_display_name(raw, 3) == expected


def test_display_names_are_length_capped():
    assert len(sanitize_display_name("a" * 1000 + ".pdf", 0)) <= 255


def up(name, data=b"data"):
    return UploadFile(io.BytesIO(data), filename=name)


async def collect(uploads, **kw):
    kw = {"max_files": 50, "max_total_bytes": 10**9, **kw}
    async with stored_uploads(uploads, **kw) as stored:
        info = [(s, s.path.read_bytes(), s.path.exists()) for s in stored]
        root = stored[0].path.parent
        inside = all(s.path.resolve().parent == root.resolve() for s in stored)
    return info, root, inside


def test_files_are_stored_under_generated_names_and_removed_afterwards():
    uploads = [up("../../x.pdf", b"one"), up("..\\y.PDF", b"two"), up("noext", b"three")]
    info, root, inside = asyncio.run(collect(uploads))
    assert inside and not root.exists()
    for stored, content, existed in info:
        assert existed and re.fullmatch(r"\d{4}(\.[a-z0-9]+)?", stored.safe_name)
        assert stored.path.name == stored.safe_name and stored.original_filename != stored.safe_name
        assert stored.content_hash == hashlib.sha256(content).hexdigest()
    assert [s.display_name for s, *_ in info] == ["noext", "x.pdf", "y.PDF"]
    assert [s.safe_name for s, *_ in info] == ["0002", "0000.pdf", "0001.pdf"]


def test_pipeline_hash_equals_stored_hash():
    from app.ingestion import sha256_bytes

    info, *_ = asyncio.run(collect([up("a.pdf", b"hello")]))
    assert info[0][0].content_hash == sha256_bytes(b"hello")


def test_oversized_file_is_truncated_not_buffered():
    info, *_ = asyncio.run(collect([up("a.txt", b"x" * 100)], max_file_bytes=10))
    assert info[0][0].size == 11  # limit + 1: enough for the pipeline to flag it as too large


def test_request_limits():
    with pytest.raises(UploadError) as exc:
        asyncio.run(collect([up("a.txt"), up("b.txt"), up("c.txt")], max_files=2))
    assert exc.value.status_code == 413
    with pytest.raises(UploadError) as exc:
        asyncio.run(collect([up("a.txt", b"x" * 50), up("b.txt", b"x" * 50)], max_total_bytes=60))
    assert exc.value.status_code == 413
    with pytest.raises(UploadError) as exc:
        asyncio.run(collect([up(""), up(None)]))
    assert exc.value.status_code == 400


def test_temp_dir_is_removed_even_when_the_body_raises():
    holder = {}

    async def run():
        async with stored_uploads([up("a.pdf")], max_files=5, max_total_bytes=10**6) as stored:
            holder["root"] = stored[0].path.parent
            raise RuntimeError("pipeline blew up")

    with pytest.raises(RuntimeError):
        asyncio.run(run())
    assert not holder["root"].exists()
