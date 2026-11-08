# brain/tests/test_pi_bench.py
# Version 0.2 (08.11.2026) – bench_pi und export_subset gegen nachgebauten Server bzw. Mini-COCO.
# V0.2: Label, /props und Übersicht mehrerer Läufe (run_pi_matrix.sh).

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

PIL = pytest.importorskip("PIL.Image")

from brain.vision import bench_pi, export_subset  # noqa: E402


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        p = {"model_path": "/m/Qwen3.5-2B-Q4_K_M.gguf", "modalities": {"vision": True}} if self.path == "/props" else {}
        self.wfile.write(json.dumps(p).encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        last = body["messages"][-1]["content"]
        has_img = isinstance(last, list)
        props = body.get("response_format", {}).get("json_schema", {}).get("schema", {}).get("properties", {})
        text = json.dumps({"objects": ["cat"]} if "objects" in props else {"antwort": "nein"}) if has_img else "{}"
        out = {"choices": [{"message": {"content": text}}],
               "timings": {"prompt_n": 300 if has_img else 1200, "prompt_ms": 3000.0, "cache_n": 0,
                           "predicted_n": 20, "predicted_ms": 4000.0}}
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(out).encode())


@pytest.fixture
def url():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_bench_pi(url, tmp_path, monkeypatch):
    img = tmp_path / "img"
    img.mkdir()
    for n in ("a.jpg", "b.jpg"):
        PIL.new("RGB", (1000, 750)).save(img / n, "JPEG")
    monkeypatch.setattr(bench_pi, "out_paths", lambda s: (str(tmp_path / "p.md"), str(tmp_path / "p.json")))
    monkeypatch.setattr(sys, "argv", ["x", "--url", url, "--images", str(img), "--sizes", "320,640"])
    bench_pi.main()
    res = json.loads((tmp_path / "p.json").read_text())
    assert res["bild"]["320"]["rows"][0]["px"] == [320, 240]
    assert res["bild"]["640"]["prompt_tok_s"] == 100.0
    assert set(res["text"]) == {"zielwahl", "chat", "objekt", "suchorte"}
    assert "| 640 px |" in (tmp_path / "p.md").read_text()


def test_export_subset(tmp_path, monkeypatch):
    coco = tmp_path / "coco"
    (coco / "annotations").mkdir(parents=True)
    (coco / "val2017").mkdir()
    for n in ("1.jpg", "2.jpg", "3.jpg"):
        PIL.new("RGB", (10, 10)).save(coco / "val2017" / n, "JPEG")
    ann = {"images": [{"id": i, "file_name": f"{i}.jpg"} for i in (1, 2, 3)],
           "annotations": [{"image_id": 1, "category_id": 63, "area": 1},      # couch -> Innenraum
                           {"image_id": 2, "category_id": 28, "area": 1},      # umbrella allein -> nicht
                           {"image_id": 3, "category_id": 70, "area": 1}],     # toilet -> Innenraum
           "categories": []}
    (coco / "annotations" / "instances_val2017.json").write_text(json.dumps(ann))
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["x", "--coco", str(coco), "-n", "5", "--out", str(out)])
    export_subset.main()
    assert sorted(os.listdir(out / "val2017")) == ["1.jpg", "3.jpg"]
    sub = json.loads((out / "annotations" / "instances_subset.json").read_text())
    assert {a["image_id"] for a in sub["annotations"]} == {1, 3}


def test_bench_text_only(url, tmp_path, monkeypatch):
    monkeypatch.setattr(bench_pi, "out_paths", lambda s: (str(tmp_path / "t.md"), str(tmp_path / "t.json")))
    monkeypatch.setattr(sys, "argv", ["x", "--url", url, "--text-only"])
    bench_pi.main()
    res = json.loads((tmp_path / "t.json").read_text())
    assert res["bild"] == {} and "zielwahl" in res["text"]
    assert "Bildfragen" not in (tmp_path / "t.md").read_text()


def test_label_props_and_summary(url, tmp_path, monkeypatch):
    img = tmp_path / "img"
    img.mkdir()
    PIL.new("RGB", (800, 600)).save(img / "a.jpg", "JPEG")
    paths = {"pi_bench_q35-2b": tmp_path / "a", "pi_bench_q3-text": tmp_path / "b", "pi_matrix": tmp_path / "m"}
    monkeypatch.setattr(bench_pi, "out_paths", lambda s: (str(paths[s]) + ".md", str(paths[s]) + ".json"))
    monkeypatch.setattr(sys, "argv", ["x", "--url", url, "--images", str(img), "-n", "1", "--sizes", "320",
                                      "--label", "q35-2b", "--mmproj", "mm-q8.gguf"])
    bench_pi.main()
    monkeypatch.setattr(sys, "argv", ["x", "--url", url, "--text-only", "--label", "q3-text"])
    bench_pi.main()
    a = json.loads((tmp_path / "a.json").read_text())
    assert a["modell"] == "Qwen3.5-2B-Q4_K_M.gguf" and a["label"] == "q35-2b"
    assert a["text"]["zielwahl"]["prompt_tok_s"] == 400.0
    assert "mm-q8.gguf" in (tmp_path / "a.md").read_text()
    monkeypatch.setattr(sys, "argv", ["x", "--summarize", str(tmp_path / "a.json"), str(tmp_path / "b.json")])
    bench_pi.main()
    m = (tmp_path / "m.md").read_text()
    assert "| q35-2b |" in m and "| q3-text |" in m and "Dose 320 px" in m
