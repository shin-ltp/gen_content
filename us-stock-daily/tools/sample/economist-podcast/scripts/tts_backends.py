"""
GCE VM 自動復旧ユーティリティ。

Qwen / VoxCPM / ComfyUI 等の llm-spot（GCE）远程 batch が SSH/SCP 失敗した際に
停止中 VM の起動を試みる。Fish Audio（Mac SSH）は対象外。
"""
import json
import os
import subprocess
import time

from config import (
    FISH_AUDIO_TTS_REMOTE_HOST,
    FISH_AUDIO_TTS_REMOTE_PROJECT,
    FISH_AUDIO_TTS_REMOTE_ZONE,
    QWEN_TTS_REMOTE_PROJECT,
    QWEN_TTS_REMOTE_ZONE,
)

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_ROOT_DIR = os.path.dirname(_SCRIPTS_DIR)
_DEFAULT_GCE_KEYFILE = os.path.join(_SKILL_ROOT_DIR, "google_gce_default_app.json")
_DEFAULT_GCE_PROJECT_ID = "fuzoku-sns"
_remote_host = FISH_AUDIO_TTS_REMOTE_HOST or "cho@llm-spot"
_host_part = (
    _remote_host.split("@", 1)[-1].strip()
    if "@" in _remote_host
    else _remote_host.strip()
) or "llm-spot"
_GCE_RECOVERY_INSTANCE = (
    os.getenv("GCE_RECOVERY_INSTANCE_NAME", "").strip() or _host_part
)
_GCE_RECOVERY_ZONE = (
    os.getenv("GCE_RECOVERY_ZONE", "").strip()
    or FISH_AUDIO_TTS_REMOTE_ZONE
    or QWEN_TTS_REMOTE_ZONE
)
_GCE_RECOVERY_PROJECT = (
    os.getenv("GCE_RECOVERY_PROJECT_ID", "").strip()
    or FISH_AUDIO_TTS_REMOTE_PROJECT
    or QWEN_TTS_REMOTE_PROJECT
    or os.getenv("GCP_PROJECT_ID", "").strip()
    or _DEFAULT_GCE_PROJECT_ID
)


def _load_project_id_from_keyfile() -> str:
    if not os.path.exists(_DEFAULT_GCE_KEYFILE):
        return _GCE_RECOVERY_PROJECT
    try:
        with open(_DEFAULT_GCE_KEYFILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("project_id") or _GCE_RECOVERY_PROJECT).strip() or _GCE_RECOVERY_PROJECT
    except Exception:
        return _GCE_RECOVERY_PROJECT


def _run_gcloud_status_cmd(project_id: str) -> str | None:
    cmd_candidates = [
        [
            "gcloud",
            "compute",
            "instances",
            "describe",
            _GCE_RECOVERY_INSTANCE,
            "--zone",
            _GCE_RECOVERY_ZONE,
            "--project",
            project_id,
            "--format=value(status)",
        ],
        [
            "gcloud.cmd",
            "compute",
            "instances",
            "describe",
            _GCE_RECOVERY_INSTANCE,
            "--zone",
            _GCE_RECOVERY_ZONE,
            "--project",
            project_id,
            "--format=value(status)",
        ],
    ]
    env = os.environ.copy()
    if os.path.exists(_DEFAULT_GCE_KEYFILE) and not env.get("GOOGLE_APPLICATION_CREDENTIALS"):
        env["GOOGLE_APPLICATION_CREDENTIALS"] = _DEFAULT_GCE_KEYFILE
    last_err: str | None = None
    for cmd in cmd_candidates:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
        except Exception as e:
            last_err = str(e)
            continue
        if result.returncode == 0:
            return (result.stdout or "").strip() or None
        last_err = (result.stderr or result.stdout or "").strip()[:300]
    if last_err:
        print(f"        [警告] VM状態確認に失敗(gcloud): {last_err}")
    return None


