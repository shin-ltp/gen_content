"""SSH 简装 remote 辅助 (ComfyUI Mac FLUX2 用)"""
import subprocess
import time

from config import (
    COMFYUI_SSH_CONNECT_TIMEOUT,
    COMFYUI_SSH_RETRY_COUNT,
    COMFYUI_SSH_RETRY_WAIT_SEC,
)


class RemoteError(RuntimeError):
    pass


class PlainSSHRemote:
    """ssh / scp を薄くラップする。Windows から Mac への長セッションを想定しない短コマンド用。"""

    def __init__(self, host: str):
        self.host = host
        self._base_args = [
            "ssh",
            "-o",
            f"ConnectTimeout={COMFYUI_SSH_CONNECT_TIMEOUT}",
            "-o",
            "BatchMode=yes",
            self.host,
        ]

    def _run(self, args, timeout: int):
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            raise RemoteError(
                f"remote command failed (rc={proc.returncode}): "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout

    def ssh(self, remote_cmd: str, label: str = "ssh", timeout: int | None = None) -> str:
        cap_timeout = timeout or COMFYUI_SSH_RETRY_WAIT_SEC + 30
        last: Exception | None = None
        for attempt in range(1, COMFYUI_SSH_RETRY_COUNT + 1):
            try:
                return self._run(self._base_args + [remote_cmd], cap_timeout)
            except (subprocess.TimeoutExpired, RemoteError) as e:
                last = e
                if attempt < COMFYUI_SSH_RETRY_COUNT:
                    time.sleep(COMFYUI_SSH_RETRY_WAIT_SEC)
        raise RemoteError(f"[{label}] failed after retries: {last}")

    def scp_from_remote(self, remote_path: str, local_path: str) -> str:
        proc = subprocess.run(
            [
                "scp",
                "-o",
                f"ConnectTimeout={COMFYUI_SSH_CONNECT_TIMEOUT}",
                "-o",
                "BatchMode=yes",
                f"{self.host}:{remote_path}",
                local_path,
            ],
            capture_output=True,
            text=True,
            timeout=COMFYUI_SSH_RETRY_WAIT_SEC + 60,
        )
        if proc.returncode != 0:
            raise RemoteError(
                f"scp failed (rc={proc.returncode}): "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout
