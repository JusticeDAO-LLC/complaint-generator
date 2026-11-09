from integrations.ipfs_datasets.multimedia import extract_attachment_text, extract_transcript_or_text


def test_video_transcript_degrades_when_ffmpeg_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("integrations.ipfs_datasets.multimedia.shutil.which", lambda _name: None)
    video = tmp_path / "hearing.mp4"
    video.write_bytes(b"not-a-real-video")

    result = extract_transcript_or_text(video)

    assert result["status"] == "degraded"
    assert "ffmpeg" in result["missing_tools"]


def test_attachment_text_passthrough_returns_the_upstream_value(monkeypatch):
    monkeypatch.setattr(
        "integrations.ipfs_datasets.multimedia.import_attr_optional",
        lambda *_args, **_kwargs: (lambda path: f"text:{path}", None),
    )

    assert extract_attachment_text("notes.txt") == "text:notes.txt"
