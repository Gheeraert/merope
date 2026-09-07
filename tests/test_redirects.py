"""bloggen.build.redirects: static meta-refresh stubs generated when a
slug (hence URL) changes, tracked across builds via a small on-disk
history keyed by the content's stable source-file identity — a slug
edit doesn't rename the .md file itself.
"""

from __future__ import annotations

from pathlib import Path
import uuid

from bloggen.build.redirects import (
    load_url_history,
    plan_redirects,
    render_redirect_html,
    save_url_history,
    update_history,
)

RUNTIME_ROOT = Path("tests/.runtime")
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)


def test_update_history_records_a_first_seen_url():
    history = update_history({}, {"content/posts/a.md": "/billets/a/index.html"})
    assert history == {"content/posts/a.md": ["/billets/a/index.html"]}


def test_update_history_appends_a_changed_url_without_dropping_the_old_one():
    history = {"content/posts/a.md": ["/billets/ancien-slug/index.html"]}
    updated = update_history(history, {"content/posts/a.md": "/billets/nouveau-slug/index.html"})
    assert updated["content/posts/a.md"] == [
        "/billets/ancien-slug/index.html",
        "/billets/nouveau-slug/index.html",
    ]


def test_update_history_does_not_duplicate_an_unchanged_url():
    history = {"content/posts/a.md": ["/billets/a/index.html"]}
    updated = update_history(history, {"content/posts/a.md": "/billets/a/index.html"})
    assert updated["content/posts/a.md"] == ["/billets/a/index.html"]


def test_update_history_does_not_mutate_the_input():
    history = {"content/posts/a.md": ["/billets/a/index.html"]}
    update_history(history, {"content/posts/a.md": "/billets/b/index.html"})
    assert history["content/posts/a.md"] == ["/billets/a/index.html"]


def test_plan_redirects_targets_the_current_url_for_a_renamed_slug():
    history = {
        "content/posts/a.md": ["/billets/ancien-slug/index.html", "/billets/nouveau-slug/index.html"]
    }
    current = {"content/posts/a.md": "/billets/nouveau-slug/index.html"}
    plans = plan_redirects(history, current)
    assert len(plans) == 1
    assert plans[0].stale_url == "/billets/ancien-slug/index.html"
    assert plans[0].target_url == "/billets/nouveau-slug/index.html"


def test_plan_redirects_chains_a_slug_renamed_twice_straight_to_the_latest():
    """A -> B -> C: both A and B must redirect straight to C, not A -> B."""
    history = {"content/posts/a.md": ["/billets/a/index.html", "/billets/b/index.html", "/billets/c/index.html"]}
    current = {"content/posts/a.md": "/billets/c/index.html"}
    plans = plan_redirects(history, current)
    targets = {plan.stale_url: plan.target_url for plan in plans}
    assert targets == {
        "/billets/a/index.html": "/billets/c/index.html",
        "/billets/b/index.html": "/billets/c/index.html",
    }


def test_plan_redirects_skips_content_with_no_current_url():
    """Deleted/drafted content: nothing sound to redirect its old URL to."""
    history = {"content/posts/a.md": ["/billets/a/index.html"]}
    plans = plan_redirects(history, current={})
    assert plans == []


def test_plan_redirects_never_overwrites_another_pages_current_url():
    """The old slug of post A was reused by an unrelated post B — B's
    real, current page must never be replaced by a redirect stub."""
    history = {
        "content/posts/a.md": ["/billets/reprise/index.html", "/billets/a-nouveau/index.html"],
        "content/posts/b.md": ["/billets/reprise/index.html"],
    }
    current = {
        "content/posts/a.md": "/billets/a-nouveau/index.html",
        "content/posts/b.md": "/billets/reprise/index.html",
    }
    plans = plan_redirects(history, current)
    assert all(plan.stale_url != "/billets/reprise/index.html" for plan in plans)


def test_plan_redirects_is_empty_when_nothing_changed():
    history = {"content/posts/a.md": ["/billets/a/index.html"]}
    current = {"content/posts/a.md": "/billets/a/index.html"}
    assert plan_redirects(history, current) == []


def test_render_redirect_html_escapes_and_meta_refreshes():
    html = render_redirect_html("../nouveau-slug/index.html")
    assert 'meta http-equiv="refresh" content="0; url=../nouveau-slug/index.html"' in html
    assert 'rel="canonical" href="../nouveau-slug/index.html"' in html
    assert 'name="robots" content="noindex"' in html


def test_render_redirect_html_escapes_special_characters_in_the_href():
    html = render_redirect_html("../a&b/index.html")
    assert "../a&amp;b/index.html" in html
    assert "../a&b/index.html" not in html.split("<body>")[0]


def test_url_history_round_trips_through_disk():
    history_path = RUNTIME_ROOT / f"url_history_{uuid.uuid4().hex}" / "history.json"
    history = {
        "content/posts/a.md": ["/billets/a/index.html", "/billets/a-bis/index.html"],
        "content/pages/accueil.md": ["/accueil/index.html"],
    }
    save_url_history(history_path, history)
    assert load_url_history(history_path) == history


def test_load_url_history_returns_empty_dict_when_the_file_is_missing():
    assert load_url_history(RUNTIME_ROOT / f"does-not-exist-{uuid.uuid4().hex}.json") == {}


def test_load_url_history_returns_empty_dict_for_malformed_json():
    history_path = RUNTIME_ROOT / f"url_history_bad_{uuid.uuid4().hex}" / "history.json"
    history_path.parent.mkdir(parents=True)
    history_path.write_text("not json at all", encoding="utf-8")
    assert load_url_history(history_path) == {}
