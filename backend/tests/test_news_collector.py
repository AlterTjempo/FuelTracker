"""The news collector must survive bad articles instead of losing the whole run."""

from services.news_collector import clean_article, dedupe_batch


def test_duplicate_links_in_one_run_are_collapsed():
    batch = [
        {"link": "http://a/1", "source": "EIA", "title": "x"},
        {"link": "http://a/2", "source": "EIA", "title": "y"},
        {
            "link": "http://a/1 ",
            "source": "Rigzone",
            "title": "same article, second feed",
        },
        {"link": "", "source": "EIA", "title": "no link"},
    ]
    out = dedupe_batch(batch)
    assert [a["link"] for a in out] == ["http://a/1", "http://a/2"]
    assert out[0]["source"] == "EIA"  # first one wins


def test_nul_and_control_characters_are_removed():
    a = clean_article(
        {
            "title": "ti\x00tle",
            "link": " http://a/1\x00 ",
            "summary": "bad\x00te\x07xt\nkeeps newlines\t and tabs",
        }
    )
    assert "\x00" not in a["title"] + a["link"] + a["summary"]
    assert a["link"] == "http://a/1"
    assert "\n" in a["summary"] and "\t" in a["summary"]  # normal whitespace is kept


def test_overlong_text_is_capped_and_none_is_kept():
    a = clean_article(
        {"title": "t" * 5000, "link": "http://a/1", "summary": "s" * 50000}
    )
    assert len(a["title"]) <= 1000 and len(a["summary"]) <= 20000
    assert (
        clean_article({"title": "t", "link": "http://a/1", "summary": None})["summary"]
        is None
    )
