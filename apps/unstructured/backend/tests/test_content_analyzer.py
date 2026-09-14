from primedata.analysis.content_analyzer import build_representative_sample


def test_build_representative_sample_small_text_returns_same():
    text = "This is a short sample."
    assert build_representative_sample(text, chunk=5000, max_total=20000) == text


def test_build_representative_sample_large_text_contains_markers_and_caps():
    text = ("a" * 10000) + ("b" * 10000) + ("c" * 10000)
    sample = build_representative_sample(text, chunk=5000, max_total=20000)

    assert len(sample) <= 20000
    assert "=== MIDDLE SAMPLE ===" in sample
    assert "=== END SAMPLE ===" in sample
