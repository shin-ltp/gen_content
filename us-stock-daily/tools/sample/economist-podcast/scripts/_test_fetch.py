"""テスト: fetch_reference_images の検索・ダウンロード機能を単体検証

実記事の analysis.json を変更せず、メモリ上で image_reference を付与して
fetch_reference_images の各関数を試す。
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# scripts ディレクトリをパスに追加
scripts_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(scripts_dir))

from fetch_reference_images import (
    _fetch_bing_images,
    _fetch_ddg_images,
    _download_and_validate_image,
    _get_bing_api_key,
    IMAGE_REFERENCE_MIN_BYTES,
)


def test_search(query: str, count: int = 5) -> None:
    """検索エンジンの動作確認。"""
    print(f"\n{'='*60}")
    print(f"検索クエリ: {query}")
    print(f"{'='*60}")

    bing_key = _get_bing_api_key()
    print(f"Bing API キー設定: {'あり' if bing_key else 'なし（DuckDuckGo 使用）'}")

    if bing_key:
        print("\n--- Bing Image Search ---")
        urls = _fetch_bing_images(query, count)
        print(f"結果: {len(urls)} 件")
        for i, u in enumerate(urls[:3], 1):
            print(f"  [{i}] {u[:100]}")

    print("\n--- DuckDuckGo (fallback) ---")
    urls_ddg = _fetch_ddg_images(query, count)
    print(f"結果: {len(urls_ddg)} 件")
    for i, u in enumerate(urls_ddg[:3], 1):
        print(f"  [{i}] {u[:100]}")

    # 最初の URL のダウンロードを試行
    all_urls = urls + urls_ddg if bing_key else urls_ddg
    if all_urls:
        print(f"\n--- ダウンロード試行（最初の候補）---")
        url = all_urls[0]
        print(f"URL: {url[:100]}")
        raw = _download_and_validate_image(url, IMAGE_REFERENCE_MIN_BYTES)
        if raw:
            print(f"成功: {len(raw):,} bytes (JPEG 正規化済み)")
            # 一時保存して内容確認
            tmp = scripts_dir / f"_test_ref_{hash(query) % 10000}.jpg"
            tmp.write_bytes(raw)
            print(f"保存: {tmp}")
        else:
            print("失敗: ダウンロードまたは検証エラー")
            # 2番目の候補も試す
            if len(all_urls) > 1:
                print(f"2番目の候補を試行: {all_urls[1][:100]}")
                raw = _download_and_validate_image(all_urls[1], IMAGE_REFERENCE_MIN_BYTES)
                if raw:
                    print(f"成功: {len(raw):,} bytes")


if __name__ == "__main__":
    queries = [
        ("Sanae Takaichi official portrait", "高市早苗"),
        ("Elon Musk portrait 2025", "イーロン・マスク"),
        ("Xi Jinping official portrait", "習近平"),
    ]
    for en_query, ja_label in queries:
        test_search(en_query)
        print(f"\n({ja_label} のテスト完了)")
