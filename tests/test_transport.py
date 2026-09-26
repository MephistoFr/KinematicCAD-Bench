import io
import stat
import sys
import zipfile

import pytest

from kinematiccad.process import bounded_run
from kinematiccad.transport import pack, unpack


def test_flat_archive_roundtrip(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "submission.json").write_text("{}")
    unpack(pack(source), tmp_path / "dest", candidate=True)
    assert (tmp_path / "dest" / "submission.json").read_text() == "{}"


@pytest.mark.parametrize(
    "name",
    ["../escape", "/absolute", "C:\\file", "a/b.step", "result.json", "CON.step", "nul.step", "COM1.step"],
)
def test_untrusted_archive_paths_rejected(tmp_path, name):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr(name, b"bad")
    with pytest.raises(ValueError):
        unpack(data.getvalue(), tmp_path / "dest", candidate=True)


def test_untrusted_symlink_and_compression_rejected(tmp_path):
    for link in (True, False):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            info = zipfile.ZipInfo("a.step")
            if link:
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            else:
                info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, b"target")
        with pytest.raises(ValueError):
            unpack(data.getvalue(), tmp_path / "dest")


def test_case_colliding_archive_names_rejected(tmp_path):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("a.step", b"one")
        archive.writestr("A.step", b"two")
    with pytest.raises(ValueError):
        unpack(data.getvalue(), tmp_path / "dest", candidate=True)


def test_timeout_and_output_quota():
    with pytest.raises(TimeoutError):
        bounded_run([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.2)
    with pytest.raises(RuntimeError, match="quota"):
        bounded_run([sys.executable, "-c", "print('x'*100000)"], output_limit=1000)
