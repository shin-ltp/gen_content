"""Mac 远程临时文件清理（Fish Audio jobs / ComfyUI output）。"""
from __future__ import annotations

from config import (
    COMFYUI_OUTPUT_DIR,
    COMFYUI_REMOTE_HOST,
    FISH_AUDIO_TTS_REMOTE_HOST,
    FISH_AUDIO_TTS_REMOTE_WORKROOT,
    IMG_GENERATION_PROVIDER,
    TTS_BACKEND,
)


def _ssh(host: str):
    from fish_audio_batch import _PlainSSHRemote

    return _PlainSSHRemote(host)


def cleanup_fish_audio_job(issue_date: str) -> None:
    """删除 Mac 上当期 Fish Audio 远程 job 目录。"""
    if TTS_BACKEND != "fish":
        return

    host = FISH_AUDIO_TTS_REMOTE_HOST
    job_dir = f"{FISH_AUDIO_TTS_REMOTE_WORKROOT.rstrip('/')}/{issue_date}"
    _ssh(host).ssh_short(f"rm -rf {job_dir}", label="SSH(cleanup fish job)")


def cleanup_comfyui_output() -> None:
    """删除 Mac 上 ComfyUI output 目录中的生成 PNG。"""
    if IMG_GENERATION_PROVIDER != "comfyui":
        return

    host = COMFYUI_REMOTE_HOST
    out = COMFYUI_OUTPUT_DIR.rstrip("/")
    cmd = f"find {out} -maxdepth 2 -type f \\( -name '*.png' -o -name '*.jpg' -o -name '*.webp' \\) -delete"
    _ssh(host).ssh_short(cmd, label="SSH(cleanup comfyui output)")


def cleanup_mac_issue_artifacts(issue_date: str) -> None:
    """流程全部成功后：清除 Mac 上当期 Fish job 与 ComfyUI 输出残留。"""
    cleaned: list[str] = []

    if TTS_BACKEND == "fish":
        cleanup_fish_audio_job(issue_date)
        cleaned.append(f"fish-audio/jobs/{issue_date}")

    if IMG_GENERATION_PROVIDER == "comfyui":
        cleanup_comfyui_output()
        cleaned.append("comfyui/output/*")

    if cleaned:
        print(
            f"  [Mac 清理] 已清除远程临时文件: {', '.join(cleaned)}",
            flush=True,
        )
