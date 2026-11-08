# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 15:01)

Modell `Qwen3.5-4B-Q4_K_M.gguf`, mmproj `mmproj-Qwen3.5-4B-f16.gguf`, Lauf `q35-4b-q4km-f16`.

3 Bilder. Temperatur 51.8 → 63.9 °C, Drosselung throttled=0x0 → throttled=0x0, Server 6230 MB, frei 3548 MB.

**Bildfragen** (Median je Bild)

| längste Kante | Bild+Frage Tokens | Prompt tok/s | Erzeugung tok/s | ja/nein (Dose) | Liste (40 Klassen) |
|---|---|---|---|---|---|
| 320 px | 124 | 7.9 | 3.1 | 17.99 s | 24.9 s |
| 448 px | 184 | 7.2 | 3.1 | 28.03 s | 35.93 s |

**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 72.19 s | 1132 | 19.3 | 14.16 s | 4 | 2.8 |
| chat | 44.3 s | 689 | 19.9 | 10.14 s | 4 | 2.9 |
| objekt | 29.84 s | 332 | 19.3 | 13.06 s | 4 | 2.9 |
| suchorte | 24.25 s | 219 | 19.4 | 13.36 s | 4 | 2.9 |

Hinweis: „nach Wechsel“ = der feste Teil des Prompts musste neu gerechnet werden (mit -np 1 hält der Server nur einen Prompt im Cache).
