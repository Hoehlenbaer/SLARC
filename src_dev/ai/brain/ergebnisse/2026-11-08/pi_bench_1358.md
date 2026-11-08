# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 13:58)

3 Bilder. Temperatur 47.4 → 65.5 °C, Drosselung throttled=0x0 → throttled=0x0, Server 6463 MB, frei 3532 MB.

**Bildfragen** (Median je Bild)

| längste Kante | Bild+Frage Tokens | Prompt tok/s | Erzeugung tok/s | ja/nein (Dose) | Liste (40 Klassen) |
|---|---|---|---|---|---|
| 320 px | 124 | 8.0 | 3.8 | 17.43 s | 24.01 s |
| 448 px | 184 | 6.7 | 2.9 | 28.19 s | 36.9 s |
| 640 px | 344 | 6.5 | 3.6 | 54.95 s | 61.94 s |

**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|
| zielwahl | 69.7 s | 1132 | 11.92 s | 4 | 3.3 |
| chat | 42.67 s | 689 | 8.52 s | 4 | 3.4 |
| objekt | 27.82 s | 332 | 11.04 s | 4 | 3.5 |
| suchorte | 22.04 s | 219 | 11.25 s | 4 | 3.5 |

Hinweis: „nach Wechsel“ = der feste Teil des Prompts musste neu gerechnet werden (mit -np 1 hält der Server nur einen Prompt im Cache).
