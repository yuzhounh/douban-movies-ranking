"""Build from the frozen public payload, then verify every list and row in order."""
import argparse
import hashlib
import json
from pathlib import Path

from build_pages_data import write_shards

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", action="store_true")
    args = parser.parse_args()
    original = ROOT / "docs/data/movies.json"
    raw = original.read_bytes()
    payload = json.loads(raw)
    if args.pack:
        write_shards(payload, original)
    directory = original.parent
    read = lambda name: json.loads((directory / name).read_text(encoding="utf-8"))
    manifest = read("manifest.json")
    assert manifest["count"] == len(payload["movies"])
    assert manifest["generated_at"] == payload["generated_at"]
    assert manifest["formula"] == payload["formula"]
    assert [{k: v for k, v in item.items() if k != "data"}
            for item in manifest["navigation"]] == payload["navigation"]
    assert read(manifest["search"]) == [[m["id"], m["title"]] for m in payload["movies"]]
    members = [[] for _ in payload["navigation"]]
    for index, movie in enumerate(payload["movies"]):
        for source in movie["sources"]:
            members[source].append(index)
    references = {"manifest.json", manifest["search"]}
    for source, expected in zip(manifest["navigation"], members):
        descriptor = read(source["data"])
        assert descriptor["count"] == source["count"] == len(expected)
        assert read(descriptor["index"]) == expected
        rows = [row for page in descriptor["pages"] for row in read(page)]
        assert rows == [{k: v for k, v in payload["movies"][i].items() if k != "sources"}
                        for i in expected]
        assert all(len(read(page)) == min(100, len(expected) - start * 100)
                   for start, page in enumerate(descriptor["pages"]))
        references.update([source["data"], descriptor["index"], *descriptor["pages"]])
    assert original.read_bytes() == raw
    first = read(manifest["navigation"][0]["data"])
    first_files = ["manifest.json", manifest["navigation"][0]["data"], first["pages"][0]]
    receipt = {
        "original_sha256": hashlib.sha256(raw).hexdigest(), "movies": len(payload["movies"]),
        "lists": len(members), "memberships_verified_in_order": sum(map(len, members)),
        "legacy_bytes": len(raw), "first_page_json_bytes": sum((directory / f).stat().st_size for f in first_files),
        "first_page_files": first_files, "search_index_bytes": (directory / manifest["search"]).stat().st_size,
        "default_membership_bytes": (directory / first["index"]).stat().st_size,
        "shard_files": len(references), "shard_json_bytes": sum((directory / f).stat().st_size for f in references),
        "note": "Uncompressed file bytes, not measured network transfer, heap, latency or energy. Pages intentionally duplicate cross-list display rows; legacy full payload retained.",
    }
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    (results / "pages-shards-verification.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
