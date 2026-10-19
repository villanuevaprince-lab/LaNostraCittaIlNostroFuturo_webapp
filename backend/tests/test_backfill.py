from backend.backfill_attachments import source_file


def test_backfill_finds_new_and_legacy_paths_without_traversal(tmp_path):
    current = tmp_path / "storage" / "uploads" / "recent.jpg"
    old = tmp_path / "uploads" / "segnalazioni" / "1" / "buca.jpg"
    for path in (current, old):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"jpeg")
    assert source_file(tmp_path, "recent.jpg") == current
    assert source_file(tmp_path, "/uploads/segnalazioni/1/buca.jpg") == old
    assert source_file(tmp_path, "../../outside.jpg") is None
