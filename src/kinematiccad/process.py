"""Bounded subprocess I/O and process-tree timeouts; no shell interpretation."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time


def kill_tree(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.kill()
    except ProcessLookupError:
        pass


def bounded_run(argv, *, timeout=300, output_limit=128_000_000, cwd=None, env=None, stdin=None):
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
        start_new_session=os.name != "nt",
    )
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()

    def drain(stream, buffer, limit):
        while True:
            block = stream.read(65536)
            if not block:
                break
            if len(buffer) + len(block) > limit:
                overflow.set()
                break
            buffer.extend(block)

    threads = [
        threading.Thread(target=drain, args=(process.stdout, buffers[0], output_limit), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, buffers[1], 2_000_000), daemon=True),
    ]
    for thread in threads:
        thread.start()

    def feed():
        try:
            process.stdin.write(stdin)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    if stdin is not None:
        threading.Thread(target=feed, daemon=True).start()
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None:
            if overflow.is_set():
                raise RuntimeError("Subprocess output quota exceeded")
            if time.monotonic() > deadline:
                raise TimeoutError(f"Subprocess exceeded {timeout} seconds")
            time.sleep(0.025)
        for thread in threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        if any(t.is_alive() for t in threads):
            raise TimeoutError("Descendant retained subprocess pipes")
        if overflow.is_set():
            raise RuntimeError("Subprocess output quota exceeded")
        if process.returncode:
            raise RuntimeError(
                f"Process exited {process.returncode}: " + buffers[1].decode("utf-8", "replace")[-5000:]
            )
        return bytes(buffers[0]), bytes(buffers[1])
    finally:
        kill_tree(process)
        process.wait()
        for stream in (process.stdout, process.stderr):
            stream.close()
