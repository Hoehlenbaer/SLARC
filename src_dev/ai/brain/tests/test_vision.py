# brain/tests/test_vision.py
# Version 0.1 (07.11.2026) – compare_vlm gegen einen nachgebauten llama-server.

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from brain.vision import compare_vlm as V


class FakeServer(BaseHTTPRequestHandler):
    answer = {"objects": ["cat", "couch"]}

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["messages"][0]["content"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        props = body["response_format"]["json_schema"]["schema"]["properties"]
        if "objects" in props:
            content = json.dumps(self.answer)
        elif "antwort" in props:
            content = json.dumps({"antwort": props["antwort"]["enum"][0]})
        else:
            content = json.dumps({"text": "Eine Katze liegt auf dem Sofa."})
        out = {"choices": [{"message": {"content": content}}]}
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(out).encode())


def _jpg(path):
    PIL = pytest.importorskip("PIL.Image")
    PIL.new("RGB", (800, 600), (120, 90, 60)).save(path, "JPEG")   # groß genug, um verkleinert zu werden


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), FakeServer)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def coco(tmp_path):
    img = tmp_path / "img"
    img.mkdir()
    for n in ("a.jpg", "b.jpg"):
        _jpg(img / n)
    ann = {"images": [{"id": 1, "file_name": "a.jpg"}, {"id": 2, "file_name": "b.jpg"}],
           "annotations": [{"image_id": 1, "category_id": 17, "area": 5000},      # cat, groß
                           {"image_id": 1, "category_id": 47, "area": 300},       # cup, klein
                           {"image_id": 2, "category_id": 63, "area": 9000}]}     # couch
    p = tmp_path / "ann.json"
    p.write_text(json.dumps(ann))
    return str(p), str(img)


def test_metrics_basic():
    gt_all = {1: {"cat", "cup"}, 2: {"couch"}}
    gt_big = {1: {"cat"}, 2: {"couch"}}
    m = V.metrics({1: {"cat", "dog"}, 2: {"couch"}}, gt_all, gt_big, [1, 2])
    assert m["precision"] == round(2 / 3, 3) and m["recall"] == round(2 / 3, 3)
    assert m["recall_nicht_klein"] == 1.0 and ("dog", 1) in m["erfunden"]


def test_coco_run_two_servers(server, coco, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(V, "out_paths", lambda stem: (str(tmp_path / "r.md"), str(tmp_path / "r.json")))
    ann, img = coco
    monkeypatch.setattr(sys, "argv", ["x", "--server", f"A={server}", "--server", f"B={server}",
                                      "--coco-ann", ann, "--coco-img", img, "-n", "2", "--describe", "1"])
    V.main()
    rep = (tmp_path / "r.md").read_text()
    assert "| A |" in rep and "| B |" in rep and "Eine Katze liegt auf dem Sofa." in rep
    res = json.loads((tmp_path / "r.json").read_text())
    assert res["modelle"]["A"]["recall"] == round(2 / 3, 3)     # cat, couch gefunden, cup übersehen


def test_questions(server, tmp_path, monkeypatch):
    monkeypatch.setattr(V, "out_paths", lambda stem: (str(tmp_path / "q.md"), str(tmp_path / "q.json")))
    _jpg(tmp_path / "f.jpg")
    q = [{"bild": "f.jpg", "frage": "Fenster offen?", "antworten": ["ja", "nein"], "richtig": "ja"}]
    (tmp_path / "q_in.json").write_text(json.dumps(q))
    monkeypatch.setattr(sys, "argv", ["x", "--server", f"4B={server}", "--questions", str(tmp_path / "q_in.json")])
    V.main()
    assert "4B: 1/1 richtig" in (tmp_path / "q.md").read_text()
