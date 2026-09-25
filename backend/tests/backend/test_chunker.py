"""Unit tests for app.rag.chunker. No database."""
from app.rag.chunker import (
    ChunkConfig, chunk_note, extract_plain_text, note_content_hash,
    pack_windows, split_sentences, estimate_tokens, build_context,
)

H2 = '<h2 style="font-size:1.4em;color:#FF9800;">{}</h2>'
P = '<p style="margin:10px 0;">{}</p>'
BUL = (
    '<div style="margin:12px 0;">'
    '<div style="display:flex;"><span style="color:#FF9800;">◆</span><span>{}</span></div>'
    '<div style="display:flex;"><span style="color:#FF9800;">◆</span><span>{}</span></div>'
    '</div>'
)
HR = '<hr style="border:none;border-top:2px dashed #FFB74D;margin:24px 0;">'


def long_sentences(n, words=12):
    return [" ".join(f"w{i}x{j}" for j in range(words)) + "." for i in range(n)]


class TestExtraction:
    def test_headings_and_bullets(self):
        html = H2.format("Cells") + P.format("Cells are units. They divide.") + BUL.format("Nucleus holds DNA", "Ribosomes make protein")
        chunks = chunk_note(html, None)
        assert len(chunks) == 1
        assert chunks[0].heading == "Cells"
        assert "Nucleus holds DNA\nRibosomes make protein" in chunks[0].text
        assert "◆" not in chunks[0].text

    def test_page_break_increments_page_and_resets_heading(self):
        html = H2.format("One") + P.format("First page.") + HR + P.format("Second page.")
        chunks = chunk_note(html, None)
        assert [(c.page, c.heading) for c in chunks] == [(1, "One"), (2, None)]

    def test_failed_page_marker_dropped(self):
        html = P.format("[Page 2 failed: boom]") + P.format("Real text.")
        chunks = chunk_note(html, None)
        assert len(chunks) == 1 and chunks[0].text == "Real text."

    def test_raw_text_fallback_when_no_html(self):
        chunks = chunk_note(None, "Line one.\nLine two.")
        assert chunks[0].text == "Line one.\nLine two."

    def test_plain_structured_text_used_before_raw(self):
        chunks = chunk_note("edited plain text", "ocr text")
        assert chunks[0].text == "edited plain text"

    def test_empty_note(self):
        assert chunk_note("", "") == []
        assert chunk_note(None, None) == []

    def test_extract_plain_text_includes_headings(self):
        html = H2.format("Title") + P.format("Body.")
        assert extract_plain_text(html, None) == "Title\nBody."

    def test_entities_unescaped(self):
        assert chunk_note(P.format("a &amp; b &lt; c"), None)[0].text == "a & b < c"


class TestSentences:
    def test_basic_split(self):
        assert split_sentences("One thing. Two things! Three?") == ["One thing.", "Two things!", "Three?"]

    def test_math_not_split_inside_dollars(self):
        s = "Rule: $f(x) = x. y$ holds. Next."
        assert split_sentences(s) == ["Rule: $f(x) = x. y$ holds.", "Next."]

    def test_abbreviations_and_enumerations_not_split(self):
        assert split_sentences("e.g. this stays. Next one.") == ["e.g. this stays.", "Next one."]
        assert split_sentences("1. nucleus holds dna. 2. ribosomes") == ["1. nucleus holds dna.", "2. ribosomes"]
        assert split_sentences("see fig. 3 for details. done") == ["see fig. 3 for details.", "done"]

    def test_uncapitalized_sentences_still_split(self):
        assert split_sentences("mitochondria make atp. ribosomes make protein.") == [
            "mitochondria make atp.", "ribosomes make protein."]


class TestPacking:
    def test_windows_respect_target_and_overlap(self):
        sents = long_sentences(10)              # ~16 tokens each
        cfg = ChunkConfig(target_tokens=40, max_tokens=60, overlap_sentences=1, min_tail_tokens=10)
        wins = pack_windows(sents, cfg)
        assert len(wins) > 1
        for a, b in zip(wins, wins[1:]):
            assert a[-1] == b[0]                 # one-sentence overlap
        assert all(sum(estimate_tokens(s) for s in w) <= cfg.max_tokens for w in wins)
        flat = [s for w in wins for s in w]
        assert set(flat) == set(sents)           # nothing lost

    def test_single_oversized_sentence_kept_whole(self):
        big = " ".join(f"tok{i}" for i in range(100)) + "."
        wins = pack_windows([big, "Small."], ChunkConfig(target_tokens=20, max_tokens=30))
        assert wins[0][0] == big

    def test_tiny_tail_merges_backward(self):
        sents = long_sentences(3) + ["Tail."]
        cfg = ChunkConfig(target_tokens=45, max_tokens=80, overlap_sentences=0, min_tail_tokens=10)
        wins = pack_windows(sents, cfg)
        assert wins[-1][-1] == "Tail." and len(wins[-1]) > 1

    def test_no_duplicate_overlap_only_tail(self):
        sents = long_sentences(3)
        cfg = ChunkConfig(target_tokens=48, max_tokens=80, overlap_sentences=1, min_tail_tokens=1)
        wins = pack_windows(sents, cfg)
        assert wins[-1] != [sents[-1]] or len(wins) == 1


class TestGranularity:
    def _html(self):
        return (H2.format("A") + P.format(" ".join(long_sentences(6)))
                + H2.format("B") + P.format(" ".join(long_sentences(6))))

    def test_note_granularity_single_chunk_with_headings_inline(self):
        chunks = chunk_note(self._html(), None, ChunkConfig(granularity="note"))
        assert len(chunks) == 1 and chunks[0].heading is None
        assert chunks[0].text.startswith("A.")

    def test_section_granularity_one_per_heading(self):
        chunks = chunk_note(self._html(), None, ChunkConfig(granularity="section", max_tokens=500))
        assert [c.heading for c in chunks] == ["A", "B"]

    def test_window_granularity_splits_long_sections(self):
        chunks = chunk_note(self._html(), None, ChunkConfig(granularity="window", target_tokens=40, max_tokens=60))
        assert len(chunks) > 2
        assert [c.ordinal for c in chunks] == list(range(len(chunks)))


class TestHashing:
    def test_chunk_hash_stable_and_sensitive(self):
        a = chunk_note(P.format("Same text."), None)[0]
        b = chunk_note(P.format("Same text."), None)[0]
        c = chunk_note(P.format("Other text."), None)[0]
        assert a.content_hash == b.content_hash != c.content_hash

    def test_note_hash_changes_with_title_and_config(self):
        html = P.format("Body.")
        base = note_content_hash("T", html, None, ChunkConfig())
        assert base == note_content_hash("T", html, None, ChunkConfig())
        assert base != note_content_hash("T2", html, None, ChunkConfig())
        assert base != note_content_hash("T", html, None, ChunkConfig(granularity="note"))

    def test_note_hash_ignores_style_attributes(self):
        a = note_content_hash("T", '<p style="a">x.</p>', None, ChunkConfig())
        b = note_content_hash("T", '<p style="b">x.</p>', None, ChunkConfig())
        assert a == b


def test_build_context():
    assert build_context("Note", "Sec") == "Note > Sec"
    assert build_context("Note", None) == "Note"
    assert build_context(None, None) == ""
