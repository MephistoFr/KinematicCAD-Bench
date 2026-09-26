from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from .process import bounded_run
from .transport import unpack

THREAD_ENV = {
    "PYTHONHASHSEED": "0",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "TZ": "UTC",
}


class Sandbox:
    def __init__(self, *, unsafe_local=False, image="kinematiccad-bench:0.1.0", timeout=600):
        self.unsafe_local, self.image, self.timeout = unsafe_local, image, timeout
        if unsafe_local:
            self.provenance = {"isolation": "unsafe-local", "rankable": False}
        else:
            if not shutil.which("docker"):
                raise RuntimeError(
                    "Docker is required. --unsafe-local is reserved for trusted development scripts."
                )
            stdout, _ = bounded_run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], timeout=20)
            self.image_id = stdout.decode().strip()
            stdout, _ = bounded_run(
                ["docker", "image", "inspect", image + "-candidate", "--format", "{{.Id}}"], timeout=20
            )
            self.candidate_image_id = stdout.decode().strip()
            self.provenance = {
                "isolation": "docker",
                "rankable": True,
                "image_id": self.image_id,
                "candidate_image_id": self.candidate_image_id,
            }

    def run(self, mode: str, input_dir: Path, output_dir: Path):
        input_dir, output_dir = input_dir.resolve(), output_dir.resolve()
        if output_dir.exists() and any(output_dir.iterdir()):
            raise ValueError("Refusing to reuse a nonempty output directory")
        if self.unsafe_local:
            env = os.environ.copy()
            env.update(THREAD_ENV)
            # Do not pass API credentials into design execution, even in developer mode.
            for name in list(env):
                if any(s in name.upper() for s in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")):
                    env.pop(name, None)
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
            command = [
                sys.executable,
                "-m",
                "kinematiccad.worker",
                mode,
                "--input",
                str(input_dir),
                "--output",
                str(output_dir),
                "--timeout",
                str(max(1, self.timeout - 10)),
            ]
            bounded_run(command, timeout=self.timeout, output_limit=2_000_000, env=env)
            return
        name = "kcb-" + uuid.uuid4().hex
        command = [
            "docker",
            "run",
            "--name",
            name,
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--user=10001:10001",
            "--pids-limit=64",
            "--memory=4g",
            "--memory-swap=4g",
            "--cpus=1",
            "--ulimit",
            "nofile=128:128",
            "--ulimit",
            "fsize=67108864:67108864",
            "--tmpfs",
            "/work:rw,noexec,nosuid,size=256m,uid=10001,gid=10001,mode=700",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m,uid=10001,gid=10001,mode=700",
            "--workdir=/work",
            "--mount",
            f"type=bind,src={input_dir},dst=/input,readonly",
        ]
        for key, value in THREAD_ENV.items():
            command += ["--env", f"{key}={value}"]
        command += [
            self.candidate_image_id if mode == "candidate" else self.image_id,
            "python",
            "-I",
            "-m",
            "kinematiccad.worker",
            mode,
            "--input",
            "/input",
            "--archive",
            "--timeout",
            str(max(1, self.timeout - 10)),
        ]
        try:
            archive, _ = bounded_run(command, timeout=self.timeout)
            unpack(archive, output_dir, candidate=mode == "candidate")
        finally:
            # Killing the Docker client alone would leave the actual container alive.
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20, check=False)
