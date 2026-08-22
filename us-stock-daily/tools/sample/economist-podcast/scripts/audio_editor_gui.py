"""
Audio Segment Editor GUI — 分片音声エディタ

segments.json を読み込み、セグメントの可視化・テキスト編集・再生成・
挿入・削除・並べ替え・結合を GUI で行うツール。

使用方法:
  python audio_editor_gui.py 2026-02-21 -e 01 -a 01
  python audio_editor_gui.py 2026-02-21          # GUI 内で選択

機能:
  - セグメント一覧の可視化（状態色分け表示）
  - テキスト編集 → 該当セグメントのみ再生成
  - 任意位置への新規セグメント挿入
  - セグメント分割（Split）
  - 並べ替え・削除
  - 全セグメント結合 → MP3 出力
"""
import json
import os
import sys
import io
import subprocess
import threading
import time
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

if sys.stdout and getattr(sys.stdout, "encoding", None) and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and getattr(sys.stderr, "encoding", None) and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    print("Error: tkinter が見つかりません。Python を tkinter 付きで再インストールしてください。", file=sys.stderr)
    sys.exit(1)

from config import TTS_BACKEND, get_issue_dir
from generate_audio import (
    _get_wav_duration_sec,
    _silence_duration,
    _slice_by_pause_and_period,
    _validate_wav,
    AudioGenerator,
    MAX_RETRIES,
    SILENCE_PAUSE_LONG_SEC,
    SILENCE_PAUSE_SHORT_SEC,
    SILENCE_PERIOD_SEC,
    WAV_MIN_SIZE,
)

