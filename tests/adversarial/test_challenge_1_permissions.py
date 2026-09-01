"""Adversarial stress test for Challenge 1: Permission Boundaries & Isolation."""
import os
import stat
import subprocess
import tempfile
import pytest

def test_secrets_directory_mode_0700():
    """Verify secrets directories have strict 0700 permissions."""
    paths = ["/home/moku/secrets", "/home/moku/secrets/yt-auto"]
    for path in paths:
        assert os.path.exists(path), f"Path does not exist: {path}"
        st = os.stat(path)
        mode = stat.S_IMODE(st.st_mode)
        assert mode == 0o700, f"Expected 0700 for {path}, got {oct(mode)}"
        # Verify group and others bits are strictly 0
        assert (mode & 0o077) == 0, f"Group or other bits non-zero: {oct(mode)}"

def test_unauthorized_user_access_blocked():
    """Verify unauthorized user (nobody) cannot read, list, or write to secrets."""
    # Attempt to list /home/moku/secrets as nobody
    cmd_list = ["sudo", "-u", "nobody", "ls", "-la", "/home/moku/secrets"]
    res_list = subprocess.run(cmd_list, capture_output=True, text=True)
    assert res_list.returncode != 0, f"Unauthorized listing should fail: {res_list.stdout}"
    assert "Permission denied" in res_list.stderr, f"Expected Permission denied, got: {res_list.stderr}"

    # Attempt to touch a file in /home/moku/secrets/yt-auto as nobody
    cmd_write = ["sudo", "-u", "nobody", "touch", "/home/moku/secrets/yt-auto/unauthorized.txt"]
    res_write = subprocess.run(cmd_write, capture_output=True, text=True)
    assert res_write.returncode != 0, f"Unauthorized write should fail: {res_write.stdout}"
    assert "Permission denied" in res_write.stderr, f"Expected Permission denied, got: {res_write.stderr}"

def test_secrets_file_read_write_owner_integrity():
    """Verify authorized owner (moku) can create and read files with 0600."""
    secret_file = "/home/moku/secrets/yt-auto/adversarial_test.key"
    try:
        with open(secret_file, "w") as f:
            f.write("super_secret_payload_12345\n")
        os.chmod(secret_file, 0o600)
        
        # Verify owner can read
        with open(secret_file, "r") as f:
            content = f.read()
        assert content == "super_secret_payload_12345\n"
        
        # Verify nobody cannot read the file directly
        cmd_cat = ["sudo", "-u", "nobody", "cat", secret_file]
        res_cat = subprocess.run(cmd_cat, capture_output=True, text=True)
        assert res_cat.returncode != 0
        assert "Permission denied" in res_cat.stderr
    finally:
        if os.path.exists(secret_file):
            os.remove(secret_file)

def test_all_standard_directories_exist_with_expected_permissions():
    """Verify all R1 provisioned directories exist and are properly structured."""
    expected_dirs = [
        ("/home/moku/data/yt-auto", 0o755),
        ("/home/moku/data/yt-auto/db", 0o755),
        ("/home/moku/data/yt-auto/worksets", 0o755),
        ("/home/moku/secrets/yt-auto", 0o700),
        ("/home/moku/work/yt-auto", 0o755),
        ("/home/moku/work/yt-auto/renders", 0o755),
        ("/home/moku/work/yt-auto/audio", 0o755),
        ("/home/moku/work/yt-auto/subtitles", 0o755),
        ("/home/moku/work/yt-auto/thumbnails", 0o755),
        ("/home/moku/work/yt-auto/loops", 0o755),
        ("/home/moku/work/yt-auto/temp", 0o755),
        ("/home/moku/artifacts/yt-auto", 0o755),
        ("/home/moku/artifacts/yt-auto/approved", 0o755),
        ("/home/moku/artifacts/yt-auto/rejected", 0o755),
        ("/home/moku/artifacts/yt-auto/metadata", 0o755),
        ("/home/moku/logs/yt-auto", 0o755),
        ("/home/moku/logs/yt-auto/pipeline", 0o755),
        ("/home/moku/logs/yt-auto/daemon", 0o755),
        ("/home/moku/logs/yt-auto/agents", 0o755),
        ("/home/moku/logs/yt-auto/telegram", 0o755),
        ("/home/moku/.config/yt-auto/agent_appdata", 0o755),
        ("/home/moku/.config/yt-auto/agent_appdata/pipeline_creative", 0o755),
        ("/home/moku/.config/yt-auto/agent_appdata/pipeline_visual", 0o755),
        ("/home/moku/.config/yt-auto/agent_appdata/pipeline_planning", 0o755),
        ("/home/moku/.config/yt-auto/agent_appdata/pipeline_qa", 0o755),
    ]
    for path, expected_mode in expected_dirs:
        assert os.path.exists(path), f"Missing required directory: {path}"
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == expected_mode, f"Mode mismatch for {path}: expected {oct(expected_mode)}, got {oct(mode)}"

if __name__ == "__main__":
    pytest.main(["-v", __file__])
