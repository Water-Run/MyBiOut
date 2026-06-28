import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Ensure project root is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mybiout.pages.ohmyconfig.ohmyconfig import _auto_get_sessdata_from_browsers, _fast_copy_file


def test_fast_copy_file_basic():
    # Test copying a normal file
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as src_file:
        src_file.write(b"hello world")
        src_path = Path(src_file.name)

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as dst_file:
        dst_path = Path(dst_file.name)

    try:
        # Should succeed
        success = _fast_copy_file(src_path, dst_path)
        assert success is True
        with dst_path.open("rb") as f:
            assert f.read() == b"hello world"
    finally:
        if src_path.exists():
            src_path.unlink()
        if dst_path.exists():
            dst_path.unlink()


def test_fast_copy_file_non_existent():
    # Test copying a non-existent file
    src_path = Path("this_file_does_not_exist.txt")
    dst_path = Path("destination.txt")
    success = _fast_copy_file(src_path, dst_path)
    assert success is False


@patch("mybiout.pages.ohmyconfig.ohmyconfig._fast_copy_file")
def test_auto_get_sessdata_from_browsers_fallback_or_empty(mock_copy):
    # Mock fast copy to always return False (simulating locked/missing files)
    mock_copy.return_value = False

    # Run the function, it should return None because files are missing/locked
    result = _auto_get_sessdata_from_browsers("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edg/120.0")
    assert result is None
