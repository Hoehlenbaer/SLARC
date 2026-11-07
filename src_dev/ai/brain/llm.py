# brain/llm.py
# Version 0.2 (07.11.2026) – LLM-Anbindung für die Zielwahl.
# V0.2: n_gpu_layers wählbar (PC mit CUDA), Modellordner H: auch unter WSL.
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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from dataclasses import dataclass
from typing import Optional

from .behaviors import MOODS
from .prompt import grammar, messages

DEFAULT_MODEL = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
SEARCH_PATHS = [
    os.path.dirname(os.path.abspath(__file__)),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."),
    "H:/SLARC_resources/models/",
    "/mnt/h/SLARC_resources/models/",     # dasselbe unter WSL
    "/home/admin/.models/",
    os.path.expanduser("~/.models/"),
]
TIMEOUT_S = 60.0     # danach Code-Auswahl (Konzept 8.2)


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
                 verbose: bool = False):
        from llama_cpp import Llama, LlamaGrammar   # erst hier, damit Tests ohne llama_cpp laufen
        path = find_model(model)
        if path is None:
            raise FileNotFoundError(f"Modell nicht gefunden: {model}")
        self.name = os.path.basename(path)
        self._grammar_cls = LlamaGrammar
        self._grammars: dict[int, object] = {}
        self.temperature = temperature
        self.llm = Llama(model_path=path, n_ctx=n_ctx, n_threads=n_threads,
                         n_gpu_layers=n_gpu_layers, use_mmap=True, verbose=verbose)
        self._pool = ThreadPoolExecutor(max_workers=1)

    def _grammar(self, n: int):
        if n not in self._grammars:
            self._grammars[n] = self._grammar_cls.from_string(grammar(n), verbose=False)
        return self._grammars[n]

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


class MockBrain:
    """Ohne Modell: wählt das erste Ziel, dessen Text ein Stichwort enthält,
    sonst Ziel 1 (= höchster Code-Nutzen). Nur für Tests der Kette."""
    name = "mock"

    def __init__(self, prefer: tuple[str, ...] = ("Bitte", "begrüßen", "untersuchen")):
        self.prefer = prefer

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
