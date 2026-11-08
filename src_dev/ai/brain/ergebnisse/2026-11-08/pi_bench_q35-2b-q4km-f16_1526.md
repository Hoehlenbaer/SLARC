# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 15:26)

Modell `Qwen3.5-2B-Q4_K_M.gguf`, mmproj `mmproj-Qwen3.5-2B-f16.gguf`, Lauf `q35-2b-q4km-f16`.

3 Bilder. Temperatur 51.8 → 65.0 °C, Drosselung throttled=0x0 → throttled=0x0, Server 3442 MB, frei 5159 MB.

**Bildfragen** (Median je Bild)

| längste Kante | Bild+Frage Tokens | Prompt tok/s | Erzeugung tok/s | ja/nein (Dose) | Liste (40 Klassen) |
|---|---|---|---|---|---|
| 320 px | 124 | 10.8 | 7.7 | 12.45 s | 15.98 s |
| 448 px | 184 | 9.3 | 7.6 | 20.62 s | 23.85 s |

**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 28.31 s | 1132 | 50.1 | 5.82 s | 4 | 7.3 |
| chat | 18.37 s | 689 | 51.5 | 5.17 s | 4 | 7.4 |
| objekt | 10.99 s | 332 | 50.4 | 4.61 s | 4 | 7.4 |
| suchorte | 9.51 s | 219 | 50.5 | 5.39 s | 4 | 7.5 |

Hinweis: „nach Wechsel“ = der feste Teil des Prompts musste neu gerechnet werden (mit -np 1 hält der Server nur einen Prompt im Cache).
