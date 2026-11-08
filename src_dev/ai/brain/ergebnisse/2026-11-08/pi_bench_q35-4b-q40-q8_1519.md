# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 15:19)

Modell `Qwen3.5-4B-Q4_0.gguf`, mmproj `mmproj-Qwen3.5-4B-Q8_0.gguf`, Lauf `q35-4b-q40-q8`.

3 Bilder. Temperatur 52.4 → 63.4 °C, Drosselung throttled=0x0 → throttled=0x0, Server 5759 MB, frei 4021 MB.

**Bildfragen** (Median je Bild)

| längste Kante | Bild+Frage Tokens | Prompt tok/s | Erzeugung tok/s | ja/nein (Dose) | Liste (40 Klassen) |
|---|---|---|---|---|---|
| 320 px | 124 | 18.3 | 3.5 | 9.48 s | 15.19 s |
| 448 px | 184 | 17.2 | 3.3 | 13.51 s | 19.14 s |

**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 53.48 s | 1132 | 28.3 | 14.01 s | 4 | 3.0 |
| chat | 32.1 s | 689 | 29.6 | 9.25 s | 4 | 3.2 |
| objekt | 21.11 s | 332 | 28.0 | 9.55 s | 4 | 3.3 |
| suchorte | 18.26 s | 219 | 28.2 | 10.88 s | 4 | 3.2 |

Hinweis: „nach Wechsel“ = der feste Teil des Prompts musste neu gerechnet werden (mit -np 1 hält der Server nur einen Prompt im Cache).
