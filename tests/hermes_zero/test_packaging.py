from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOST_PKG = ROOT / "packages" / "hermes-host"
UV = shutil.which("uv")


@pytest.mark.skipif(UV is None, reason="uv is required to build/install the host wheel")
@pytest.mark.skipif(os.environ.get("HERMES_ZERO_SKIP_PACKAGING") == "1", reason="packaging skipped")
def test_host_wheel_contains_no_application_code_and_runs_clean(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    subprocess.check_call(
        [UV, "build", "--wheel", "--out-dir", str(dist), str(HOST_PKG)],
        cwd=str(tmp_path),
    )
    wheels = list(dist.glob("hermes_host-*.whl"))
    assert wheels, "host wheel was not built"
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert any(name.startswith("hermes_host/") for name in names)
    forbidden = ("agent/", "tools/", "hermes_cli/", "gateway/", "run_agent.py", "cli.py")
    assert not any(name.startswith(prefix) or name == prefix for prefix in forbidden for name in names)

    env_dir = tmp_path / "venv"
    subprocess.check_call([UV, "venv", str(env_dir)], cwd=str(tmp_path))
    python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.check_call([UV, "pip", "install", "--python", str(python), str(wheel)], cwd=str(tmp_path))
    home = tmp_path / "clean-home"
    home.mkdir()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONSAFEPATH"] = "1"
    output = subprocess.check_output(
        [str(python), "-P", "-m", "hermes_host", "--home", str(home), "status"],
        cwd=str(env_dir),
        text=True,
        env=env,
    )
    assert '"running": false' in output
    assert '"enabled": []' in output
    probe = subprocess.check_output(
        [
            str(python),
            "-P",
            "-c",
            "import importlib.util as u; mods=['agent','tools','hermes_cli','run_agent'];"
            "print([m for m in mods if u.find_spec(m)])",
        ],
        cwd=str(env_dir),
        text=True,
        env=env,
    )
    assert probe.strip() == "[]"
