import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from fetch_reference_images import _search_person_image, _score_image_url
for name, q in [("Elon Musk", "Elon Musk official portrait"), ("Sanae Takaichi", "Sanae Takaichi official portrait")]:
    print(f"\n=== {name} ===")
    urls = _search_person_image(name, q, 5)
    for u in urls:
        print(f"  score={_score_image_url(u):3d} | {u[:95]}")