def _run_gcloud_start_cmd(project_id: str) -> bool:
    cmd_candidates = [
        [
            "gcloud",
            "compute",
            "instances",
            "start",
            _GCE_RECOVERY_INSTANCE,
            "--zone",
            _GCE_RECOVERY_ZONE,
            "--project",
            project_id,
        ],
        [
            "gcloud.cmd",
            "compute",
            "instances",
            "start",
            _GCE_RECOVERY_INSTANCE,
            "--zone",
            _GCE_RECOVERY_ZONE,
            "--project",
            project_id,
        ],
    ]
    env = os.environ.copy()
    if os.path.exists(_DEFAULT_GCE_KEYFILE) and not env.get("GOOGLE_APPLICATION_CREDENTIALS"):
        env["GOOGLE_APPLICATION_CREDENTIALS"] = _DEFAULT_GCE_KEYFILE
    last_err: str | None = None
    for cmd in cmd_candidates:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
        except Exception as e:
            last_err = str(e)
            continue
        if result.returncode == 0:
            return True
        last_err = (result.stderr or result.stdout or "").strip()[:300]
    if last_err:
        print(f"        [警告] VM起動に失敗(gcloud): {last_err}")
    return False


def _compute_api_get_status(project_id: str) -> str | None:
    if not os.path.exists(_DEFAULT_GCE_KEYFILE):
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except Exception as e:
        print(f"        [警告] Compute API クライアント読込失敗: {e}")
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            _DEFAULT_GCE_KEYFILE,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        svc = build("compute", "v1", credentials=creds, cache_discovery=False)
        resp = (
            svc.instances()
            .get(project=project_id, zone=_GCE_RECOVERY_ZONE, instance=_GCE_RECOVERY_INSTANCE)
            .execute()
        )
        return str(resp.get("status") or "").strip() or None
    except Exception as e:
        print(f"        [警告] Compute API 状態確認失敗: {e}")
        return None


def _compute_api_start_instance(project_id: str) -> bool:
    if not os.path.exists(_DEFAULT_GCE_KEYFILE):
        return False
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except Exception as e:
        print(f"        [警告] Compute API クライアント読込失敗: {e}")
        return False
    try:
        creds = service_account.Credentials.from_service_account_file(
            _DEFAULT_GCE_KEYFILE,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        svc = build("compute", "v1", credentials=creds, cache_discovery=False)
        (
            svc.instances()
            .start(project=project_id, zone=_GCE_RECOVERY_ZONE, instance=_GCE_RECOVERY_INSTANCE)
            .execute()
        )
        return True
    except Exception as e:
        print(f"        [警告] Compute API 起動失敗: {e}")
        return False


def recover_gce_vm_if_stopped(*, reason: str = "接続エラー") -> bool:
    """GCE VM（既定: llm-spot）が停止していれば起動を試みる。起動を試みた場合 True。"""
    project_id = _load_project_id_from_keyfile()
    print(
        f"        [復旧] {reason} — VM 状態確認: "
        f"{_GCE_RECOVERY_INSTANCE} ({_GCE_RECOVERY_ZONE}, project={project_id})"
    )
    status = _run_gcloud_status_cmd(project_id)
    if not status:
        status = _compute_api_get_status(project_id)
    if not status:
        print("        [警告] VM 状態確認に失敗しました（gcloud/Compute API ともに失敗）。")
        return False
    status_up = status.strip().upper()
    print(f"        [復旧] VM 状態: {status_up}")
    if status_up in {"RUNNING", "PROVISIONING", "STAGING"}:
        return False
    if status_up in {"TERMINATED", "STOPPED", "SUSPENDED"}:
        print("        [復旧] VM が停止状態のため起動を試みます...")
        started = _run_gcloud_start_cmd(project_id)
        if not started:
            started = _compute_api_start_instance(project_id)
        if started:
            print("        [復旧] VM 起動コマンドを実行しました。")
            time.sleep(5)
            return True
    return False
