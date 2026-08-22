"""
エピソード分組モジュール
改写済みの記事をセクション類似度に基づいてグループ化し、
45〜70分・最大8篇のポッドキャストエピソードにまとめる。

WebUI 初回表示: ディスクへは書き込まず、既定の分組結果のみ算出する（draft）。
WebUI「保存」初回: episodes_plan.json および各 episodes/NN/metadata.json を作成する。
既にエピソードディレクトリにファイルがある場合はエラー（上書きは手動削除後）。

--from-plan: episodes_plan.json から適用。既定は既存 metadata があるとエラー。
  --force で既存 metadata を上書き再生成する。
"""
import sys
import json
import argparse
import re
from collections import defaultdict
from pathlib import Path

from config import (
    EPISODE_TARGET_CHARS,
    EPISODE_MAX_ARTICLES,
    CHARS_PER_MINUTE_JA,
    SECTION_AFFINITY,
    ensure_section_mapping,
    get_issue_dir,
    get_episode_dir,
    normalize_economist_section,
)
from state_manager import StateManager


class EpisodeGrouper:
    """エピソード分組クラス"""

    @staticmethod
    def _read_title_from_article_md(article_path: Path) -> str | None:
        """
        articles/NNN.md の YAML フロントマターから title を読む。
        改写後の見出しを正とし、episodes 分組・episodes_plan の title_ja と同期させる。
        """
        if not article_path.exists():
            return None
        try:
            text = article_path.read_text(encoding="utf-8")
        except OSError:
            return None
        m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
        if not m:
            return None
        for line in m.group(1).splitlines():
            if line.startswith("title:"):
                raw = line[len("title:") :].strip()
                if len(raw) >= 2 and raw[0] == raw[-1] == '"':
                    return raw[1:-1].replace('\\"', '"').strip()
                return raw.strip()
        return None

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.state = StateManager(issue_date)
        self.output_dir = get_issue_dir(issue_date)
        self.articles_dir = self.output_dir / "articles"
        self.pregenerated_plan_path = self.output_dir / "episodes_plan_pregenerated.json"
        # WebUI 初回表示用（ディスク未保存の既定プラン）
        self._draft_plan: dict | None = None

    def _load_pregenerated_plan(self) -> dict | None:
        """事前生成した分組プランを読み込む。"""
        if not self.pregenerated_plan_path.is_file():
            return None
        try:
            with open(self.pregenerated_plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
            episodes = plan.get("episodes")
            if not isinstance(episodes, list) or not episodes:
                print(
                    f"[警告] {self.pregenerated_plan_path.name} に有効な episodes がありません。"
                )
                return None
            return plan
        except (json.JSONDecodeError, OSError) as e:
            print(f"[警告] {self.pregenerated_plan_path.name} の読み込みに失敗: {e}")
            return None

    def _load_articles(self) -> list[dict]:
        """分析結果と改写済み記事テキストを読み込む"""
        analysis_path = self.output_dir / "analysis.json"
        if not analysis_path.exists():
            print("[エラー] analysis.json が見つかりません。")
            return []

        with open(analysis_path, "r", encoding="utf-8") as f:
            analysis = json.load(f)

        articles = []
        for meta in analysis:
            if meta.get("status") != "KEEP":
                continue
            if "section" in meta and isinstance(meta["section"], str):
                meta["section"] = normalize_economist_section(meta["section"])
            article_path = self.articles_dir / f"{meta['id']:03d}.md"
            if not article_path.exists():
                print(f"[警告] 改写ファイルが見つかりません: {article_path.name}")
                continue
            # テキストサイズ計算のため読み込むが、メタデータにはパスのみ保持でも可
            # ここでは文字数計算のために読み込む
            with open(article_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            body_content = re.sub(r"^---[\s\S]*?---\n", "", content)
            
            meta["char_count"] = len(body_content)
            meta["estimated_minutes"] = round(len(body_content) / CHARS_PER_MINUTE_JA, 1)
            # front matter の title（改写で整えた日本語題）を最優先
            fm_title = self._read_title_from_article_md(article_path)
            if fm_title:
                meta["japanese_title"] = fm_title

            articles.append(meta)

        return articles

    def _calculate_similarity(self, a1: dict, a2: dict) -> float:
        """2つの記事間の類似度を計算する（キーワードとタイトルの重複）"""
        kw1 = set(a1.get("keywords_ja", []))
        kw2 = set(a2.get("keywords_ja", []))
        
        # タイトルもキーワードとして扱う（簡易的な形態素解析の代わり）
        # 日本語なので文字ベースのn-gramや単語分割がないと難しいが、
        # ここではキーワードの一致を主に見る
        
        intersection = len(kw1 & kw2)
        union = len(kw1 | kw2)
        
        if union == 0:
            return 0.0
            
        jaccard = intersection / union
        return jaccard

    def _calculate_group_similarity(self, article: dict, group: list[dict]) -> float:
        """記事とグループ全体の類似度（平均）を計算"""
        if not group:
            return 0.0
        scores = [self._calculate_similarity(article, a) for a in group]
        return sum(scores) / len(scores)

    def _sort_group_by_relevance(self, articles: list[dict]) -> list[dict]:
        """グループ内の記事を関連順に並び替える（貪欲法）"""
        if not articles:
            return []
            
        # 1. 最もスコアが高い（重要な）記事を先頭にする、またはカバー記事を先頭にする
        # relevance_scoreは小さいほど重要
        start_article = min(articles, key=lambda a: (not a.get("is_cover_story", False), a.get("relevance_score", 99)))
        
        sorted_list = [start_article]
        remaining = [a for a in articles if a != start_article]
        
        while remaining:
            last = sorted_list[-1]
            # 直前の記事と最も類似度が高い記事を探す
            next_article = max(remaining, key=lambda a: self._calculate_similarity(last, a))
            sorted_list.append(next_article)
            remaining.remove(next_article)
            
        return sorted_list

    def _group_by_section(self, articles: list[dict]) -> list[list[dict]]:
        """
        セクションと内容の類似度を考慮してエピソードを構成する。
        ターゲット時間: 45～70分、1エピソードあたり最大 EPISODE_MAX_ARTICLES 記事。
        """
        min_chars, max_chars = EPISODE_TARGET_CHARS
        max_articles = EPISODE_MAX_ARTICLES
        
        # ── Step 1: 初期分類（SECTION_AFFINITYベース） ──
        groups: dict[str, list[dict]] = defaultdict(list)
        for article in articles:
            section = article["section"]
            ensure_section_mapping(section)
            affinity = SECTION_AFFINITY.get(section, "other")
            groups[affinity].append(article)

        # ── Step 2: Opinionカテゴリの記事を再分配 ──
        # Opinionにある記事が、他の地域・テーマカテゴリと強く関連していれば移動する
        opinion_articles = groups.get("opinion", [])[:]
        for article in opinion_articles:
            best_affinity = "opinion"
            best_score = 0.0
            
            # Opinion以外のグループとの類似度をチェック
            for aff, arts in groups.items():
                if aff == "opinion":
                    continue
                score = self._calculate_group_similarity(article, arts)
                # 閾値は調整が必要だが、ある程度の関連性があれば移動
                if score > 0.05 and score > best_score:
                    best_score = score
                    best_affinity = aff
            
            if best_affinity != "opinion":
                groups["opinion"].remove(article)
                groups[best_affinity].append(article)
                # print(f"  [移動] {article['japanese_title']} -> {best_affinity} (score: {best_score:.2f})")

        # ── Step 3: 各グループ内を関連順にソート ──
        for aff in groups:
            groups[aff] = self._sort_group_by_relevance(groups[aff])

        # ── Step 4: 時間枠・記事数上限に合わせて調整 ──
        episodes: list[list[dict]] = []
        pending_groups: list[tuple[str, list[dict]]] = [] # (affinity, articles)

        # まず、各グループのサイズを確認
        for aff, arts in groups.items():
            if not arts:
                continue
                
            total_chars = sum(a["char_count"] for a in arts)
            
            if total_chars > max_chars or len(arts) > max_articles:
                # 大きすぎる -> 分割
                # ソート済みなので、頭から順番に切っていけば関連性は保たれるはず
                current_ep = []
                current_chars = 0
                for a in arts:
                    if current_ep and (
                        current_chars + a["char_count"] > max_chars
                        or len(current_ep) >= max_articles
                    ):
                        # 最小時間を満たしているか確認
                        if current_chars >= min_chars:
                            episodes.append(current_ep)
                            current_ep = []
                            current_chars = 0
                        else:
                            # 最小時間に満たない場合、次へ持ち越すか、無理やり区切るか
                            # ここでは一旦区切って、後でマージ候補にする
                            pending_groups.append((aff, current_ep))
                            current_ep = []
                            current_chars = 0
                    
                    current_ep.append(a)
                    current_chars += a["char_count"]
                
                if current_ep:
                    if current_chars >= min_chars:
                        episodes.append(current_ep)
                    else:
                        pending_groups.append((aff, current_ep))

            elif total_chars >= min_chars:
                # ちょうどいい -> 確定
                episodes.append(arts)
            else:
                # 小さい -> マージ候補
                pending_groups.append((aff, arts))

        # ── Step 5: 小さいグループ（pending）の処理 ──
        # 他のpendingグループと結合してサイズを満たすようにする
        # 類似度の高い組み合わせを優先
        
        while pending_groups:
            # 現在の未処理リストから1つ取り出す
            aff1, arts1 = pending_groups.pop(0)
            chars1 = sum(a["char_count"] for a in arts1)
            
            best_match_idx = -1
            best_combined_score = -1.0
            
            # マージ相手を探す
            for i, (aff2, arts2) in enumerate(pending_groups):
                chars2 = sum(a["char_count"] for a in arts2)
                if chars1 + chars2 <= max_chars and len(arts1) + len(arts2) <= max_articles:
                    # グループ間の類似度（代表として各グループの全記事クロスチェックは重いので、
                    # ここではグループ名の相性や、簡易チェックを行う）
                    # 今回はシンプルに、結合後のサイズが良くなるものを優先しつつ、
                    # 可能なら類似度も見たいが、まずはサイズ優先で埋める
                    
                    # 簡易類似度: グループの最初の記事同士で比較
                    score = self._calculate_similarity(arts1[0], arts2[0])
                    
                    if score > best_combined_score:
                        best_combined_score = score
                        best_match_idx = i
                    elif best_match_idx == -1:
                        # スコア0でもサイズが合うなら候補にする
                        best_match_idx = i
            
            if best_match_idx != -1:
                # マージ実行
                aff2, arts2 = pending_groups.pop(best_match_idx)
                merged_arts = arts1 + arts2
                merged_chars = chars1 + sum(a["char_count"] for a in arts2)
                
                if merged_chars >= min_chars:
                    episodes.append(merged_arts)
                else:
                    # まだ小さい -> 再度pendingへ（末尾に追加して後で再評価）
                    pending_groups.append((f"{aff1}+{aff2}", merged_arts))
            else:
                # マージ相手が見つからない場合
                # 既存のエピソードで余裕があるものがあれば入れる
                placed = False
                for ep in episodes:
                    ep_chars = sum(a["char_count"] for a in ep)
                    if ep_chars + chars1 <= max_chars and len(ep) + len(arts1) <= max_articles:
                        ep.extend(arts1)
                        placed = True
                        break
                
                if not placed:
                    # どうしても入らないなら単独でエピソードにする（短くても仕方ない）
                    episodes.append(arts1)

        # ── Step 6: 記事数上限の最終チェック ──
        final_episodes: list[list[dict]] = []
        for ep in episodes:
            if len(ep) > max_articles:
                self._split_large_group(
                    ep, final_episodes, min_chars, max_chars, max_articles
                )
            else:
                final_episodes.append(ep)
        return final_episodes

    @staticmethod
    def _split_large_group(
        articles: list[dict],
        episodes: list[list[dict]],
        min_chars: int,
        max_chars: int,
        max_articles: int = EPISODE_MAX_ARTICLES,
    ) -> None:
        """max_chars / max_articles を超えるグループを記事単位で複数エピソードに分割する"""
        current_ep: list[dict] = []
        current_chars = 0

        for article in articles:
            ac = article["char_count"]
            over_chars = current_chars + ac > max_chars and current_ep
            over_count = len(current_ep) >= max_articles
            if over_chars or over_count:
                episodes.append(current_ep)
                current_ep = []
                current_chars = 0
            current_ep.append(article)
            current_chars += ac

        if current_ep:
            # 残りが極端に短い場合は直前のエピソードに吸収
            if current_chars < min_chars * 0.4 and episodes:
                prev_chars = sum(a["char_count"] for a in episodes[-1])
                if (
                    prev_chars + current_chars <= max_chars * 1.1
                    and len(episodes[-1]) + len(current_ep) <= max_articles
                ):
                    episodes[-1].extend(current_ep)
                    return
            episodes.append(current_ep)

    def _copy_article_images(self, episode_dir: Path, articles: list[dict]):
        """エピソードディレクトリに記事の挿絵をコピーする。

        articles が full meta（order なし）の場合は並び順から order を補完する。
        """
        import shutil
        images_dir = episode_dir / "images"
        images_dir.mkdir(exist_ok=True)
        
        src_images_dir = self.output_dir / "articles" / "images"
        for idx, article in enumerate(articles, start=1):
            try:
                order = int(article.get("order", idx))
            except (TypeError, ValueError):
                order = idx
            aid = article.get("id")
            try:
                aid_int = int(aid)
            except (TypeError, ValueError):
                continue
            
            for ext in ("png", "jpg", "jpeg", "webp"):
                src = src_images_dir / f"{aid_int:03d}.{ext}"
                if src.exists():
                    dst = images_dir / f"{order:02d}.{ext}"
                    try:
                        shutil.copy2(src, dst)
                    except OSError as e:
                        print(f"  [警告] 挿絵のコピーに失敗 {src} -> {dst}: {e}")
                    break

    def _save_episode_metadata(self, episode_num: int, articles: list[dict]):
        """エピソードのメタデータのみを保存し、挿絵をコピーする"""
        episode_dir = get_episode_dir(self.issue_date, episode_num)
        episode_dir.mkdir(parents=True, exist_ok=True)

        meta = self._build_episode_metadata_dict(episode_num, articles)
        with open(episode_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        self._copy_article_images(episode_dir, articles)
        return episode_dir

    def _build_episode_metadata_dict(
        self, episode_num: int, articles: list[dict]
    ) -> dict:
        """エピソード 1 件分の metadata 辞書（ディスク書き込みなし）。"""
        seen = set()
        sections: list[str] = []
        for a in articles:
            s = a["section"]
            if s not in seen:
                seen.add(s)
                sections.append(s)

        return {
            "episode_num": episode_num,
            "issue_date": self.issue_date,
            "sections": sections,
            "article_count": len(articles),
            "total_chars": sum(a["char_count"] for a in articles),
            "estimated_minutes": round(
                sum(a["estimated_minutes"] for a in articles), 1
            ),
            "articles": [
                {
                    "order": i + 1,
                    "id": a["id"],
                    "original_title": a["original_title"],
                    "japanese_title": a.get("japanese_title", ""),
                    "section": a["section"],
                    "summary_ja": a.get("summary_ja", ""),
                    "one_line_intro": a.get("one_line_intro", ""),
                    "relevance_score": a["relevance_score"],
                    "is_cover_story": a.get("is_cover_story", False),
                    "keywords_ja": a.get("keywords_ja", []),
                    "char_count": a["char_count"],
                }
                for i, a in enumerate(articles)
            ],
        }

    @staticmethod
    def _merge_prev_metadata_extras(meta: dict, prev: dict | None) -> None:
        """既存 metadata から youtube / intro / closing / episode_key および記事の YouTube タイムスタンプを復元。"""
        if not prev:
            return
        yt = prev.get("youtube")
        if isinstance(yt, dict) and str(yt.get("video_id", "")).strip():
            meta["youtube"] = yt
        for key in ("intro", "closing", "episode_key"):
            if key in prev:
                meta[key] = prev[key]
        prev_by_id: dict[int, dict] = {}
        for a in prev.get("articles") or []:
            if a.get("id") is None:
                continue
            try:
                prev_by_id[int(a["id"])] = a
            except (TypeError, ValueError):
                continue
        for art in meta.get("articles", []):
            aid = art.get("id")
            if aid is None:
                continue
            try:
                po = prev_by_id.get(int(aid))
            except (TypeError, ValueError):
                continue
            if not po:
                continue
            for k in ("youtube_start_sec", "youtube_start_time", "duration_sec"):
                if k in po:
                    art[k] = po[k]

    def _build_episodes_plan(self, episodes: list[list[dict]]) -> dict:
        """分組結果をユーザーが確認・編集できる軽量な plan JSON として構築する"""
        plan_episodes = []
        for ep_num, ep_articles in enumerate(episodes, 1):
            total_chars = sum(a["char_count"] for a in ep_articles)
            total_min = round(total_chars / CHARS_PER_MINUTE_JA, 1)

            seen = set()
            sections = []
            for a in ep_articles:
                s = a["section"]
                if s not in seen:
                    seen.add(s)
                    sections.append(s)

            plan_episodes.append({
                "episode_num": ep_num,
                "estimated_minutes": total_min,
                "article_count": len(ep_articles),
                "sections": sections,
                "articles": [
                    {
                        "id": a["id"],
                        "section": a["section"],
                        "title_ja": a.get("japanese_title", a["original_title"]),
                        "keywords_ja": a.get("keywords_ja", []),
                        "summary_ja": a.get("summary_ja", ""),
                        "char_count": a["char_count"],
                        "estimated_minutes": a.get("estimated_minutes", 0),
                    }
                    for a in ep_articles
                ],
            })

        return {
            "issue_date": self.issue_date,
            "episode_count": len(episodes),
            "total_articles": sum(len(ep) for ep in episodes),
            "episodes": plan_episodes,
        }

    def _save_episodes_plan(self, plan: dict) -> Path:
        """episodes_plan.json を該当号の出力ルートに保存する"""
        plan_path = self.output_dir / "episodes_plan.json"
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
        return plan_path

    @staticmethod
    def _episode_dir_has_entries(ep_dir: Path) -> bool:
        """エピソードディレクトリが存在し、かつ何らかのファイル/サブディレクトリがあるか。"""
        if not ep_dir.is_dir():
            return False
        try:
            next(ep_dir.iterdir())
            return True
        except StopIteration:
            return False
        except OSError:
            return True

    def _load_analysis_map(self) -> dict | None:
        analysis_path = self.output_dir / "analysis.json"
        if not analysis_path.is_file():
            print("[エラー] analysis.json が見つかりません。")
            return None
        try:
            with open(analysis_path, "r", encoding="utf-8") as f:
                analysis = json.load(f)
            return {a["id"]: a for a in analysis}
        except (json.JSONDecodeError, OSError, KeyError, TypeError) as e:
            print(f"[エラー] analysis.json の読み込みに失敗しました: {e}")
            return None

    def _char_count_from_article_md(self, article_id: int) -> int:
        p = self.articles_dir / f"{article_id:03d}.md"
        if not p.is_file():
            return 0
        try:
            content = p.read_text(encoding="utf-8")
        except OSError:
            return 0
        body = re.sub(r"^---[\s\S]*?---\n", "", content)
        return len(body)

    def _merge_plan_article_into_full(
        self, plan_article: dict, analysis_map: dict
    ) -> dict | None:
        aid = plan_article["id"]
        full_meta = analysis_map.get(aid)
        if not full_meta:
            return None
        char_count = self._char_count_from_article_md(aid)
        merged = {**full_meta}
        merged["char_count"] = char_count
        merged["estimated_minutes"] = round(char_count / CHARS_PER_MINUTE_JA, 1)
        fm_title = self._read_title_from_article_md(self.articles_dir / f"{aid:03d}.md")
        if fm_title:
            merged["japanese_title"] = fm_title
        return merged

    def _full_articles_for_plan_episode(
        self, ep_data: dict, analysis_map: dict
    ) -> list[dict]:
        out: list[dict] = []
        for plan_article in ep_data.get("articles", []):
            merged = self._merge_plan_article_into_full(plan_article, analysis_map)
            if merged:
                out.append(merged)
        return out

    def materialize_plan_from_web(self, plan: dict) -> tuple[bool, str]:
        """WebUI 初回「保存」用: plan をディスクへ materialize する。

        途中失敗で一部の EP だけ作成済みになっている場合でも、
        sync ロジックで再実行して整合を回復できるようにする。
        """
        plan_path = self.output_dir / "episodes_plan.json"
        if plan_path.is_file():
            return False, "episodes_plan.json が既に存在します。"

        episodes = plan.get("episodes") or []
        for ep_data in episodes:
            ep_num = int(ep_data.get("episode_num", 0))
            if ep_num <= 0:
                return False, f"無効な episode_num: {ep_data.get('episode_num')}"
            ep_dir = get_episode_dir(self.issue_date, ep_num)
            meta_path = ep_dir / "metadata.json"
            # 途中失敗の復旧は許可（metadata がある場合のみ）
            if self._episode_dir_has_entries(ep_dir) and not meta_path.is_file():
                return (
                    False,
                    f"エピソード {ep_num:02d} に既存ファイルがありますが metadata.json がありません。"
                    f" 手動で {ep_dir} を整理してから再保存してください。",
                )

        return self.sync_plan_json_to_episode_metadata(plan)

    def sync_plan_json_to_episode_metadata(self, plan: dict) -> tuple[bool, str]:
        """episodes_plan.json 既存時の WebUI「保存」用: プランに合わせて各 metadata を更新する。

        新規エピソード（metadata 未作成・ディレクトリ空）のみディレクトリ作成を許可する。
        既にファイルがあるディレクトリへの新規作成は materialize と同様に禁止しないが、
        新規 EP は空でない親があっても metadata が無ければ作成する。
        """
        episodes = plan.get("episodes") or []
        if not episodes:
            return False, "プランにエピソードがありません。"

        analysis_map = self._load_analysis_map()
        if not analysis_map:
            return False, "analysis.json を読み込めませんでした。"

        rebuilt_episodes: list[list[dict]] = []
        rebuilt_ep_nums: list[int] = []

        for ep_data in episodes:
            ep_num = int(ep_data.get("episode_num", 0))
            if ep_num <= 0:
                return False, f"無効な episode_num: {ep_data.get('episode_num')}"

            ep_articles_full = self._full_articles_for_plan_episode(ep_data, analysis_map)
            if not ep_articles_full:
                return False, f"エピソード {ep_num:02d}: 有効な記事がありません。"

            ep_dir = get_episode_dir(self.issue_date, ep_num)
            meta_path = ep_dir / "metadata.json"

            if meta_path.is_file():
                try:
                    prev = json.loads(meta_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as e:
                    return False, f"{meta_path}: 読み込み失敗 {e}"
                meta = self._build_episode_metadata_dict(ep_num, ep_articles_full)
                self._merge_prev_metadata_extras(meta, prev)
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2, ensure_ascii=False)
                self._copy_article_images(ep_dir, ep_articles_full)
            else:
                if self._episode_dir_has_entries(ep_dir):
                    return (
                        False,
                        f"エピソード {ep_num:02d} に metadata.json がありませんが、"
                        f"ディレクトリ {ep_dir} に既にファイルがあります。"
                        f" 手動で整理するか、空のディレクトリにしてください。",
                    )
                ep_dir.mkdir(parents=True, exist_ok=True)
                meta = self._build_episode_metadata_dict(ep_num, ep_articles_full)
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2, ensure_ascii=False)
                self._copy_article_images(ep_dir, ep_articles_full)

            rebuilt_episodes.append(ep_articles_full)
            rebuilt_ep_nums.append(ep_num)

        updated_plan = self._build_episodes_plan(rebuilt_episodes)
        for i, ep in enumerate(updated_plan["episodes"]):
            ep["episode_num"] = rebuilt_ep_nums[i]
        self._save_episodes_plan(updated_plan)
        return True, ""

    def verify_plan_materialized_on_disk(self, plan: dict) -> tuple[bool, str]:
        """確認ボタン用: 各 EP に metadata.json があるか。"""
        for ep_data in plan.get("episodes") or []:
            ep_num = int(ep_data.get("episode_num", 0))
            if ep_num <= 0:
                return False, f"無効な episode_num: {ep_data.get('episode_num')}"
            meta_path = get_episode_dir(self.issue_date, ep_num) / "metadata.json"
            if not meta_path.is_file():
                return (
                    False,
                    "各エピソードの metadata.json がまだありません。"
                    " 先に「保存」でディスクへ書き出してください。",
                )
        plan_path = self.output_dir / "episodes_plan.json"
        if not plan_path.is_file():
            return False, "episodes_plan.json がありません。先に「保存」してください。"
        return True, ""

    def sync_metadata_after_group_confirm(self) -> bool:
        """WebUI 確認後: plan の存在と materialize 済みを検証し、analysis から文字数等をソフト同期する。"""
        plan_path = self.output_dir / "episodes_plan.json"
        if not plan_path.is_file():
            print(f"[エラー] {plan_path} がありません。")
            return False
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[エラー] episodes_plan.json の読み込みに失敗: {e}")
            return False

        ok, err = self.verify_plan_materialized_on_disk(plan)
        if not ok:
            print(f"[エラー] {err}")
            return False

        analysis_map = self._load_analysis_map()
        if not analysis_map:
            return False

        if not self._soft_merge_metadata_from_analysis(plan, analysis_map):
            return False

        print("[完了] エピソード分組のディスク状態を確認し、メタデータを analysis 由来で同期しました。")
        return True

    def _soft_merge_metadata_from_analysis(
        self, plan: dict, analysis_map: dict
    ) -> bool:
        """既存 metadata.json の youtube / intro / closing / episode_key 等を保ったまま、
        記事の char_count・estimated_minutes・japanese_title を MD/analysis で更新する。
        """
        for ep_data in plan.get("episodes") or []:
            ep_num = int(ep_data["episode_num"])
            meta_path = get_episode_dir(self.issue_date, ep_num) / "metadata.json"
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"[エラー] {meta_path} の読み込みに失敗: {e}")
                return False

            articles = meta.get("articles") or []
            total_chars = 0
            total_est_min = 0.0
            for art in articles:
                aid = art.get("id")
                if aid is None:
                    continue
                try:
                    aid_int = int(aid)
                except (TypeError, ValueError):
                    continue
                merged = self._merge_plan_article_into_full({"id": aid_int}, analysis_map)
                if not merged:
                    continue
                art["char_count"] = merged["char_count"]
                art["estimated_minutes"] = merged["estimated_minutes"]
                if merged.get("japanese_title"):
                    art["japanese_title"] = merged["japanese_title"]
                total_chars += int(art.get("char_count", 0) or 0)
                total_est_min += float(art.get("estimated_minutes", 0) or 0)

            meta["article_count"] = len(articles)
            meta["total_chars"] = total_chars
            meta["estimated_minutes"] = round(total_est_min, 1)

            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2, ensure_ascii=False)
            except OSError as e:
                print(f"[エラー] {meta_path} の書き込みに失敗: {e}")
                return False

        ep_nums: list[int] = []
        rebuilt_for_plan: list[list[dict]] = []
        for ep_data in plan.get("episodes") or []:
            ep_num = int(ep_data["episode_num"])
            ep_nums.append(ep_num)
            meta_path = get_episode_dir(self.issue_date, ep_num) / "metadata.json"
            with open(meta_path, "r", encoding="utf-8") as f:
                md = json.load(f)
            full_list: list[dict] = []
            for a in md.get("articles") or []:
                aid = int(a["id"])
                base = {**analysis_map.get(aid, {})}
                base["char_count"] = a.get("char_count", 0)
                base["estimated_minutes"] = a.get("estimated_minutes", 0)
                base["japanese_title"] = a.get(
                    "japanese_title", base.get("japanese_title", "")
                )
                full_list.append(base)
            rebuilt_for_plan.append(full_list)

        updated_plan = self._build_episodes_plan(rebuilt_for_plan)
        for i, ep in enumerate(updated_plan["episodes"]):
            ep["episode_num"] = ep_nums[i]
        self._save_episodes_plan(updated_plan)
        return True

    def apply_plan(self, *, force: bool = False) -> bool:
        """episodes_plan.json から各エピソードの metadata.json を生成する（CLI 用）。

        force=False のとき、いずれかの EP で metadata.json が既に存在するか、
        エピソードディレクトリにファイルがある場合はエラー（手動削除または --force）。
        force=True のときは上書き再生成する（YouTube 等の追記フィールドは失われる可能性あり）。
        """
        plan_path = self.output_dir / "episodes_plan.json"
        if not plan_path.exists():
            print(f"[エラー] {plan_path} が見つかりません。")
            return False

        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)

        analysis_map = self._load_analysis_map()
        if not analysis_map:
            return False

        plan_episodes = plan.get("episodes", [])
        if not plan_episodes:
            print("[エラー] episodes_plan.json にエピソード情報がありません。")
            return False

        if not force:
            for ep_data in plan_episodes:
                ep_num = int(ep_data["episode_num"])
                ep_dir = get_episode_dir(self.issue_date, ep_num)
                meta_path = ep_dir / "metadata.json"
                if meta_path.is_file() or self._episode_dir_has_entries(ep_dir):
                    print(
                        f"[エラー] エピソード {ep_num:02d} に既にファイルがあります: {ep_dir}\n"
                        f"  上書きする場合はディレクトリを手動で削除するか、--force を指定してください。"
                    )
                    return False

        print(
            f"[処理中] episodes_plan.json から {len(plan_episodes)} 個のエピソードを"
            f"{'再生成' if force else '生成'}します...\n"
        )

        rebuilt_episodes: list[list[dict]] = []
        rebuilt_ep_nums: list[int] = []

        for ep_data in plan_episodes:
            ep_num = int(ep_data["episode_num"])
            ep_articles_full = self._full_articles_for_plan_episode(
                ep_data, analysis_map
            )
            if not ep_articles_full:
                print(f"  [警告] エピソード{ep_num}: 有効な記事がありません。スキップします。")
                continue

            ep_dir = self._save_episode_metadata(ep_num, ep_articles_full)
            total_min = sum(a["estimated_minutes"] for a in ep_articles_full)
            print(
                f"  エピソード{ep_num}: {len(ep_articles_full)}篇, "
                f"約{total_min:.1f}分 → {ep_dir / 'metadata.json'}"
            )
            rebuilt_episodes.append(ep_articles_full)
            rebuilt_ep_nums.append(ep_num)

        updated_plan = self._build_episodes_plan(rebuilt_episodes)
        for i, ep in enumerate(updated_plan["episodes"]):
            ep["episode_num"] = rebuilt_ep_nums[i]
        self._save_episodes_plan(updated_plan)

        print(f"\n[完了] {len(rebuilt_ep_nums)} 個のエピソードを plan から反映しました。")
        return True

    def group_episodes(self) -> bool:
        """記事をエピソードに分組する（ディスクには書かない）。WebUI 用 draft を保持する。"""
        self.state.start_step("GROUP_EPISODES")

        pregenerated = self._load_pregenerated_plan()
        if pregenerated is not None:
            self._draft_plan = pregenerated
            ep_count = len(pregenerated.get("episodes", []))
            self.state.update_step_details("GROUP_EPISODES", {"episode_count": ep_count})
            print(
                f"[情報] 事前生成プランを読み込みました: {self.pregenerated_plan_path.name} "
                f"({ep_count} EP)"
            )
            print("[完了] 既定分組の再計算をスキップし、事前生成プランを WebUI に渡します。")
            return True

        articles = self._load_articles()
        if not articles:
            print("[エラー] 改写済みの記事が見つかりません。")
            self._draft_plan = None
            return False

        print(f"[処理中] {len(articles)}篇の記事をエピソードに分組中...\n")

        episodes = self._group_by_section(articles)

        print(f"[情報] {len(episodes)}個のエピソードに分割しました：")
        for ep_num, ep_articles in enumerate(episodes, 1):
            sorted_arts = ep_articles
            total_chars = sum(a["char_count"] for a in sorted_arts)
            total_min = total_chars / CHARS_PER_MINUTE_JA
            seen = set()
            sec_list = []
            for a in sorted_arts:
                if a["section"] not in seen:
                    seen.add(a["section"])
                    sec_list.append(a["section"])
            print(
                f"  エピソード{ep_num}: {len(sorted_arts)}篇, "
                f"約{total_min:.1f}分 [{', '.join(sec_list)}]"
            )

        plan = self._build_episodes_plan(episodes)
        self._draft_plan = plan

        self.state.update_step_details("GROUP_EPISODES", {"episode_count": len(episodes)})
        print(
            f"\n[完了] 既定の分組を算出しました（{len(episodes)} EP）。"
            f" ディスク未保存 — WebUI で確認後「保存」で書き出してください。"
        )
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="エピソード分組")
    parser.add_argument("issue_date", help="発行日 (YYYY-MM-DD)")
    parser.add_argument(
        "--from-plan",
        action="store_true",
        help="episodes_plan.json を読み込んでエピソードを生成する（WebUI なし）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="--from-plan 時に既存の episodes/NN を上書きする（注意: metadata の追記情報が失われる場合あり）",
    )
    args = parser.parse_args()

    grouper = EpisodeGrouper(args.issue_date)
    plan_path = grouper.output_dir / "episodes_plan.json"

    if args.from_plan:
        if not grouper.apply_plan(force=args.force):
            sys.exit(1)
    elif plan_path.exists():
        from webui_server import serve_and_wait

        print("[情報] episodes_plan.json が存在するため、自動分組をスキップし WebUI を起動します。")
        serve_and_wait(grouper.output_dir, "episodes", episodes_plan_draft=None)
        print("\n[処理中] 確認後のメタデータ同期...")
        if not grouper.sync_metadata_after_group_confirm():
            sys.exit(1)
    else:
        if not grouper.group_episodes():
            sys.exit(1)
        from webui_server import serve_and_wait

        draft = grouper._draft_plan
        serve_and_wait(grouper.output_dir, "episodes", episodes_plan_draft=draft)
        print("\n[処理中] 確認後のメタデータ同期...")
        if not grouper.sync_metadata_after_group_confirm():
            sys.exit(1)
