"""Unit tests for the standalone mobile bundle assembler."""

import base64
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "mobile" / "build_standalone.py"
SPEC = importlib.util.spec_from_file_location("mobile_build_standalone", MODULE_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def _manifest_from_head(head):
    marker = 'rel="manifest" href="data:application/manifest+json;base64,'
    encoded = head.split(marker, 1)[1].split('"', 1)[0]
    return json.loads(base64.b64decode(encoded).decode("utf-8"))


def test_head_metadata_contains_installable_offline_manifest():
    head = builder.head_meta()
    manifest = _manifest_from_head(head)

    assert manifest["lang"] == "ar"
    assert manifest["dir"] == "rtl"
    assert manifest["display"] == "standalone"
    assert manifest["theme_color"] == builder.THEME
    assert {(icon["sizes"], icon["type"]) for icon in manifest["icons"]} == {
        ("192x192", "image/png"),
        ("512x512", "image/png"),
    }
    assert all(icon["src"].startswith("data:image/png;base64,")
               for icon in manifest["icons"])
    assert 'rel="apple-touch-icon"' in head
    assert 'name="theme-color"' in head


def test_inline_guards_escape_scripts_and_reject_style_terminators(tmp_path):
    assert builder.safe_js("before</script>after") == "before<\\/script>after"
    assert builder.safe_js("ordinary data") == "ordinary data"

    safe = tmp_path / "safe.css"
    safe.write_text("body { color: red; }", encoding="utf-8")
    assert builder.read_css(safe) == "body { color: red; }"

    unsafe = tmp_path / "unsafe.css"
    unsafe.write_text("body{} </StYlE><script>bad()</script>", encoding="utf-8")
    with pytest.raises(SystemExit, match="would truncate the inlined block"):
        builder.read_css(unsafe)


def test_read_reports_missing_repository_input():
    missing = ROOT / "mobile" / "definitely-missing-test-input.js"
    with pytest.raises(SystemExit, match=r"missing input: mobile/definitely-missing"):
        builder.read(missing)


def test_build_inlines_inputs_in_runtime_order_and_escapes_payloads(tmp_path, monkeypatch):
    app = tmp_path / "mobile"
    src = app / "src"
    snaps = app / "data" / "snapshots"
    vendor = app / "vendor"
    assets = app / "assets"
    fonts = tmp_path / "fonts"
    for directory in (src, snaps, vendor, assets, fonts):
        directory.mkdir(parents=True, exist_ok=True)

    (vendor / "vendor.js").write_text("window.vendorLoaded=true;", encoding="utf-8")
    (tmp_path / "echarts.js").write_text("window.chartLoaded=true;", encoding="utf-8")
    (tmp_path / "data.js").write_text("window.DASH_DATA={};", encoding="utf-8")
    (tmp_path / "margin.json").write_text('{"note":"</script>"}', encoding="utf-8")
    (src / "one.js").write_text("window.moduleLoaded=true;", encoding="utf-8")
    (src / "app.css").write_text("body{direction:rtl}", encoding="utf-8")
    (snaps / "index.json").write_text(
        json.dumps([{"file": "snapshot.json", "label": "one"}]), encoding="utf-8")
    (snaps / "snapshot.json").write_text('{"value":"</script>"}', encoding="utf-8")
    for name in ("logo-header.png", "special-logo.png", "icon-192.png",
                 "icon-512.png", "apple-touch-icon.png"):
        (assets / name).write_bytes(("image-" + name).encode())
    (fonts / "font.woff2").write_bytes(b"font")

    monkeypatch.setattr(builder, "APP", app)
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(builder, "SRC", src)
    monkeypatch.setattr(builder, "SNAPS", snaps)
    monkeypatch.setattr(builder, "ECHARTS", tmp_path / "echarts.js")
    monkeypatch.setattr(builder, "DASH_DATA_JS", tmp_path / "data.js")
    monkeypatch.setattr(builder, "MARGIN_JSON", tmp_path / "margin.json")
    monkeypatch.setattr(builder, "FONT_DIR", fonts)
    monkeypatch.setattr(builder, "ASSETS", assets)
    monkeypatch.setattr(builder, "FONTS", {"font.woff2": 400})
    monkeypatch.setattr(builder, "VENDOR", ["vendor.js"])
    monkeypatch.setattr(builder, "MODULES", ["one.js", "missing.js"])

    destination = builder.build()
    output = destination.read_text(encoding="utf-8")

    assert destination == app / "dist" / "Abu_Hashem_Mobile_standalone.html"
    ordered_markers = [
        "window.vendorLoaded", "window.chartLoaded", "window.DASH_DATA",
        "window.DASH_BRAND", "window.DASH_MARGIN", 'id="snap-index"',
        'id="snap-snapshot.json"', "window.moduleLoaded",
    ]
    positions = [output.index(marker) for marker in ordered_markers]
    assert positions == sorted(positions)
    assert output.count("<\\/script>") == 2
    assert "missing.js" not in output
    assert "data:font/woff2;base64," in output
    assert "body{direction:rtl}" in output
