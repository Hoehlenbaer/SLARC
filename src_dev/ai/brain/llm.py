# brain/llm.py
# Version 0.5 (08.11.2026) – LLM-Anbindung für die Zielwahl.
# V0.2: n_gpu_layers wählbar (PC mit CUDA), Modellordner H: auch unter WSL.
# V0.5 (08.11.2026): ServerBrain – llama-server über HTTP mit festem Slot je Aufgabe.
#       Grund: Pi-Messung 08.11.2026, mit einem Slot kostet jeder Aufgabenwechsel 30–70 s
#       (fester Prompt-Teil neu), im Cache 9–14 s. Server dazu mit -np N starten.
#       Wartet beim Anlegen bis zu wait_s auf /health (sonst Fehler statt lauter Fehlantworten).
# V0.4: ~/.models zuerst durchsuchen (unter WSL lädt /mnt/… über 9P ~1 min).
# V0.3: generate() für beliebige Aufgaben mit eigener Grammatik (semantic.py);
#       optionaler RAM-Cache, damit mehrere Systemprompts im Cache bleiben.
#
# LlamaBrain: llama.cpp über llama-cpp-python, Ausgabe per GBNF erzwungen.
#   Systemprompt und Few-Shot sind konstant; llama.cpp verwendet den
#   KV-Cache für den gleichen Präfix weiter, je Aufruf ist nur der
#   Zustandstext neu zu rechnen.
# MockBrain: regelbasiert, für Tests ohne Modell.
#
# Modellsuche wie in exploration_manager_V4.py (Skriptordner, H:/…, ~/.models).

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from dataclasses import dataclass
from typing import Optional

from .behaviors import MOODS
from .prompt import grammar, messages

DEFAULT_MODEL = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
SEARCH_PATHS = [
    os.path.expanduser("~/.models/"),      # zuerst: Linux-Dateisystem, schnell
    os.path.dirname(os.path.abspath(__file__)),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."),
    "H:/SLARC_resources/models/",
    "/mnt/h/SLARC_resources/models/",     # dasselbe unter WSL
    "/home/admin/.models/",
]
TIMEOUT_S = 60.0     # danach Code-Auswahl (Konzept 8.2)


@dataclass
class Generation:
    raw: str
    latency_s: float
    tokens_in: int = 0
    tokens_out: int = 0
    error: str = ""


@dataclass
class LLMResult:
    choice: Optional[int]          # 1-basiert, None = ungültig/Zeitüberschreitung
    reason: str
    mood: str
    raw: str
    latency_s: float
    tokens_in: int = 0
    tokens_out: int = 0
    error: str = ""


def find_model(name_or_path: str) -> Optional[str]:
    if os.path.exists(name_or_path):
        return name_or_path
    for p in SEARCH_PATHS:
        c = os.path.join(p, name_or_path)
        if os.path.exists(c):
            return c
    return None


def parse(raw: str, n_options: int) -> tuple[Optional[int], str, str, str]:
    """Antwort prüfen. Mit Grammatik sollte nie etwas schiefgehen; ohne
    (z. B. anderes Backend) fängt das hier halluzinierte Werte ab."""
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, "", "", f"kein JSON: {e}"
    z = d.get("ziel")
    if not isinstance(z, int) or not 1 <= z <= n_options:
        return None, "", "", f"ziel ungültig: {z!r}"
    mood = d.get("stimmung", "")
    if mood not in MOODS:
        mood = "ruhig"
    return z, str(d.get("begruendung", "")).strip(), mood, ""


