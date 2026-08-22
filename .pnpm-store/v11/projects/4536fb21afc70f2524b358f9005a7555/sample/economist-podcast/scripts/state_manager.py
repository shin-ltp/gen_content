"""
ワークフロー状態管理モジュール
各処理ステップの進捗状況をJSONファイルで追跡し、中断・再開を可能にする
"""
import json
from pathlib import Path
from datetime import datetime
from config import get_issue_dir

# ワークフローのステップ定義（実行順序）
WORKFLOW_STEPS = [
    "EXTRACT_TEXT",      # テキスト抽出
    "ANALYZE_ARTICLES",  # 記事分析・スコアリング
    "REWRITE_ARTICLES",  # 記事改写
    "GROUP_EPISODES",    # エピソード分組・導入生成
    "GENERATE_IMAGES",   # 挿絵生成
    "PREPARE_TTS",       # TTS用テキスト準備
    "GENERATE_AUDIO",    # 音声生成
    "GENERATE_VIDEO",    # 動画生成
]


class StateManager:
    """ワークフローの状態を管理するクラス"""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.output_dir = get_issue_dir(issue_date)
        self.status_file = self.output_dir / "status.json"
        self.status = self._load()

    def _load(self) -> dict:
        """状態ファイルを読み込む。存在しない場合は初期状態を返す"""
        if self.status_file.exists():
            data = json.loads(self.status_file.read_text(encoding="utf-8"))
            migrated = False
            # 後方互換: REVIEW_EPISODES を GROUP_EPISODES に統合
            if "REVIEW_EPISODES" in data.get("completed_steps", []):
                data["completed_steps"] = [
                    s for s in data["completed_steps"] if s != "REVIEW_EPISODES"
                ]
                if "GROUP_EPISODES" not in data["completed_steps"]:
                    data["completed_steps"].append("GROUP_EPISODES")
                migrated = True
            data.get("step_details", {}).pop("REVIEW_EPISODES", None)
            # 後方互換: エピソード単位のステップは completed_steps から除外
            ep_steps = {"PREPARE_TTS", "GENERATE_AUDIO", "GENERATE_VIDEO"}
            orig_len = len(data.get("completed_steps", []))
            data["completed_steps"] = [
                s for s in data.get("completed_steps", []) if s not in ep_steps
            ]
            if len(data["completed_steps"]) != orig_len:
                migrated = True
            for s in ep_steps:
                if data.get("step_details", {}).pop(s, None) is not None:
                    migrated = True
            # 後方互換: REWRITE_ARTICLES が completed_steps にあるのに WAITING_USER の場合は COMPLETED に統一
            rewrite_detail = data.get("step_details", {}).get("REWRITE_ARTICLES")
            if (
                rewrite_detail
                and rewrite_detail.get("status") == "WAITING_USER"
                and "REWRITE_ARTICLES" in data.get("completed_steps", [])
            ):
                rewrite_detail["status"] = "COMPLETED"
                migrated = True
            if migrated:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                data["updated_at"] = datetime.now().isoformat()
                self.status_file.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            return data
        return {
            "issue_date": self.issue_date,
            "current_step": None,
            "completed_steps": [],
            "step_details": {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    def _save(self):
        """状態をファイルに保存"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.status["updated_at"] = datetime.now().isoformat()
        with open(self.status_file, "w", encoding="utf-8") as f:
            json.dump(self.status, f, indent=2, ensure_ascii=False)

    def is_completed(self, step: str) -> bool:
        """指定ステップが完了済みか確認"""
        return step in self.status["completed_steps"]

    def is_waiting_user(self, step: str) -> bool:
        """指定ステップがユーザーの確認待ちか確認"""
        detail = self.status.get("step_details", {}).get(step, {})
        return detail.get("status") == "WAITING_USER"

    def start_step(self, step: str):
        """ステップの開始を記録"""
        self.status["current_step"] = step
        self.status.setdefault("step_details", {})[step] = {
            "status": "IN_PROGRESS",
            "started_at": datetime.now().isoformat(),
        }
        self._save()
        print(f"[状態] ステップ開始: {step}")

    def complete_step(self, step: str, details: dict = None):
        """ステップの完了を記録"""
        if step not in self.status["completed_steps"]:
            self.status["completed_steps"].append(step)
        self.status["current_step"] = None
        step_info = self.status.setdefault("step_details", {}).setdefault(step, {})
        step_info["status"] = "COMPLETED"
        step_info["completed_at"] = datetime.now().isoformat()
        if details:
            step_info.update(details)
        self._save()
        print(f"[状態] ステップ完了: {step}")

    def request_user_review(self, step: str, message: str):
        """ユーザーレビューの要求を記録"""
        self.status["current_step"] = step
        self.status.setdefault("step_details", {})[step] = {
            "status": "WAITING_USER",
            "message": message,
            "requested_at": datetime.now().isoformat(),
        }
        self._save()
        print(f"[状態] ユーザー確認待ち: {step}")
        print(f"  → {message}")

    def approve_step(self, step: str):
        """ユーザーがステップを承認"""
        if step not in self.status["completed_steps"]:
            self.status["completed_steps"].append(step)
        step_info = self.status.setdefault("step_details", {}).setdefault(step, {})
        step_info["status"] = "APPROVED"
        step_info["approved_at"] = datetime.now().isoformat()
        self.status["current_step"] = None
        self._save()
        print(f"[状態] ユーザー承認完了: {step}")

    def update_step_details(self, step: str, details: dict):
        """ステップの詳細を更新する（completed_steps は変更しない）"""
        step_info = self.status.setdefault("step_details", {}).setdefault(step, {})
        step_info.update(details)
        self._save()

    def get_status(self) -> dict:
        """現在の状態を取得"""
        return self.status.copy()

    def print_summary(self):
        """状態のサマリーを表示"""
        print(f"\n{'='*55}")
        print(f"  The Economist {self.issue_date} 号 - 制作進捗状況")
        print(f"{'='*55}")
        for step in WORKFLOW_STEPS:
            if step in self.status["completed_steps"]:
                mark = "  [完了]"
            elif self.is_waiting_user(step):
                mark = "  [確認待ち]"
            elif self.status.get("current_step") == step:
                mark = "  [進行中]"
            else:
                mark = "  [ ]"
            print(f"  {mark} {step}")
        print(f"{'='*55}\n")