# ── After-type 表示マッピング ─────────────────────────────────
AFTER_LABELS = [
    ("。(句点)", "period"),
    ("[pause short]", "pause_short"),
    ("[pause long]", "pause_long"),
    ("(なし)", None),
]
AFTER_TO_LABEL = {v: k for k, v in AFTER_LABELS}
LABEL_TO_AFTER = {k: v for k, v in AFTER_LABELS}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  InsertDialog — 新規セグメント挿入用ダイアログ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class InsertDialog(tk.Toplevel):
    """新規セグメント挿入ダイアログ。"""

    def __init__(self, parent, title="新規セグメント挿入"):
        super().__init__(parent)
        self.title(title)
        self.resizable(True, True)
        self.result = None
        self.transient(parent)
        self.grab_set()

        tk.Label(self, text="テキスト:", font=("Meiryo", 10)).pack(
            padx=10, pady=(10, 0), anchor="w"
        )
        self.text_w = tk.Text(self, height=5, width=70, font=("Meiryo", 11), wrap="word")
        self.text_w.pack(padx=10, pady=5, fill="both", expand=True)

        af = ttk.Frame(self)
        af.pack(padx=10, pady=5, fill="x")
        tk.Label(af, text="区切り:").pack(side="left")
        self.after_var = tk.StringVar(value="。(句点)")
        ttk.Combobox(
            af,
            textvariable=self.after_var,
            values=[lbl for lbl, _ in AFTER_LABELS],
            state="readonly",
            width=18,
        ).pack(side="left", padx=5)

        bf = ttk.Frame(self)
        bf.pack(padx=10, pady=(5, 10))
        ttk.Button(bf, text="挿入", command=self._ok).pack(side="left", padx=5)
        ttk.Button(bf, text="キャンセル", command=self.destroy).pack(side="left", padx=5)

        self.text_w.focus_set()
        self.geometry("620x280")
        self.wait_window()

    def _ok(self):
        text = self.text_w.get("1.0", "end-1c")
        after = LABEL_TO_AFTER.get(self.after_var.get(), "period")
        self.result = (text, after)
        self.destroy()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BatchInitDialog — TTS txt から segments.json を一括作成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class BatchInitDialog(tk.Toplevel):
    """TTS テキストが存在し segments.json が未作成の記事を一覧表示し、
    選択した記事の切片定義ファイルを一括作成するダイアログ。"""

    def __init__(self, parent, output_dir: Path):
        super().__init__(parent)
        self.title("切片定義ファイルの新規作成")
        self.resizable(True, True)
        self.result: list[tuple[str, str, Path]] | None = None
        self.transient(parent)
        self.grab_set()

        self.candidates = self._find_candidates(output_dir)

        tk.Label(
            self,
            text="TTS テキストあり・切片未作成の記事:",
            font=("Meiryo", 10, "bold"),
        ).pack(padx=10, pady=(10, 2), anchor="w")

        if not self.candidates:
            tk.Label(
                self, text="（対象の記事がありません）", font=("Meiryo", 10), fg="#888"
            ).pack(padx=10, pady=10)
            ttk.Button(self, text="閉じる", command=self.destroy).pack(pady=(0, 10))
            self.geometry("420x160")
            self.wait_window()
            return

        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            list_frame,
            selectmode="extended",
            font=("Meiryo", 10),
            yscrollcommand=scrollbar.set,
        )
        self.listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)

        for ep, art, tts_path in self.candidates:
            self.listbox.insert("end", f"Episode {ep} / Article {art}  ({tts_path.name})")

        self.listbox.select_set(0, "end")

        bf = ttk.Frame(self)
        bf.pack(padx=10, pady=(5, 10))
        ttk.Button(
            bf, text="全選択", command=lambda: self.listbox.select_set(0, "end")
        ).pack(side="left", padx=5)
        ttk.Button(
            bf, text="全解除", command=lambda: self.listbox.select_clear(0, "end")
        ).pack(side="left", padx=5)
        ttk.Button(bf, text="作成", command=self._ok).pack(side="left", padx=5)
        ttk.Button(bf, text="キャンセル", command=self.destroy).pack(side="left", padx=5)

        self.geometry("480x380")
        self.wait_window()

    def _find_candidates(self, output_dir: Path) -> list[tuple[str, str, Path]]:
        episodes_dir = output_dir / "episodes"
        candidates: list[tuple[str, str, Path]] = []
        if not episodes_dir.exists():
            return candidates
        for ep_dir in sorted(episodes_dir.iterdir()):
            if not ep_dir.is_dir():
                continue
            tts_dir = ep_dir / "tts"
            if not tts_dir.exists():
                continue
            for tts_file in sorted(tts_dir.glob("*.txt")):
                art = tts_file.stem
                seg_json = ep_dir / "audio_work" / art / "segments.json"
                if not seg_json.exists():
                    candidates.append((ep_dir.name, art, tts_file))
        return candidates

    def _ok(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("情報", "記事を選択してください。", parent=self)
            return
        self.result = [self.candidates[i] for i in sel]
        self.destroy()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AudioEditorApp — メインウインドウ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AudioEditorApp(tk.Tk):
    """Audio Segment Editor GUI メインウインドウ。"""

    def __init__(
        self,
        issue_date: str,
        episode=None,
        article=None,
        backend=None,
    ):
        super().__init__()
        self.title(f"Audio Segment Editor — {issue_date}")
        self.geometry("1120x850")
        self.minsize(860, 620)

        self.issue_date = issue_date
        self._backend_name = (backend or TTS_BACKEND).strip().lower()
        if self._backend_name not in ("fish", "qwen", "voxcpm"):
            self._backend_name = "fish"
        self.output_dir = get_issue_dir(issue_date)
        self.segments: list[dict] = []
        self.meta: dict = {}
        self.work_dir: Path | None = None
        self.audio_path: Path | None = None
        self.tts_path: Path | None = None
        self.selected_pos: int | None = None
        self.modified = False
        self._status_cache: dict = {}
        self._play_proc = None
        self._playing = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-s>", lambda e: self._save())

        if episode and article:
            self.ep_var.set(episode)
            self.art_var.set(article)
            self.after(100, self._load_data)

    # ── UI 構築 ──────────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=26, font=("Meiryo", 10))
        style.configure("Treeview.Heading", font=("Meiryo", 10, "bold"))

        # ── Toolbar ──
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(toolbar, text="Episode:").pack(side="left")
        self.ep_var = tk.StringVar()
        self.ep_combo = ttk.Combobox(
            toolbar, textvariable=self.ep_var, width=5, state="readonly"
        )
        self.ep_combo.pack(side="left", padx=(2, 10))
        self.ep_combo.bind("<<ComboboxSelected>>", self._on_ep_change)

        tk.Label(toolbar, text="Article:").pack(side="left")
        self.art_var = tk.StringVar()
        self.art_combo = ttk.Combobox(
            toolbar, textvariable=self.art_var, width=5, state="readonly"
        )
        self.art_combo.pack(side="left", padx=(2, 10))

        ttk.Button(toolbar, text="Load", command=self._load_data).pack(side="left", padx=4)
        ttk.Button(
            toolbar, text="New Segments", command=self._batch_create_segments
        ).pack(side="left", padx=4)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        self._populate_episodes()

        # ── Main paned window ──
        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=8, pady=4)

        # ── Treeview frame ──
        tree_frame = ttk.Frame(paned)
        paned.add(tree_frame, weight=3)

        self.tree_label = tk.Label(
            tree_frame, text="セグメント一覧", anchor="w", font=("Meiryo", 10, "bold")
        )
        self.tree_label.pack(fill="x")

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_scroll_y.pack(side="right", fill="y")

        cols = ("order", "preview", "after", "status")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=cols,
            show="headings",
            yscrollcommand=tree_scroll_y.set,
            selectmode="browse",
        )
        tree_scroll_y.config(command=self.tree.yview)

        self.tree.heading("order", text="#")
        self.tree.heading("preview", text="テキスト")
        self.tree.heading("after", text="区切り")
        self.tree.heading("status", text="状態")
        self.tree.column("order", width=45, anchor="center", stretch=False)
        self.tree.column("preview", width=600, anchor="w")
        self.tree.column("after", width=120, anchor="center", stretch=False)
        self.tree.column("status", width=140, anchor="center", stretch=False)

        self.tree.tag_configure("ok", background="#d4edda")
        self.tree.tag_configure("missing", background="#fff3cd")
        self.tree.tag_configure("error", background="#f8d7da")
        self.tree.tag_configure("silence", background="#e9ecef")

        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Delete>", lambda e: self._delete_selected())

        # ── Editor frame ──
        editor_frame = ttk.Frame(paned)
        paned.add(editor_frame, weight=1)

        text_row = ttk.Frame(editor_frame)
        text_row.pack(fill="both", expand=True, pady=(4, 0))

        left_edit = ttk.Frame(text_row)
        left_edit.pack(side="left", fill="both", expand=True)

        self.edit_label = tk.Label(
            left_edit, text="テキスト編集:", anchor="w", font=("Meiryo", 10, "bold")
        )
        self.edit_label.pack(fill="x")

        self.text_editor = tk.Text(
            left_edit, height=5, font=("Meiryo", 11), wrap="word", state="disabled"
        )
        self.text_editor.pack(fill="both", expand=True)

        # Info panel
        info = ttk.LabelFrame(text_row, text="セグメント情報", width=180)
        info.pack(side="right", fill="y", padx=(8, 0))
        info.pack_propagate(False)
        self.info_labels: dict[str, tk.Label] = {}
        for key, label_text in [
            ("index", "Index:"),
            ("wav", "WAV:"),
            ("size", "Size:"),
            ("dur", "Duration:"),
            ("st", "Status:"),
        ]:
            tk.Label(info, text=label_text, font=("Meiryo", 9), anchor="w").pack(
                fill="x", padx=5, pady=(3, 0)
            )
            lbl = tk.Label(info, text="—", font=("Meiryo", 9, "bold"), anchor="w", fg="#333")
            lbl.pack(fill="x", padx=5)
            self.info_labels[key] = lbl

        # ── Controls row 1: edit + playback ──
        ctrl1 = ttk.Frame(editor_frame)
        ctrl1.pack(fill="x", pady=(6, 2))

        tk.Label(ctrl1, text="区切り:").pack(side="left")
        self.after_combo_var = tk.StringVar()
        self.after_combo = ttk.Combobox(
            ctrl1,
            textvariable=self.after_combo_var,
            values=[lbl for lbl, _ in AFTER_LABELS],
            state="readonly",
            width=16,
        )
        self.after_combo.pack(side="left", padx=(2, 12))
        self.after_combo.bind("<<ComboboxSelected>>", self._on_after_change)

        self.btn_apply = ttk.Button(ctrl1, text="Apply", command=self._apply_text)
        self.btn_apply.pack(side="left", padx=2)
        self.btn_regen = ttk.Button(ctrl1, text="Regenerate", command=self._regenerate_selected)
        self.btn_regen.pack(side="left", padx=2)
        self.btn_regen_all = ttk.Button(
            ctrl1, text="Regen All Missing", command=self._regenerate_all_missing
        )
        self.btn_regen_all.pack(side="left", padx=2)

        ttk.Separator(ctrl1, orient="vertical").pack(side="left", fill="y", padx=8)
        self.btn_play = ttk.Button(ctrl1, text="\u25b6 Play", command=self._play_selected)
        self.btn_play.pack(side="left", padx=2)
        self.btn_stop = ttk.Button(ctrl1, text="\u25a0 Stop", command=self._stop_playback)
        self.btn_stop.pack(side="left", padx=2)

        # ── Controls row 2: structure + output ──
        ctrl2 = ttk.Frame(editor_frame)
        ctrl2.pack(fill="x", pady=2)

        self.btn_ins_before = ttk.Button(ctrl2, text="+ Before", command=self._insert_before)
        self.btn_ins_before.pack(side="left", padx=2)
        self.btn_ins_after = ttk.Button(ctrl2, text="+ After", command=self._insert_after)
        self.btn_ins_after.pack(side="left", padx=2)
        self.btn_split = ttk.Button(ctrl2, text="\u2702 Split", command=self._split_segment)
        self.btn_split.pack(side="left", padx=2)
        self.btn_delete = ttk.Button(ctrl2, text="Delete", command=self._delete_selected)
        self.btn_delete.pack(side="left", padx=2)

        ttk.Separator(ctrl2, orient="vertical").pack(side="left", fill="y", padx=6)
        self.btn_up = ttk.Button(ctrl2, text="\u2191 Up", command=self._move_up)
        self.btn_up.pack(side="left", padx=2)
        self.btn_down = ttk.Button(ctrl2, text="\u2193 Down", command=self._move_down)
        self.btn_down.pack(side="left", padx=2)

        ttk.Separator(ctrl2, orient="vertical").pack(side="left", fill="y", padx=6)
        self.btn_merge = ttk.Button(ctrl2, text="Merge \u2192 MP3", command=self._merge_all)
        self.btn_merge.pack(side="left", padx=2)
        self.btn_save = ttk.Button(ctrl2, text="Save", command=self._save)
        self.btn_save.pack(side="left", padx=2)
        self.btn_write_tts = ttk.Button(
            ctrl2, text="Write TTS", command=self._write_tts_back
        )
        self.btn_write_tts.pack(side="left", padx=2)

        # ── Status bar ──
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(
            self,
            textvariable=self.status_var,
            anchor="w",
            relief="sunken",
            bd=1,
            font=("Meiryo", 9),
        ).pack(fill="x", side="bottom", padx=8, pady=(0, 6))

    # ── Episode / Article discovery ──────────────────────────

    def _populate_episodes(self):
        episodes_dir = self.output_dir / "episodes"
        eps = []
        if episodes_dir.exists():
            eps = sorted(d.name for d in episodes_dir.iterdir() if d.is_dir())
        self.ep_combo["values"] = eps
        if eps and not self.ep_var.get():
            self.ep_var.set(eps[0])
            self._on_ep_change()

    def _on_ep_change(self, event=None):
        ep = self.ep_var.get()
        ep_dir = self.output_dir / "episodes" / ep
        articles_set: set[str] = set()

        # TTS テキストに存在するすべてのファイル（intro, closing を含む）をベースにする
        tts = ep_dir / "tts"
        if tts.exists():
            for f in tts.glob("*.txt"):
                articles_set.add(f.stem)

        # 既に audio_work があるものも補完（segments.json だけあるケースなど）
        aw = ep_dir / "audio_work"
        if aw.exists():
            for d in aw.iterdir():
                if d.is_dir():
                    articles_set.add(d.name)

        articles = sorted(articles_set)
        self.art_combo["values"] = articles
        if articles:
            # 既存選択がリストにあれば保持、なければ先頭にリセット
            current = self.art_var.get()
            self.art_var.set(current if current in articles else articles[0])

    # ── Batch create segments from TTS txt ──────────────────

    def _batch_create_segments(self):
        dlg = BatchInitDialog(self, self.output_dir)
        if not dlg.result:
            return

        created = 0
        for ep, art, tts_path in dlg.result:
            ep_dir = self.output_dir / "episodes" / ep
            work_dir = ep_dir / "audio_work" / art
            work_dir.mkdir(parents=True, exist_ok=True)

            text = tts_path.read_text(encoding="utf-8")
            raw = _slice_by_pause_and_period(text)
            segments: list[dict] = []
            for i, (seg_text, after) in enumerate(raw):
                segments.append(
                    {
                        "index": i,
                        "text": seg_text,
                        "after": after,
                        "has_text": bool(seg_text),
                        "silence_sec": _silence_duration(after),
                        "wav_file": f"seg_{i:04d}.wav" if seg_text else None,
                    }
                )

            meta = {
                "source": art,
                "total_segments": len(segments),
                "text_segments": sum(1 for s in segments if s["has_text"]),
                "silence_config": {
                    "pause_long": SILENCE_PAUSE_LONG_SEC,
                    "pause_short": SILENCE_PAUSE_SHORT_SEC,
                    "period": SILENCE_PERIOD_SEC,
                },
            }
            data = {**meta, "segments": segments}
            info_path = work_dir / "segments.json"
            info_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            created += 1

        self._populate_episodes()
        self._set_status(f"切片定義ファイル作成完了: {created} 件")

        if created == 1:
            ep, art, _ = dlg.result[0]
            self.ep_var.set(ep)
            self._on_ep_change()
            self.art_var.set(art)
            self._load_data()

    # ── Data loading / saving ────────────────────────────────

    def _load_data(self):
        ep = self.ep_var.get().strip()
        art = self.art_var.get().strip()
        if not ep or not art:
            messagebox.showwarning("警告", "Episode と Article を指定してください。")
            return

        ep_dir = self.output_dir / "episodes" / ep
        self.work_dir = ep_dir / "audio_work" / art
        self.audio_path = ep_dir / "audio" / f"{art}.mp3"
        self.tts_path = ep_dir / "tts" / f"{art}.txt"
        info_path = self.work_dir / "segments.json"

        if info_path.exists():
            data = json.loads(info_path.read_text(encoding="utf-8"))
            self.segments = data.get("segments", [])
            self.meta = {k: v for k, v in data.items() if k != "segments"}
        elif self.tts_path.exists():
            if messagebox.askyesno(
                "初回生成",
                "segments.json が見つかりません。\nTTSテキストから分片を作成しますか？",
            ):
                self._create_initial_segments(self.tts_path)
            else:
                return
        else:
            messagebox.showerror(
                "エラー", f"対象ファイルが見つかりません:\n{info_path}\n{self.tts_path}"
            )
            return

        self._status_cache.clear()
        self.selected_pos = None
        self.text_editor.config(state="normal")
        self.text_editor.delete("1.0", "end")
        self.text_editor.config(state="disabled")
        self._refresh_tree()
        self.modified = False
        total = len(self.segments)
        text_count = sum(1 for s in self.segments if s["has_text"])
        self._set_status(f"読み込み完了: {total} セグメント ({text_count} テキスト)")

    def _create_initial_segments(self, tts_path: Path):
        text = tts_path.read_text(encoding="utf-8")
        raw = _slice_by_pause_and_period(text)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.segments = []
        for i, (seg_text, after) in enumerate(raw):
            self.segments.append(
                {
                    "index": i,
                    "text": seg_text,
                    "after": after,
                    "has_text": bool(seg_text),
                    "silence_sec": _silence_duration(after),
                    "wav_file": f"seg_{i:04d}.wav" if seg_text else None,
                }
            )
        self.meta = {
            "source": self.art_var.get(),
            "total_segments": len(self.segments),
            "text_segments": sum(1 for s in self.segments if s["has_text"]),
            "silence_config": {
                "pause_long": SILENCE_PAUSE_LONG_SEC,
                "pause_short": SILENCE_PAUSE_SHORT_SEC,
                "period": SILENCE_PERIOD_SEC,
            },
        }
        self._save_segments()

    def _save(self):
        if not self.work_dir:
            return
        self._save_segments()
        self.modified = False
        self._set_status("保存完了")

    def _save_segments(self):
        if not self.work_dir:
            return
        self.meta["total_segments"] = len(self.segments)
        self.meta["text_segments"] = sum(1 for s in self.segments if s["has_text"])
        data = {**self.meta, "segments": self.segments}
        info_path = self.work_dir / "segments.json"
        info_path.parent.mkdir(parents=True, exist_ok=True)
        info_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _reconstruct_tts_text(self) -> str:
        """全セグメントからTTSテキストを再構築する。"""
        parts: list[str] = []
        for seg in self.segments:
            text = seg["text"]
            after = seg.get("after")
            if text:
                parts.append(text)
            if after == "pause_long":
                parts.append("\n[pause long]\n")
            elif after == "pause_short":
                parts.append("\n[pause short]\n")
            elif after == "period" and text:
                parts.append("\n")
        return "".join(parts)

    def _save_tts_file(self):
        """セグメントからTTSテキストを再構築し、ttsファイルに書き戻す。"""
        if not self.tts_path:
            return
        reconstructed = self._reconstruct_tts_text()
        self.tts_path.write_text(reconstructed, encoding="utf-8")

    def _write_tts_back(self):
        """切片内容を TTS txt ファイルへ回写する（ボタン用）。"""
        if not self.tts_path or not self.segments:
            messagebox.showinfo("情報", "先にデータを読み込んでください。")
            return
        if not messagebox.askyesno(
            "確認",
            f"現在の切片内容で TTS ファイルを上書きしますか？\n{self.tts_path}",
        ):
            return
        self._save_segments()
        self._save_tts_file()
        self._set_status(f"TTS ファイル書き戻し完了: {self.tts_path.name}")

    # ── Treeview refresh ─────────────────────────────────────

    def _refresh_tree(self):
        sel_pos = self.selected_pos
        self.tree.delete(*self.tree.get_children())

        for i, seg in enumerate(self.segments):
            preview = seg["text"][:80].replace("\n", " ") if seg["text"] else ""
            if not seg["has_text"]:
                after_val = seg.get("after", "")
                preview = f"\u2501\u2501 [{after_val}] \u2501\u2501" if after_val else "\u2501\u2501\u2501"

            after_display = AFTER_TO_LABEL.get(seg.get("after"), "(なし)")
            status_key, status_text = self._get_seg_status_quick(seg)

            self.tree.insert(
                "",
                "end",
                iid=str(i),
                values=(i + 1, preview, after_display, status_text),
                tags=(status_key,),
            )

        total = len(self.segments)
        text_count = sum(1 for s in self.segments if s["has_text"])
        self.tree_label.config(text=f"セグメント一覧 ({total} total, {text_count} text)")

        # Async validation for uncached segments
        self._start_bg_validation()

        if sel_pos is not None and sel_pos < len(self.segments):
            self._select_position(sel_pos)

    def _get_seg_status_quick(self, seg) -> tuple[str, str]:
        """Quick status check: uses cache, falls back to file-existence check."""
        if not seg["has_text"]:
            sec = seg.get("silence_sec", 0)
            return "silence", f"\u23f8 {sec}s"

        wav_file = seg.get("wav_file")
        if not wav_file or not self.work_dir:
            return "missing", "未生成"

        wav_path = self.work_dir / wav_file
        if not wav_path.exists():
            return "missing", "未生成"

        cache_key = str(wav_path)
        try:
            mtime = wav_path.stat().st_mtime
        except OSError:
            return "missing", "未生成"

        if cache_key in self._status_cache:
            c_st, c_dt, c_mt = self._status_cache[cache_key]
            if c_mt == mtime:
                return c_st, c_dt

        size = wav_path.stat().st_size
        if size < WAV_MIN_SIZE:
            return "error", "サイズ不足"

        return "ok", "検証中..."

    def _get_seg_status_full(self, seg) -> tuple[str, str]:
        """Full validation with ffprobe — caches the result."""
        if not seg["has_text"]:
            sec = seg.get("silence_sec", 0)
            return "silence", f"\u23f8 {sec}s"

        wav_file = seg.get("wav_file")
        if not wav_file or not self.work_dir:
            return "missing", "未生成"

        wav_path = self.work_dir / wav_file
        if not wav_path.exists():
            return "missing", "未生成"

        try:
            mtime = wav_path.stat().st_mtime
            size = wav_path.stat().st_size
        except OSError:
            return "missing", "未生成"

        cache_key = str(wav_path)
        if cache_key in self._status_cache:
            c_st, c_dt, c_mt = self._status_cache[cache_key]
            if c_mt == mtime:
                return c_st, c_dt

        if size < WAV_MIN_SIZE:
            r = ("error", "サイズ不足")
            self._status_cache[cache_key] = (*r, mtime)
            return r

        valid, reason, _kind = _validate_wav(wav_path, seg["text"])
        if not valid:
            r = ("error", reason[:25])
            self._status_cache[cache_key] = (*r, mtime)
            return r

        duration = _get_wav_duration_sec(wav_path)
        r = ("ok", f"OK {duration:.1f}s")
        self._status_cache[cache_key] = (*r, mtime)
        return r

    def _start_bg_validation(self):
        """Background thread to validate uncached WAV files and update tree."""
        uncached = []
        for i, seg in enumerate(self.segments):
            if not seg["has_text"] or not seg.get("wav_file") or not self.work_dir:
                continue
            wav_path = self.work_dir / seg["wav_file"]
            if wav_path.exists() and str(wav_path) not in self._status_cache:
                uncached.append((i, seg))

        if not uncached:
            return

        def validate():
            for pos, seg in uncached:
                st_key, st_text = self._get_seg_status_full(seg)
                self.after(0, lambda p=pos, k=st_key, t=st_text: self._update_tree_item(p, k, t))

        threading.Thread(target=validate, daemon=True).start()

    def _update_tree_item(self, pos: int, status_key: str, status_text: str):
        iid = str(pos)
        if self.tree.exists(iid):
            values = list(self.tree.item(iid, "values"))
            values[3] = status_text
            self.tree.item(iid, values=tuple(values), tags=(status_key,))

    # ── Selection ────────────────────────────────────────────

    def _on_tree_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            self.selected_pos = None
            return
        pos = int(sel[0])
        self.selected_pos = pos
        seg = self.segments[pos]

        self.text_editor.config(state="normal")
        self.text_editor.delete("1.0", "end")
        self.text_editor.insert("1.0", seg["text"])

        after_label = AFTER_TO_LABEL.get(seg.get("after"), "(なし)")
        self.after_combo_var.set(after_label)
        self._update_info(seg)
        self.edit_label.config(text=f"テキスト編集: #{pos + 1}")

    def _update_info(self, seg):
        self.info_labels["index"].config(text=str(seg.get("index", "—")))
        self.info_labels["wav"].config(text=seg.get("wav_file") or "—")

        if seg.get("wav_file") and self.work_dir:
            wav_path = self.work_dir / seg["wav_file"]
            if wav_path.exists():
                sz = wav_path.stat().st_size
                self.info_labels["size"].config(text=f"{sz:,} bytes")
                dur = _get_wav_duration_sec(wav_path)
                self.info_labels["dur"].config(text=f"{dur:.2f}s" if dur > 0 else "—")
            else:
                self.info_labels["size"].config(text="—")
                self.info_labels["dur"].config(text="—")
        else:
            self.info_labels["size"].config(text="—")
            self.info_labels["dur"].config(text="—")

        st_key, st_txt = self._get_seg_status_quick(seg)
        self.info_labels["st"].config(text=st_txt)

    def _select_position(self, pos: int):
        iid = str(pos)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self._on_tree_select()

    # ── Text editing ─────────────────────────────────────────

    def _apply_text(self):
        pos = self.selected_pos
        if pos is None:
            return
        new_text = self.text_editor.get("1.0", "end-1c")
        seg = self.segments[pos]
        if new_text == seg["text"]:
            self._set_status("変更なし")
            return

        seg["text"] = new_text
        seg["has_text"] = bool(new_text.strip())
        if seg["has_text"] and not seg.get("wav_file"):
            seg["wav_file"] = f"seg_{seg['index']:04d}.wav"
        elif not seg["has_text"]:
            if seg.get("wav_file") and self.work_dir:
                (self.work_dir / seg["wav_file"]).unlink(missing_ok=True)
            seg["wav_file"] = None

        if seg.get("wav_file") and self.work_dir:
            wav_path = self.work_dir / seg["wav_file"]
            self._status_cache.pop(str(wav_path), None)
            wav_path.unlink(missing_ok=True)

        self.modified = True
        self._save_tts_file()
        self._save_segments()
        self._refresh_tree()
        self._select_position(pos)
        self._set_status(f"#{pos + 1} テキスト更新 → TTS保存済（要 Regenerate）")

    def _on_after_change(self, event=None):
        pos = self.selected_pos
        if pos is None:
            return
        label = self.after_combo_var.get()
        new_after = LABEL_TO_AFTER.get(label)
        seg = self.segments[pos]
        seg["after"] = new_after
        seg["silence_sec"] = _silence_duration(new_after)
        self.modified = True
        self._refresh_tree()
        self._select_position(pos)

    # ── Regenerate ───────────────────────────────────────────

    def _regenerate_selected(self):
        pos = self.selected_pos
        if pos is None:
            messagebox.showinfo("情報", "セグメントを選択してください。")
            return
        seg = self.segments[pos]
        if not seg["has_text"]:
            messagebox.showinfo("情報", "テキストのないセグメントは生成できません。")
            return
        if not seg.get("wav_file"):
            seg["wav_file"] = f"seg_{seg['index']:04d}.wav"

        self._set_status(f"#{pos + 1} 生成中...")
        self._set_buttons_state("disabled")

        def task():
            try:
                gen = AudioGenerator(self.issue_date, backend=self._backend_name)
                gen._synthesize_segments(self.work_dir, [seg], force=True)
                wav_path = self.work_dir / seg["wav_file"]
                self._status_cache.pop(str(wav_path), None)
                valid, reason, _kind = _validate_wav(wav_path, seg["text"])
                self.after(
                    0,
                    lambda: self._on_regen_done(pos, valid, "" if valid else reason),
                )
            except Exception as e:
                self.after(0, lambda: self._on_regen_done(pos, False, str(e)))

        threading.Thread(target=task, daemon=True).start()

    def _on_regen_done(self, pos: int, success: bool, msg: str = ""):
        self._set_buttons_state("normal")
        self._status_cache.clear()
        self._refresh_tree()
        self._select_position(pos)
        if success:
            self._set_status(f"#{pos + 1} 生成完了")
        else:
            self._set_status(f"#{pos + 1} 生成失敗: {msg}")

    def _regenerate_all_missing(self):
        if not self.work_dir:
            return
        missing = []
        for i, seg in enumerate(self.segments):
            if seg["has_text"] and seg.get("wav_file"):
                st, _ = self._get_seg_status_full(seg)
                if st != "ok":
                    missing.append(seg)
        if not missing:
            messagebox.showinfo("情報", "未生成のセグメントはありません。")
            return
        n = len(missing)
        if not messagebox.askyesno("確認", f"{n} 個のセグメントを生成しますか？"):
            return

        self._set_buttons_state("disabled")

        def task():
            gen = AudioGenerator(self.issue_date, backend=self._backend_name)
            text_segs = [s for s in self.segments if s["has_text"] and s.get("wav_file")]

            self.after(
                0,
                lambda: self._set_status(f"一括生成中... {n} セグメント（远程 batch）"),
            )
            gen._synthesize_segments(self.work_dir, missing, force=True)

            bad, _rewrite_eligible = gen._validate_wavs(self.work_dir, text_segs)
            for retry_round in range(MAX_RETRIES):
                if not bad:
                    break
                retry_segs = [s for s in text_segs if s["index"] in bad]
                cnt = len(retry_segs)
                self.after(
                    0,
                    lambda r=retry_round, c=cnt: self._set_status(
                        f"リトライ {r + 1}/{MAX_RETRIES}: {c} セグメント"
                    ),
                )
                for s in retry_segs:
                    (self.work_dir / s["wav_file"]).unlink(missing_ok=True)
                gen._synthesize_segments(self.work_dir, retry_segs, force=True)
                bad, _rewrite_eligible = gen._validate_wavs(self.work_dir, text_segs)

            bad_count = len(bad)
            self.after(0, lambda b=bad_count: self._on_regen_all_done(b))

        threading.Thread(target=task, daemon=True).start()

    def _on_regen_all_done(self, bad_count: int = 0):
        self._set_buttons_state("normal")
        self._status_cache.clear()
        self._refresh_tree()
        if bad_count > 0:
            self._set_status(f"一括生成完了 ({bad_count} 件検証失敗)")
        else:
            self._set_status("一括生成完了 — 全セグメント正常")

    # ── Playback ─────────────────────────────────────────────

    def _play_selected(self):
        pos = self.selected_pos
        if pos is None:
            return
        seg = self.segments[pos]
        if not seg.get("wav_file") or not self.work_dir:
            return
        wav_path = self.work_dir / seg["wav_file"]
        if not wav_path.exists():
            messagebox.showinfo("情報", "WAVファイルが存在しません。先に生成してください。")
            return
        self._stop_playback()
        self._playing = True
        self.btn_play.config(state="disabled")
        self._set_status(f"\u25b6 再生中: #{pos + 1}")

        def play_thread():
            try:
                for i in range(pos, len(self.segments)):
                    if not self._playing:
                        break
                    seg_i = self.segments[i]

                    self.after(0, lambda p=i: self._select_position(p))

                    if seg_i.get("wav_file") and self.work_dir:
                        wp = self.work_dir / seg_i["wav_file"]
                        if wp.exists():
                            self.after(
                                0,
                                lambda p=i: self._set_status(f"\u25b6 再生中: #{p + 1}"),
                            )
                            self._play_one_wav(wp)

                    if not self._playing:
                        break

                    silence = seg_i.get("silence_sec", 0)
                    if silence and silence > 0:
                        self._sleep_interruptible(silence)
            except Exception as e:
                self.after(0, lambda err=str(e): self._set_status(f"再生エラー: {err}"))
            finally:
                self._playing = False
                self.after(0, lambda: self.btn_play.config(state="normal"))
                self.after(0, lambda: self._set_status("再生完了"))

        threading.Thread(target=play_thread, daemon=True).start()

    def _play_one_wav(self, wav_path: Path):
        """Play a single WAV file synchronously (blocks until finished or stopped)."""
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
        else:
            proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", str(wav_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._play_proc = proc
            proc.wait()
            self._play_proc = None

    def _sleep_interruptible(self, seconds: float):
        """Sleep for *seconds*, waking early if playback is stopped."""
        end = time.time() + seconds
        while time.time() < end and self._playing:
            time.sleep(0.05)

    def _stop_playback(self):
        self._playing = False
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        if self._play_proc and self._play_proc.poll() is None:
            self._play_proc.terminate()
            self._play_proc = None

    # ── Insert / Split / Delete / Move ───────────────────────

    def _next_index(self) -> int:
        return max((s["index"] for s in self.segments), default=-1) + 1

    def _insert_before(self):
        self._do_insert(before=True)

    def _insert_after(self):
        self._do_insert(before=False)

    def _do_insert(self, before: bool):
        pos = self.selected_pos
        if pos is None:
            pos = len(self.segments) if not before else 0

        dlg = InsertDialog(self)
        if dlg.result is None:
            return
        text, after = dlg.result
        insert_pos = pos if before else pos + 1
        new_idx = self._next_index()
        has_text = bool(text.strip())
        seg = {
            "index": new_idx,
            "text": text,
            "after": after,
            "has_text": has_text,
            "silence_sec": _silence_duration(after),
            "wav_file": f"seg_{new_idx:04d}.wav" if has_text else None,
        }
        self.segments.insert(insert_pos, seg)
        self.modified = True
        self._refresh_tree()
        self._select_position(insert_pos)
        self._set_status(f"セグメント挿入: #{insert_pos + 1}")

    def _split_segment(self):
        """カーソル位置でセグメントを2つに分割する。"""
        pos = self.selected_pos
        if pos is None:
            return
        seg = self.segments[pos]
        if not seg["has_text"]:
            messagebox.showinfo("情報", "テキストのないセグメントは分割できません。")
            return

        cursor_idx = self.text_editor.index("insert")
        text_before = self.text_editor.get("1.0", cursor_idx).rstrip()
        text_after = self.text_editor.get(cursor_idx, "end-1c").lstrip()

        if not text_before or not text_after:
            messagebox.showinfo("情報", "テキストの途中にカーソルを置いてから実行してください。")
            return

        # Delete old WAV for current segment
        if seg.get("wav_file") and self.work_dir:
            wav_path = self.work_dir / seg["wav_file"]
            self._status_cache.pop(str(wav_path), None)
            wav_path.unlink(missing_ok=True)

        old_after = seg["after"]
        old_silence = seg["silence_sec"]

        seg["text"] = text_before
        seg["after"] = "period"
        seg["silence_sec"] = _silence_duration("period")

        new_idx = self._next_index()
        new_seg = {
            "index": new_idx,
            "text": text_after,
            "after": old_after,
            "has_text": True,
            "silence_sec": old_silence,
            "wav_file": f"seg_{new_idx:04d}.wav",
        }
        self.segments.insert(pos + 1, new_seg)
        self.modified = True
        self._refresh_tree()
        self._select_position(pos)
        self._set_status(f"#{pos + 1} を分割しました → #{pos + 1}, #{pos + 2}")

    def _delete_selected(self):
        pos = self.selected_pos
        if pos is None:
            return
        seg = self.segments[pos]
        preview = (seg["text"][:40] + "...") if len(seg["text"]) > 40 else (seg["text"] or "(silence)")
        if not messagebox.askyesno("確認", f"セグメント #{pos + 1} を削除しますか？\n「{preview}」"):
            return

        if seg.get("wav_file") and self.work_dir:
            wav_path = self.work_dir / seg["wav_file"]
            self._status_cache.pop(str(wav_path), None)
            wav_path.unlink(missing_ok=True)

        self.segments.pop(pos)
        self.modified = True
        self._refresh_tree()
        new_pos = min(pos, len(self.segments) - 1) if self.segments else None
        if new_pos is not None:
            self._select_position(new_pos)
        else:
            self.selected_pos = None
        self._set_status("セグメント削除完了")

    def _move_up(self):
        pos = self.selected_pos
        if pos is None or pos <= 0:
            return
        self.segments[pos], self.segments[pos - 1] = (
            self.segments[pos - 1],
            self.segments[pos],
        )
        self.modified = True
        self.selected_pos = pos - 1
        self._refresh_tree()

    def _move_down(self):
        pos = self.selected_pos
        if pos is None or pos >= len(self.segments) - 1:
            return
        self.segments[pos], self.segments[pos + 1] = (
            self.segments[pos + 1],
            self.segments[pos],
        )
        self.modified = True
        self.selected_pos = pos + 1
        self._refresh_tree()

    # ── Merge ────────────────────────────────────────────────

    def _merge_all(self):
        if not self.work_dir or not self.audio_path:
            return

        self._save_segments()

        missing_n = sum(
            1
            for s in self.segments
            if s["has_text"] and self._get_seg_status_quick(s)[0] != "ok"
        )
        if missing_n > 0:
            if not messagebox.askyesno(
                "警告",
                f"{missing_n} 個のセグメントが未生成/エラーです。\n"
                "スキップして結合しますか？",
            ):
                return

        self._set_status("結合中...")
        self._set_buttons_state("disabled")
        self.audio_path.parent.mkdir(parents=True, exist_ok=True)

        def task():
            try:
                gen = AudioGenerator(self.issue_date, backend=self._backend_name)
                success, duration = gen._merge_from_work_dir(
                    self.work_dir, self.segments, self.audio_path
                )
                # 結合が成功した場合は、該当記事/特殊パートの duration_sec を metadata.json に反映する
                if success and duration > 0:
                    ep = self.ep_var.get().strip()
                    art = self.art_var.get().strip()
                    ep_dir = self.output_dir / "episodes" / ep
                    try:
                        article_order = int(art)
                    except ValueError:
                        article_order = None

                    if article_order is not None:
                        AudioGenerator._update_article_duration(
                            ep_dir, article_order, duration
                        )
                    else:
                        special_kind = art.lower()
                        if special_kind in {"intro", "closing"}:
                            AudioGenerator._update_special_duration(
                                ep_dir, special_kind, duration
                            )

                self.after(0, lambda: self._on_merge_done(success))
            except Exception as e:
                self.after(0, lambda: self._on_merge_done(False, str(e)))

        threading.Thread(target=task, daemon=True).start()

    def _on_merge_done(self, success: bool, msg: str = ""):
        self._set_buttons_state("normal")
        if success:
            self._set_status(f"結合完了: {self.audio_path.name}")
        else:
            self._set_status(f"結合失敗: {msg}")
            messagebox.showerror("エラー", f"結合に失敗しました:\n{msg}")

    # ── Helpers ──────────────────────────────────────────────

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _set_buttons_state(self, state: str):
        for btn in (
            self.btn_apply,
            self.btn_regen,
            self.btn_regen_all,
            self.btn_play,
            self.btn_ins_before,
            self.btn_ins_after,
            self.btn_split,
            self.btn_delete,
            self.btn_up,
            self.btn_down,
            self.btn_merge,
            self.btn_save,
            self.btn_write_tts,
        ):
            btn.config(state=state)

    def _on_close(self):
        if self.modified:
            resp = messagebox.askyesnocancel("保存確認", "変更が保存されていません。保存しますか？")
            if resp is None:
                return
            if resp:
                self._save()
        self._stop_playback()
        self.destroy()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Audio Segment Editor GUI — 分片音声を可視化・編集・再生成するツール"
    )
    parser.add_argument("issue_date", help="雑誌の号数 (YYYY-MM-DD)")
    parser.add_argument("--episode", "-e", default=None, help="エピソード番号 (例: 01)")
    parser.add_argument("--article", "-a", default=None, help="記事番号 (例: 01)")
    parser.add_argument(
        "--tts-backend",
        choices=["fish", "qwen", "voxcpm"],
        default=None,
        help="TTS: fish / qwen / voxcpm。未指定時は TTS_BACKEND",
    )
    args = parser.parse_args()

    app = AudioEditorApp(
        args.issue_date,
        episode=args.episode,
        article=args.article,
        backend=args.tts_backend,
    )
    app.mainloop()
