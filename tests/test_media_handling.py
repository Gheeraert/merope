from __future__ import annotations

from pathlib import Path
import uuid

from bloggen.build.assets import copy_linked_content_assets
from bloggen.content.assets import collect_linked_assets, extract_local_image_targets

RUNTIME_ROOT = Path("tests/.runtime")
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)


def test_extract_local_image_targets_ignores_remote_links():
    markdown = (
        "![Local](images/a.jpg)\n"
        "![Web](https://example.org/a.jpg)\n"
        "![Mail](mailto:test@example.org)\n"
        "![Root](/assets/images/root.jpg)\n"
        "![Anchor](#section)\n"
    )

    targets = extract_local_image_targets(markdown)

    assert targets == ["images/a.jpg", "/assets/images/root.jpg"]


def test_collect_and_copy_linked_assets():
    project = RUNTIME_ROOT / f"media_{uuid.uuid4().hex}"
    source_file = project / "content/posts/demo.md"
    source_file.parent.mkdir(parents=True, exist_ok=True)

    local_image = project / "content/posts/media/local.png"
    local_image.parent.mkdir(parents=True, exist_ok=True)
    local_image.write_bytes(b"png")

    global_image = project / "assets/images/global.jpg"
    global_image.parent.mkdir(parents=True, exist_ok=True)
    global_image.write_bytes(b"jpg")

    markdown = "![A](media/local.png)\n![B](../../assets/images/global.jpg)\n![M](missing.png)\n"
    references = collect_linked_assets(source_file, markdown, project_root=project)

    output_root = project / "site"
    html_dir = output_root / "billets/demo"
    html_dir.mkdir(parents=True, exist_ok=True)

    result = copy_linked_content_assets(
        references=references,
        project_root=project,
        output_root=output_root,
        html_output_dir=html_dir,
        source_markdown_path=source_file,
        item_kind="post",
        item_slug="demo",
        assets_dir="assets",
        copy_project_assets_enabled=False,
    )

    assert (output_root / "content-media/post/demo/media/local.png").exists()
    assert (output_root / "assets/images/global.jpg").exists()

    assert result.rewritten_targets["media/local.png"].endswith(
        "content-media/post/demo/media/local.png"
    )
    assert result.rewritten_targets["../../assets/images/global.jpg"] == "../../assets/images/global.jpg"
    assert len(result.missing) == 1
    assert result.missing[0].target == "missing.png"
