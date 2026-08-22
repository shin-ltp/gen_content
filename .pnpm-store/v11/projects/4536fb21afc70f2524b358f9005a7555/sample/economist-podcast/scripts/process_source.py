"""
ソースファイル処理モジュール
PDF/EPUBファイルからテキストと表紙画像を抽出する。
EPUB は OPF/spine に従い章ごとに raw/001.txt, 002.txt, ... として保存する。
PDF は全文を raw/001.txt に保存する。互換のため raw_text.txt も出力する。
"""
import re
import sys
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from html import unescape

import pymupdf  # PyMuPDF

from config import SOURCE_DIR, get_issue_dir
from state_manager import StateManager

# OPF でよく使われる名前空間
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"


class SourceProcessor:
    """PDF/EPUBファイルの処理クラス"""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.state = StateManager(issue_date)
        self.output_dir = get_issue_dir(issue_date)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def find_source_file(self) -> Path | None:
        """ソースディレクトリから該当号のファイルを検索"""
        SOURCE_DIR.mkdir(parents=True, exist_ok=True)
        # 対応フォーマット: PDF, EPUB
        # 日付形式のバリエーション（2026-02-07 → 2026.02.07 等）を考慮
        date_variants = [
            self.issue_date,                        # 2026-02-07
            self.issue_date.replace("-", "."),       # 2026.02.07
            self.issue_date.replace("-", ""),        # 20260207
        ]
        patterns = []
        for dv in date_variants:
            patterns.extend([
                f"*{dv}*.pdf",
                f"*{dv}*.epub",
                f"*economist*{dv}*",
                f"*Economist*{dv}*",
            ])
        for pattern in patterns:
            matches = list(SOURCE_DIR.glob(pattern))
            if matches:
                return matches[0]

        # 日付パターンが見つからない場合、ディレクトリ内の全ファイルを表示
        all_files = list(SOURCE_DIR.glob("*"))
        if all_files:
            print(f"[警告] '{self.issue_date}' に一致するファイルが見つかりません。")
            print(f"  ソースディレクトリ内のファイル一覧:")
            for f in all_files:
                print(f"    - {f.name}")
        else:
            print(f"[エラー] ソースディレクトリが空です: {SOURCE_DIR}")
        return None

    @staticmethod
    def _html_to_plain_text(html_bytes: bytes, base_encoding: str = "utf-8") -> str:
        """HTML/XHTML をプレーンテキストに変換する"""
        try:
            s = html_bytes.decode(base_encoding, errors="replace")
        except Exception:
            s = html_bytes.decode("utf-8", errors="replace")
        # 不要ブロックを除去
        s = re.sub(r"<script[^>]*>.*?</script>", " ", s, flags=re.DOTALL | re.IGNORECASE)
        s = re.sub(r"<style[^>]*>.*?</style>", " ", s, flags=re.DOTALL | re.IGNORECASE)
        # ブロック要素の直後に改行
        for tag in ("p", "div", "br", "h1", "h2", "h3", "li", "tr"):
            s = re.sub(rf"</{tag}\s*>", "\n", s, flags=re.IGNORECASE)
            s = re.sub(rf"<{tag}(?:\s[^>]*)?>", "\n", s, flags=re.IGNORECASE)
        # 残りタグを空白に
        s = re.sub(r"<[^>]+>", " ", s)
        s = unescape(s)
        # 空白・改行の正規化
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n\s*\n", "\n\n", s)
        return s.strip()

    def _extract_epub_chapters_to_raw(self, epub_path: Path) -> list[str] | None:
        """
        EPUB を ZIP として開き、OPF の spine 順に各コンテンツドキュメントのテキストを抽出する。
        戻り値: 各章のプレーンテキストのリスト（spine 順）。失敗時は None。
        """
        try:
            with zipfile.ZipFile(epub_path, "r") as zf:
                # container.xml で OPF パス取得
                try:
                    container_data = zf.read("META-INF/container.xml")
                except KeyError:
                    for name in zf.namelist():
                        if "container.xml" in name.lower():
                            container_data = zf.read(name)
                            break
                    else:
                        print("[情報] EPUB に container.xml が見つかりません")
                        return None

                root = ET.fromstring(container_data)
                ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
                rootfiles = root.findall(".//c:rootfile", ns) or root.findall(".//rootfile")
                if not rootfiles:
                    return None
                opf_path = rootfiles[0].get("full-path")
                if not opf_path:
                    return None
                opf_dir = str(Path(opf_path).parent)
                if opf_dir and not opf_dir.endswith("/"):
                    opf_dir += "/"

                opf_data = zf.read(opf_path).decode("utf-8")
                opf_root = ET.fromstring(opf_data)

                def find_opf(tag: str):
                    for ns_url in (OPF_NS, ""):
                        elem = opf_root.find(f".//{{{ns_url}}}{tag}") if ns_url else opf_root.find(f".//{tag}")
                        if elem is not None:
                            return elem
                    return None

                def findall_opf(tag: str):
                    for ns_url in (OPF_NS, ""):
                        elems = opf_root.findall(f".//{{{ns_url}}}{tag}") if ns_url else opf_root.findall(f".//{tag}")
                        if elems:
                            return elems
                    return []

                # manifest: id -> (href, media_type)
                manifest = {}
                for item in findall_opf("item"):
                    item_id = (item.get("id") or "").strip()
                    href = (item.get("href") or "").strip()
                    media_type = (item.get("media-type") or "").lower()
                    if not item_id or not href:
                        continue
                    manifest[item_id] = (href, media_type)

                # spine: 読む順の idref リスト（spine の子の itemref のみ順に採用）
                spine_refs = []
                for spine in opf_root.iter():
                    if spine.tag.endswith("spine"):
                        for c in spine:
                            if c.tag.endswith("itemref"):
                                idref = (c.get("idref") or "").strip()
                                if idref and idref in manifest:
                                    spine_refs.append(idref)
                        break

                if not spine_refs:
                    print("[情報] OPF spine から itemref が見つかりません")
                    return None

                chapters = []
                for idref in spine_refs:
                    href, media_type = manifest[idref]
                    if not href.lower().endswith((".xhtml", ".html", ".htm")) and "html" not in media_type:
                        continue
                    full_path = (Path(opf_path).parent / href).as_posix()
                    norm = lambda p: p.replace("\\", "/")
                    for name in zf.namelist():
                        if norm(name) == full_path or norm(name).endswith(norm(href)):
                            try:
                                raw = zf.read(name)
                                text = self._html_to_plain_text(raw)
                                if text:
                                    chapters.append(text)
                            except Exception as e:
                                print(f"[警告] 章の読み込みに失敗: {name} - {e}")
                            break
                return chapters if chapters else None
        except zipfile.BadZipFile:
            print("[警告] EPUB を ZIP として開けませんでした")
            return None
        except ET.ParseError as e:
            print(f"[警告] EPUB 内 XML の解析に失敗: {e}")
            return None
        except Exception as e:
            print(f"[警告] EPUB 章の抽出に失敗: {e}")
            return None

    def _extract_cover_from_epub_zip(self, epub_path: Path) -> str | None:
        """
        EPUB を ZIP として開き、OPF の manifest から表紙画像を取得して保存する。
        PyMuPDF の get_images() は EPUB の表紙がインラインや別リソースの場合に空になることがあるため、
        EPUB の標準的な meta name="cover" / properties="cover-image" に従って抽出する。
        """
        try:
            with zipfile.ZipFile(epub_path, "r") as zf:
                # container.xml で OPF パスを取得
                try:
                    container_data = zf.read("META-INF/container.xml")
                except KeyError:
                    # 大文字小文字の違いなど
                    for name in zf.namelist():
                        if "container.xml" in name.lower():
                            container_data = zf.read(name)
                            break
                    else:
                        print("[情報] EPUB に META-INF/container.xml が見つかりません")
                        return None

                root = ET.fromstring(container_data)
                # 名前空間ありの場合は検索
                ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
                rootfiles = root.findall(".//c:rootfile", ns)
                if not rootfiles:
                    rootfiles = root.findall(".//rootfile")
                if not rootfiles:
                    print("[情報] EPUB container に rootfile が見つかりません")
                    return None

                opf_path = rootfiles[0].get("full-path")
                if not opf_path:
                    return None
                opf_dir = str(Path(opf_path).parent)  # 例: "EPUB"
                if opf_dir and not opf_dir.endswith("/"):
                    opf_dir += "/"

                opf_data = zf.read(opf_path).decode("utf-8")
                opf_root = ET.fromstring(opf_data)

                # OPF 名前空間（EPUB 2/3 でよく使われる）
                opf_ns = "http://www.idpf.org/2007/opf"
                def find_in_opf(tag: str):
                    return opf_root.find(f".//{{{opf_ns}}}{tag}") or opf_root.find(f".//{tag}")

                # meta name="cover" で表紙画像の id を取得
                cover_id = None
                for meta in opf_root.iter():
                    if meta.tag.endswith("meta") and (meta.get("name") or "").lower() == "cover":
                        cover_id = (meta.get("content") or "").strip()
                        break
                if not cover_id:
                    # 属性が name でなく property のこともある
                    for meta in opf_root.iter():
                        if meta.tag.endswith("meta"):
                            if (meta.get("property") or "").lower() == "cover" or (
                                (meta.get("name") or "").lower() == "cover"
                            ):
                                cover_id = (meta.get("content") or meta.get("value") or "").strip()
                                break
                    else:
                        cover_id = None

                # item から cover 画像の href を取得（id 一致 または properties="cover-image"）
                cover_href = None
                for item in opf_root.iter():
                    if not item.tag.endswith("item"):
                        continue
                    item_id = (item.get("id") or "").strip()
                    props = (item.get("properties") or "").lower()
                    href = (item.get("href") or "").strip()
                    if not href:
                        continue
                    if item_id == cover_id or "cover-image" in props:
                        # 画像メディアタイプのみ採用
                        mt = (item.get("media-type") or "").lower()
                        if mt.startswith("image/") or href.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                            cover_href = href
                            break

                if not cover_href:
                    # よくあるパスを直接試す
                    for candidate in ("static_images/cover.jpg", "images/cover.jpg", "cover.jpg", "OEBPS/cover.jpg"):
                        full = f"{opf_dir}{candidate}".replace("//", "/")
                        if full.lstrip("/") in [n.replace("\\", "/") for n in zf.namelist()]:
                            cover_href = candidate
                            break
                    else:
                        print("[情報] OPF に表紙画像の item が見つかりません")
                        return None

                # href を OPF 基準で絶対パスに（OPF が EPUB/content.opf なら EPUB/static_images/cover.jpg）
                if not cover_href.startswith("/"):
                    full_cover_path = (Path(opf_path).parent / cover_href).as_posix()
                else:
                    full_cover_path = cover_href.lstrip("/")
                # ZIP 内はスラッシュ区切りで格納されていることが多い
                norm = lambda p: p.replace("\\", "/")
                for name in zf.namelist():
                    if norm(name) == full_cover_path or norm(name).endswith(norm(cover_href)):
                        cover_data = zf.read(name)
                        ext = Path(cover_href).suffix or ".jpg"
                        if ext.lower() not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                            ext = ".jpg"
                        cover_path = self.output_dir / f"cover{ext}"
                        with open(cover_path, "wb") as f:
                            f.write(cover_data)
                        print(f"[完了] 表紙画像を保存（EPUB）: {cover_path}")
                        return str(cover_path)
                print("[情報] 表紙画像ファイルを ZIP 内で見つけられませんでした")
                return None
        except zipfile.BadZipFile:
            print("[警告] EPUB を ZIP として開けませんでした")
            return None
        except ET.ParseError as e:
            print(f"[警告] EPUB 内 XML の解析に失敗: {e}")
            return None
        except Exception as e:
            print(f"[警告] EPUB 表紙の抽出に失敗: {e}")
            return None

    def extract_cover_image(self, doc: pymupdf.Document) -> str | None:
        """最初のページから表紙画像を抽出して保存する（PDF 向け。EPUB では get_images が空になることがある）"""
        try:
            first_page = doc[0]
            images = first_page.get_images(full=True)
            if not images:
                print("[情報] 表紙画像が見つかりませんでした")
                return None

            # 最大サイズの画像を表紙として採用
            best_image = None
            best_size = 0
            for img_info in images:
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                if base_image and len(base_image["image"]) > best_size:
                    best_size = len(base_image["image"])
                    best_image = base_image

            if best_image:
                ext = best_image.get("ext", "png")
                cover_path = self.output_dir / f"cover.{ext}"
                with open(cover_path, "wb") as f:
                    f.write(best_image["image"])
                print(f"[完了] 表紙画像を保存: {cover_path}")
                return str(cover_path)
        except Exception as e:
            print(f"[警告] 表紙画像の抽出に失敗: {e}")
        return None

    def extract_text(self) -> bool:
        """ソースファイルからテキストと表紙画像を抽出"""
        self.state.start_step("EXTRACT_TEXT")

        source_file = self.find_source_file()
        if not source_file:
            print(f"[エラー] ソースファイルが見つかりません。")
            print(f"  '{SOURCE_DIR}' に対象ファイルを配置してください。")
            return False

        print(f"[処理中] ソースファイル: {source_file.name}")

        try:
            doc = pymupdf.open(str(source_file))
        except Exception as e:
            print(f"[エラー] ファイルを開けません: {e}")
            return False

        # 表紙画像の抽出（EPUB は ZIP/OPF から取得を優先；PDF は PyMuPDF の第一ページ画像）
        cover_path = None
        if source_file.suffix.lower() == ".epub":
            cover_path = self._extract_cover_from_epub_zip(source_file)
        if cover_path is None:
            cover_path = self.extract_cover_image(doc)

        raw_dir = self.output_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        chapter_texts: list[str] = []
        page_count = 0

        # 表紙・目次など短いブロックを除外する最小文字数
        MIN_CHAPTER_CHARS = 1000

        if source_file.suffix.lower() == ".epub":
            # EPUB: spine 順に章ごとに抽出し、1000字未満は除外して raw/NNN.txt に保存
            chapter_texts = self._extract_epub_chapters_to_raw(source_file) or []
            if chapter_texts:
                # 1000字以上の章のみ残し、番号は 1 から振り直す
                chapter_texts = [t for t in chapter_texts if len(t) >= MIN_CHAPTER_CHARS]
                for i, text in enumerate(chapter_texts, 1):
                    p = raw_dir / f"{i:03d}.txt"
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(text)
                print(f"[情報] EPUB を章ごとに抽出: {len(chapter_texts)} ファイル（1000字未満は除外）→ raw/")
            if not chapter_texts:
                # フォールバック: PyMuPDF で全ページ一括
                full_text = ""
                for page in doc:
                    full_text += page.get_text() + "\n\n"
                    page_count += 1
                chapter_texts = [full_text]
                with open(raw_dir / "001.txt", "w", encoding="utf-8") as f:
                    f.write(full_text)
                print("[情報] EPUB 章抽出に失敗したため、全文を raw/001.txt に保存しました")
        else:
            # PDF: 全文を raw/001.txt に保存
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n\n"
                page_count += 1
            chapter_texts = [full_text]
            with open(raw_dir / "001.txt", "w", encoding="utf-8") as f:
                f.write(full_text)

        doc.close()

        # 互換用: 全章を連結して raw_text.txt にも保存
        full_text = "\n\n".join(chapter_texts)
        raw_text_path = self.output_dir / "raw_text.txt"
        with open(raw_text_path, "w", encoding="utf-8") as f:
            f.write(full_text)

        # 抽出メタデータを保存
        metadata = {
            "issue_date": self.issue_date,
            "source_file": source_file.name,
            "total_pages": page_count,
            "total_chars": len(full_text),
            "cover_image": cover_path,
            "raw_dir": "raw",
            "raw_file_count": len(chapter_texts),
        }
        with open(self.output_dir / "extraction_meta.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        self.state.complete_step("EXTRACT_TEXT", {
            "source_file": source_file.name,
            "total_pages": page_count,
            "total_chars": len(full_text),
            "raw_file_count": len(chapter_texts),
        })

        print(f"[完了] テキスト抽出完了: {len(chapter_texts)} 章, {len(full_text)} 文字 (raw/ + raw_text.txt)")
        return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python process_source.py <YYYY-MM-DD>")
        sys.exit(1)
    processor = SourceProcessor(sys.argv[1])
    processor.extract_text()
