"""
WebUI サーバーモジュール
ワークフロー中のユーザー確認ステップで使用する軽量 HTTP サーバー。
analysis.json / episodes_plan.json の表示・編集・保存を WebUI 経由で行い、
「確認」ボタンのクリックでオーケストレーターに制御を返す。
"""
import json
import socket
import sys
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"


def _find_free_port(start: int = 8765, end: int = 8800) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"空きポートが見つかりません ({start}-{end})")


def _make_handler(
    output_dir: Path,
    mode: str,
    confirmed: threading.Event,
    episodes_plan_draft: dict | None = None,
):
    """mode ("analysis" | "episodes") に応じた HTTP リクエストハンドラを動的生成する。

    episodes_plan_draft: episodes_plan.json が無い初回表示用の既定プラン（メモリのみ）。
    """

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", f"/{mode}"):
                html_name = (
                    "analysis_editor.html"
                    if mode == "analysis"
                    else "episodes_editor.html"
                )
                self._send_file(TOOLS_DIR / html_name, "text/html; charset=utf-8")
            elif path == "/api/analysis":
                self._send_file(
                    output_dir / "analysis.json", "application/json; charset=utf-8"
                )
            elif path == "/api/episodes-plan":
                plan_path = output_dir / "episodes_plan.json"
                if plan_path.is_file():
                    self._send_file(
                        plan_path,
                        "application/json; charset=utf-8",
                    )
                elif episodes_plan_draft is not None:
                    data = json.dumps(
                        episodes_plan_draft, ensure_ascii=False, indent=2
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_error(404, "episodes_plan.json も draft もありません")
            elif path.startswith("/api/image/"):
                filename = path.split("/")[-1]
                stem = filename.rsplit(".", 1)[0]
                img_path = output_dir / "articles" / "images" / filename
                if not img_path.exists():
                    for ext in ("png", "jpg", "jpeg", "webp"):
                        alt_path = output_dir / "articles" / "images" / f"{stem}.{ext}"
                        if alt_path.exists():
                            img_path = alt_path
                            break
                
                content_type = "image/png"
                if img_path.suffix.lower() in (".jpg", ".jpeg"):
                    content_type = "image/jpeg"
                elif img_path.suffix.lower() == ".webp":
                    content_type = "image/webp"
                    
                self._send_file(img_path, content_type)
            else:
                self.send_error(404)

        def do_POST(self):
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)

            if path == "/api/analysis":
                self._write_json(output_dir / "analysis.json", body)
            elif path == "/api/analysis/confirm":
                self._write_json(output_dir / "analysis.json", body, send_response=False)
                # 確認時点で REVIEW_ANALYSIS を完了として記録（プロセス中断時も状態を保持）
                try:
                    from state_manager import StateManager
                    issue_date = output_dir.name
                    StateManager(issue_date).complete_step("REVIEW_ANALYSIS")
                except Exception:
                    pass
                self._json_ok()
                confirmed.set()
            elif path == "/api/episodes-plan":
                try:
                    obj = json.loads(body)
                except json.JSONDecodeError as e:
                    self._json_err(str(e), status=400)
                    return
                plan_path = output_dir / "episodes_plan.json"
                issue_date = output_dir.name
                try:
                    from group_episodes import EpisodeGrouper

                    grouper = EpisodeGrouper(issue_date)
                    if not plan_path.is_file():
                        ok, err = grouper.materialize_plan_from_web(obj)
                    else:
                        ok, err = grouper.sync_plan_json_to_episode_metadata(obj)
                    if not ok:
                        self._json_err(err, status=409)
                        return
                except Exception as e:
                    self._json_err(f"保存処理で例外が発生しました: {e}", status=500)
                    return
                self._json_ok()
            elif path == "/api/episodes-plan/confirm":
                try:
                    obj = json.loads(body)
                except json.JSONDecodeError as e:
                    self._json_err(str(e), status=400)
                    return
                issue_date = output_dir.name
                try:
                    from group_episodes import EpisodeGrouper

                    grouper = EpisodeGrouper(issue_date)
                    ok, err = grouper.verify_plan_materialized_on_disk(obj)
                    if not ok:
                        self._json_err(err, status=400)
                        return
                    ok2, err2 = grouper.sync_plan_json_to_episode_metadata(obj)
                    if not ok2:
                        self._json_err(err2, status=400)
                        return
                    try:
                        from state_manager import StateManager

                        StateManager(issue_date).complete_step("GROUP_EPISODES")
                    except Exception:
                        pass
                    self._json_ok()
                    confirmed.set()
                except Exception as e:
                    self._json_err(f"確認処理で例外が発生しました: {e}", status=500)
                    return
            elif path.startswith("/api/image/regenerate/"):
                article_id = path.split("/")[-1]
                issue_date = output_dir.name
                try:
                    # orchestrate 常駐プロセスでは import キャッシュされるため、
                    # 開発中のコード更新を WebUI 再生成に反映する
                    import importlib
                    import generate_images as _generate_images_mod

                    importlib.reload(_generate_images_mod)
                    ImageGenerator = _generate_images_mod.ImageGenerator
                    gen = ImageGenerator(issue_date)
                    success = gen.regenerate_article_image(article_id)
                    if success:
                        self._json_ok()
                    else:
                        self._json_err("画像の再生成に失敗しました", status=500)
                except Exception as e:
                    self._json_err(f"サーバーエラー: {str(e)}", status=500)
            else:
                self.send_error(404)

        # ── helpers ──────────────────────────────────────
        def _send_file(self, fpath: Path, ctype: str):
            if not fpath.exists():
                self.send_error(404, f"Not found: {fpath.name}")
                return
            data = fpath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        def _write_json(self, fpath: Path, raw: bytes, send_response: bool = True):
            """JSON をファイルに書き込む。send_response=False のときはHTTPレスポンスを送らない。"""
            try:
                obj = json.loads(raw)
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(obj, f, indent=2, ensure_ascii=False)
                if send_response:
                    self._json_ok()
            except Exception as e:
                self._json_err(str(e))

        def _json_ok(self):
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json_err(self, msg: str, status: int = 500):
            body = json.dumps({"error": msg}, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            pass

    return Handler


def serve_and_wait(
    output_dir: Path,
    mode: str,
    *,
    on_started=None,
    episodes_plan_draft: dict | None = None,
) -> bool:
    """WebUI を起動しユーザーの「確認」クリックまでブロックする。

    Args:
        output_dir: 対象号の出力ディレクトリ
        mode: "analysis" | "episodes"
        on_started: サーバー起動後に呼ばれるコールバック on_started(url: str)。
                    主プロセスへの URL 通知などに使用する。
        episodes_plan_draft: mode=episodes かつ episodes_plan.json が無いとき GET で返す既定プラン。
    Returns:
        True （確認済み）
    """
    confirmed = threading.Event()
    port = _find_free_port()
    handler = _make_handler(
        output_dir, mode, confirmed, episodes_plan_draft=episodes_plan_draft
    )
    server = HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://localhost:{port}/"
    label = "記事分析レビュー" if mode == "analysis" else "エピソード編集"
    print(f"\n{'='*60}")
    print(f"  {label} WebUI")
    print(f"  URL: {url}")
    if mode == "analysis":
        skipped_path = output_dir / "analysis_skipped.json"
        if skipped_path.is_file():
            try:
                data = json.loads(skipped_path.read_text(encoding="utf-8"))
                summary = (data.get("summary") or "").strip()
                if summary:
                    print(f"  {summary.replace('[情報] ', '')}")
                else:
                    count = int(data.get("count", 0))
                    indices = data.get("skipped_raw_indices") or []
                    if count == 0:
                        print("  分析失败跳过: 0 篇")
                    else:
                        raw_list = ", ".join(f"{int(i):03d}" for i in indices)
                        print(f"  分析失败跳过: {count} 篇 (RAW {raw_list})")
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pass
    print(f"  ブラウザで確認・編集し「確認」ボタンで次に進みます。")
    print(f"{'='*60}\n", flush=True)

    if on_started is not None:
        try:
            on_started(url)
        except Exception:
            pass

    webbrowser.open(url)
    confirmed.wait()
    server.shutdown()
    print(f"[WebUI] {label}を確認しました。サーバーを停止します。\n", flush=True)
    return True
