# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 15:32)

Modell `Qwen3.5-2B-Q4_K_M.gguf`, mmproj `mmproj-Qwen3.5-2B-Q8_0.gguf`, Lauf `q35-2b-q4km-q8`.

3 Bilder. Temperatur 53.5 → 65.0 °C, Drosselung throttled=0x0 → throttled=0x0, Server 3153 MB, frei 5444 MB.

**Bildfragen** (Median je Bild)

| längste Kante | Bild+Frage Tokens | Prompt tok/s | Erzeugung tok/s | ja/nein (Dose) | Liste (40 Klassen) |
|---|---|---|---|---|---|
| 320 px | 124 | 26.5 | 8.0 | 5.59 s | 8.74 s |
| 448 px | 184 | 23.5 | 8.0 | 8.76 s | 11.88 s |

**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 28.27 s | 1132 | 50.0 | 5.76 s | 4 | 7.3 |
| chat | 18.27 s | 689 | 51.4 | 5.06 s | 4 | 7.6 |
| objekt | 10.89 s | 332 | 50.5 | 4.58 s | 4 | 7.5 |
| suchorte | 9.42 s | 219 | 50.7 | 5.33 s | 4 | 7.6 |

Hinweis: „nach Wechsel“ = der feste Teil des Prompts musste neu gerechnet werden (mit -np 1 hält der Server nur einen Prompt im Cache).
