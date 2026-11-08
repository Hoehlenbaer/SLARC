# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 15:11)

Modell `Qwen3.5-4B-Q4_K_M.gguf`, mmproj `mmproj-Qwen3.5-4B-Q8_0.gguf`, Lauf `q35-4b-q4km-q8`.

3 Bilder. Temperatur 54.0 → 66.7 °C, Drosselung throttled=0x0 → throttled=0x0, Server 6119 MB, frei 3810 MB.

**Bildfragen** (Median je Bild)

| längste Kante | Bild+Frage Tokens | Prompt tok/s | Erzeugung tok/s | ja/nein (Dose) | Liste (40 Klassen) |
|---|---|---|---|---|---|
| 320 px | 124 | 14.3 | 3.7 | 10.64 s | 17.17 s |
| 448 px | 184 | 13.6 | 3.6 | 15.59 s | 23.17 s |

**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 70.18 s | 1132 | 19.3 | 12.05 s | 4 | 3.3 |
| chat | 42.81 s | 689 | 19.9 | 8.56 s | 4 | 3.4 |
| objekt | 27.91 s | 332 | 19.3 | 11.04 s | 4 | 3.5 |
| suchorte | 22.09 s | 219 | 19.6 | 11.3 s | 4 | 3.5 |

Hinweis: „nach Wechsel“ = der feste Teil des Prompts musste neu gerechnet werden (mit -np 1 hält der Server nur einen Prompt im Cache).