class LlamaBrain:
    def __init__(self, model: str = DEFAULT_MODEL, n_threads: int = 4,
                 n_ctx: int = 3072, temperature: float = 0.3, n_gpu_layers: int = 0,
                 verbose: bool = False, ram_cache_mb: int = 0):
        from llama_cpp import Llama, LlamaGrammar   # erst hier, damit Tests ohne llama_cpp laufen
        path = find_model(model)
        if path is None:
            raise FileNotFoundError(f"Modell nicht gefunden: {model}")
        self.name = os.path.basename(path)
        self._grammar_cls = LlamaGrammar
        self._grammars: dict = {}
        self.temperature = temperature
        self.llm = Llama(model_path=path, n_ctx=n_ctx, n_threads=n_threads,
                         n_gpu_layers=n_gpu_layers, use_mmap=True, verbose=verbose)
        self._pool = ThreadPoolExecutor(max_workers=1)
        if ram_cache_mb > 0:
            # Ohne Cache rechnet llama.cpp den Systemprompt neu, sobald zwischen
            # Aufgaben (Entscheidung, Chat, Objekt …) gewechselt wird. Auf dem Pi
            # kostet das je Wechsel ~1000 Tokens. KV-Zustand je Präfix bei 4B grob
            # 150 MB, also für 5 Aufgaben ~800 MB (Annahme, messen).
            from llama_cpp import LlamaRAMCache
            self.llm.set_cache(LlamaRAMCache(capacity_bytes=ram_cache_mb << 20))

    def _grammar(self, key):
        """key: Anzahl Menüoptionen (Zielwahl) oder ein GBNF-Text."""
        if key not in self._grammars:
            gbnf = grammar(key) if isinstance(key, int) else key
            self._grammars[key] = self._grammar_cls.from_string(gbnf, verbose=False)
        return self._grammars[key]

    def _gen(self, msgs: list[dict], gbnf: str, max_tokens: int, temperature: float) -> Generation:
        t0 = time.perf_counter()
        r = self.llm.create_chat_completion(msgs, grammar=self._grammar(gbnf), temperature=temperature,
                                            top_p=0.9, top_k=40, max_tokens=max_tokens)
        u = r.get("usage", {})
        return Generation(r["choices"][0]["message"]["content"].strip(), time.perf_counter() - t0,
                          u.get("prompt_tokens", 0), u.get("completion_tokens", 0))

    def generate(self, msgs: list[dict], gbnf: str, max_tokens: int = 160,
                 temperature: float = 0.2, timeout_s: float = TIMEOUT_S) -> Generation:
        """Beliebige Aufgabe mit erzwungener Grammatik (semantic.py)."""
        fut = self._pool.submit(self._gen, msgs, gbnf, max_tokens, temperature)
        try:
            return fut.result(timeout=timeout_s)
        except FutTimeout:
            return Generation("", timeout_s, error="Zeitüberschreitung")

    def warmup(self) -> float:
        """Systemprompt und Few-Shot einmal rechnen, damit sie im Cache liegen."""
        t0 = time.perf_counter()
        self.llm.create_chat_completion(messages("ANLASS: keiner\nMÖGLICHE ZIELE\n1 Sich umsehen"),
                                        max_tokens=1, temperature=0.0)
        return time.perf_counter() - t0

    def _call(self, state: str, n: int) -> LLMResult:
        t0 = time.perf_counter()
        r = self.llm.create_chat_completion(
            messages(state), grammar=self._grammar(n),
            temperature=self.temperature, top_p=0.9, top_k=40, max_tokens=120,
        )
        lat = time.perf_counter() - t0
        raw = r["choices"][0]["message"]["content"].strip()
        z, reason, mood, err = parse(raw, n)
        u = r.get("usage", {})
        return LLMResult(z, reason, mood, raw, lat, u.get("prompt_tokens", 0),
                         u.get("completion_tokens", 0), err)

    def decide(self, state: str, n_options: int, timeout_s: float = TIMEOUT_S) -> LLMResult:
        fut = self._pool.submit(self._call, state, n_options)
        try:
            return fut.result(timeout=timeout_s)
        except FutTimeout:
            # llama.cpp lässt sich nicht abbrechen; das Ergebnis wird verworfen
            return LLMResult(None, "", "", "", timeout_s, error="Zeitüberschreitung")


# ---------------------------------------------------------------- [V0.5] llama-server
# Feste Slots nach Wichtigkeit; was keinen eigenen Slot bekommt, teilt sich den letzten.
TASK_SLOTS = ("zielwahl", "chat", "objekt", "suchen", "plaudern", "tagebuch", "bild")


def task_of(msgs: list[dict]) -> str:
    """Aufgabe am Systemprompt erkennen: 'AUFGABE: x' (semantic.py), sonst Zielwahl/Bild."""
    first = msgs[0] if msgs else {}
    if first.get("role") != "system":
        return "bild" if isinstance(first.get("content"), list) else "zielwahl"
    head = str(first.get("content", "")).split("\n", 1)[0]
    return head.split(":", 1)[1].strip() if head.startswith("AUFGABE:") else "zielwahl"


def slot_of(task: str, n_slots: int) -> int:
    i = TASK_SLOTS.index(task) if task in TASK_SLOTS else len(TASK_SLOTS)
    return min(i, n_slots - 1)


