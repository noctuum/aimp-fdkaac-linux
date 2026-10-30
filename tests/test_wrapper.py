import json
import os
import select
import shutil
import subprocess
import time

FAKE = """#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_DIR"]
open(os.path.join(d, "pid"), "w").write(str(os.getpid()))
data = sys.stdin.buffer.read()
open(sys.argv[sys.argv.index("-o") + 1], "wb").write(data)
json.dump({"argv": sys.argv[1:], "bytes": len(data)}, open(os.path.join(d, "fake.json"), "w"))
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
"""


def setup(wrapper_host_bin, folder, fake=True, mode=0o755):
    exe = folder / "fdkaac-aimp"
    shutil.copy(wrapper_host_bin, exe)
    exe.chmod(mode)
    if fake:
        (folder / "fdkaac").write_text(FAKE)
        (folder / "fdkaac").chmod(mode)
    return exe


def env(folder, **extra):
    return {"PATH": "/usr/bin:/bin", "FAKE_DIR": str(folder), **extra}


def alive(pid):
    try:
        return open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0] not in ("Z", "X")
    except FileNotFoundError:
        return False


def test_runs_fdkaac_beside_itself_with_the_same_arguments(wrapper_host_bin, tmp_path):
    exe, out = setup(wrapper_host_bin, tmp_path), tmp_path / "out.m4a"
    args = ["-b", "128", "-I", "-S", "-o", str(out), "-"]
    p = subprocess.run([exe, *args], input=b"abc" * 1000, env=env(tmp_path), timeout=30)
    fake = json.loads((tmp_path / "fake.json").read_text())
    assert p.returncode == 0 and fake == {"argv": args, "bytes": 3000} and out.read_bytes() == b"abc" * 1000


def test_failure_removes_the_output_and_keeps_the_code(wrapper_host_bin, tmp_path):
    exe, out = setup(wrapper_host_bin, tmp_path), tmp_path / "out.m4a"
    p = subprocess.run([exe, "-o", str(out), "-"], input=b"x", env=env(tmp_path, FAKE_EXIT="2"), timeout=30)
    assert p.returncode == 2 and not out.exists()


def test_modes_become_0755(wrapper_host_bin, tmp_path):
    exe = setup(wrapper_host_bin, tmp_path, mode=0o777)
    subprocess.run([exe, "-o", str(tmp_path / "out.m4a"), "-"], input=b"", env=env(tmp_path), timeout=30)
    assert [(tmp_path / n).stat().st_mode & 0o7777 for n in ("fdkaac-aimp", "fdkaac")] == [0o755, 0o755]


def test_inherited_descriptors_are_closed(wrapper_host_bin, tmp_path):
    exe = setup(wrapper_host_bin, tmp_path)
    r, w = os.pipe()
    p = subprocess.Popen([exe, "-o", str(tmp_path / "out.m4a"), "-"], stdin=subprocess.PIPE, pass_fds=(w,), env=env(tmp_path))
    os.close(w)
    try:
        ready, _, _ = select.select([r], [], [], 5)
        closed_while_running = bool(ready) and os.read(r, 1) == b""
    finally:
        p.communicate(b"x", timeout=30)
        os.close(r)
    assert closed_while_running and p.returncode == 0


def test_fdkaac_ends_with_the_wrapper(wrapper_host_bin, tmp_path):
    exe, pid_file = setup(wrapper_host_bin, tmp_path), tmp_path / "pid"
    p = subprocess.Popen([exe, "-o", str(tmp_path / "out.m4a"), "-"], stdin=subprocess.PIPE, env=env(tmp_path))
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text():
            break
        time.sleep(0.05)
    child = int(pid_file.read_text())
    p.kill()
    p.wait(timeout=30)
    for _ in range(100):
        if not alive(child):
            break
        time.sleep(0.05)
    p.stdin.close()
    assert not alive(child)


def test_missing_fdkaac_exits_127(wrapper_host_bin, tmp_path):
    exe = setup(wrapper_host_bin, tmp_path, fake=False)
    p = subprocess.run([exe, "-o", str(tmp_path / "out.m4a"), "-"], input=b"", capture_output=True, env=env(tmp_path), timeout=30)
    assert p.returncode == 127 and b"fdkaac-aimp: cannot run" in p.stderr
