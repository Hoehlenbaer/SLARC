# brain/tests/test_identify.py
# Version 0.1 (08.11.2026) – identify.py und crops_vlm.py gegen nachgebauten Server und Mini-COCO.

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

PIL = pytest.importorskip("PIL.Image")

from brain.vision import crops_vlm as C  # noqa: E402
from brain.vision import identify as I  # noqa: E402

SEEN = []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        parts = body["messages"][0]["content"]
        assert parts[0]["type"] == "text" and parts[1]["type"] == "image_url"   # Text vor dem Bild (Cache)
        props = body["response_format"]["json_schema"]["schema"]["properties"]
        if "anderes" in props:
            ans = {"name": "gabel", "anderes": "", "sicher": "ja"}
        else:
            ans = {"name": "Die Schere", "sicher": "nein"}
        out = {"choices": [{"message": {"content": json.dumps(ans)}}],
               "timings": {"prompt_n": 120, "predicted_n": 9}}
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(out).encode())


@pytest.fixture(scope="module")
def url():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_crop_square_with_margin(tmp_path):
    p = tmp_path / "a.jpg"
    PIL.new("RGB", (640, 480), "white").save(p)
    jpg = I.crop_jpeg(str(p), (100, 100, 40, 20), 0.25, 224)
    im = PIL.open(__import__("io").BytesIO(jpg))
    assert im.size == (224, 224)                                  # quadratisch, skaliert
    jpg = I.crop_jpeg(str(p), (620, 0, 20, 20), 0.25, 160)       # am Rand: abgeschnitten, nicht verzerrt
    assert max(PIL.open(__import__("io").BytesIO(jpg)).size) == 160


def test_identify_modes(url):
    jpg = I.crop_jpeg(PIL.new("RGB", (100, 100)), (10, 10, 50, 50))
    r = I.identify(url, jpg, "liste", slot=3)
    assert r.name == "gabel" and r.sure and r.prompt_n == 120 and SEEN[-1]["id_slot"] == 3
    r = I.identify(url, jpg, "frei")
    assert r.name == "schere" and not r.sure and "id_slot" not in SEEN[-1]
    assert "anderes" in I.VOCAB + [I.OTHER] and "handy" in I.VOCAB and len(set(I.VOCAB)) == len(I.VOCAB)


def test_correct_matching():
    assert C.correct("tennis racket", "tennisschläger") and C.correct("fork", "gabel")
    assert not C.correct("train", "flugzeug") and not C.correct("fork", None)
    assert C.correct("cell phone", "smartphone") and not C.correct("cell phone", "laptop")
    assert set(C.EXPECT) | set(C.EN2DE) >= {"fork", "scissors", "cat"} and len(C.EXPECT) == 40


def test_crops_main_on_mini_coco(url, tmp_path, monkeypatch):
    img = tmp_path / "img"
    img.mkdir()
    PIL.new("RGB", (320, 240)).save(img / "1.jpg")
    ann = {"images": [{"id": 1, "file_name": "1.jpg"}],
           "categories": [{"id": 48, "name": "fork"}, {"id": 87, "name": "scissors"}, {"id": 17, "name": "cat"}],
           "annotations": [{"image_id": 1, "category_id": 48, "bbox": [10, 10, 60, 40]},
                           {"image_id": 1, "category_id": 87, "bbox": [100, 50, 50, 50]},
                           {"image_id": 1, "category_id": 87, "bbox": [0, 0, 10, 10]},      # zu klein
                           {"image_id": 1, "category_id": 17, "bbox": [150, 100, 80, 80]}]}
    (tmp_path / "ann.json").write_text(json.dumps(ann))
    monkeypatch.setattr(C, "out_paths", lambda s: (str(tmp_path / "r.md"), str(tmp_path / "r.json")))
    monkeypatch.setattr(sys, "argv", ["x", "--server", f"4B={url}", "--coco-ann", str(tmp_path / "ann.json"),
                                      "--coco-img", str(img), "--sides", "160,224", "--known"])
    C.main()
    r = json.loads((tmp_path / "r.json").read_text())
    s = r["laeufe"]["4B|liste|160"]["summary"]
    assert r["boxen"] == 3 and s["n_unbekannt"] == 2 and s["treffer_unbekannt"] == 0.5   # gabel richtig, schere nicht
    assert r["laeufe"]["4B|frei|224"]["summary"]["treffer_unbekannt"] == 0.5             # schere richtig, gabel nicht
    assert "Je Klasse" in (tmp_path / "r.md").read_text()