class ServerBrain:
    """Wie LlamaBrain, aber über llama-server (HTTP). Mit n_slots > 1 bekommt jede Aufgabe
    einen festen Slot (id_slot), damit ihr fester Prompt-Teil im Cache bleibt.
    Server: llama-server -m … -np 4 -c 12288 --cache-ram 0 (je Slot c/np Tokens)."""

    def __init__(self, url: str = "http://127.0.0.1:8080", n_slots: int = 1, temperature: float = 0.3,
                 wait_s: float = 120.0):
        self.url = url.rstrip("/")
        self.n_slots = max(1, n_slots)
        self.temperature = temperature
        self.name = "server"
        t_end = time.monotonic() + wait_s
        while True:                                   # Server lädt evtl. noch das Modell
            try:
                with urllib.request.urlopen(self.url + "/health", timeout=5) as r:
                    if r.status == 200:
                        break
            except (OSError, ValueError):
                pass
            if time.monotonic() > t_end:
                raise ConnectionError(f"llama-server unter {self.url} nach {wait_s:.0f} s nicht bereit")
            time.sleep(1.0)
        try:
            with urllib.request.urlopen(self.url + "/props", timeout=10) as r:
                self.name = os.path.basename(json.loads(r.read()).get("model_path") or "") or "server"
        except (OSError, ValueError):
            pass

    def _post(self, body: dict, timeout_s: float) -> dict:
        req = urllib.request.Request(self.url + "/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return json.loads(r.read())

    def generate(self, msgs: list[dict], gbnf: Optional[str], max_tokens: int = 160,
                 temperature: float = 0.2, timeout_s: float = TIMEOUT_S) -> Generation:
        body = {"messages": msgs, "temperature": temperature, "top_p": 0.9, "top_k": 40,
                "max_tokens": max_tokens, "cache_prompt": True,
                "chat_template_kwargs": {"enable_thinking": False}}
        if gbnf:
            body["grammar"] = gbnf
        if self.n_slots > 1:
            body["id_slot"] = slot_of(task_of(msgs), self.n_slots)
        t0 = time.perf_counter()
        try:
            out = self._post(body, timeout_s)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return Generation("", time.perf_counter() - t0, error=f"Server: {e}")
        tm = out.get("timings") or {}
        return Generation(out["choices"][0]["message"]["content"].strip(), time.perf_counter() - t0,
                          tm.get("prompt_n", 0), tm.get("predicted_n", 0))

    def warmup(self) -> float:
        t0 = time.perf_counter()
        self.generate(messages("ANLASS: keiner\nMÖGLICHE ZIELE\n1 Sich umsehen"), None, 1, 0.0)
        return time.perf_counter() - t0

    def decide(self, state: str, n_options: int, timeout_s: float = TIMEOUT_S) -> LLMResult:
        g = self.generate(messages(state), grammar(n_options), 120, self.temperature, timeout_s)
        if g.error:
            return LLMResult(None, "", "", "", g.latency_s, error=g.error)
        z, reason, mood, err = parse(g.raw, n_options)
        return LLMResult(z, reason, mood, g.raw, g.latency_s, g.tokens_in, g.tokens_out, err)


class MockBrain:
    """Ohne Modell: wählt das erste Ziel, dessen Text ein Stichwort enthält,
    sonst Ziel 1 (= höchster Code-Nutzen). Nur für Tests der Kette."""
    name = "mock"

    def __init__(self, prefer: tuple[str, ...] = ("Bitte", "begrüßen", "untersuchen"), responder=None):
        self.prefer = prefer
        self.responder = responder    # f(msgs, gbnf) -> str, für generate()

    def generate(self, msgs: list[dict], gbnf: str, max_tokens: int = 160,
                 temperature: float = 0.2, timeout_s: float = TIMEOUT_S) -> Generation:
        if self.responder is None:
            return Generation("", 0.0, error="Mock ohne responder")
        return Generation(self.responder(msgs, gbnf), 0.0)

    def warmup(self) -> float:
        return 0.0

    def decide(self, state: str, n_options: int, timeout_s: float = TIMEOUT_S) -> LLMResult:
        menu = state.split("MÖGLICHE ZIELE\n", 1)[-1].splitlines()
        choice = 1
        for kw in self.prefer:
            hit = next((i for i, l in enumerate(menu, 1) if kw in l), None)
            if hit:
                choice = hit
                break
        raw = json.dumps({"begruendung": "Mock", "ziel": choice, "stimmung": "ruhig"})
        z, reason, mood, err = parse(raw, n_options)
        return LLMResult(z, reason, mood, raw, 0.0, error=err)
