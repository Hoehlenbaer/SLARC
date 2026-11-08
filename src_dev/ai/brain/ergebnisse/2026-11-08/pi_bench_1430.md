# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 14:30)

3 Bilder. Temperatur 46.9 → 63.4 °C, Drosselung throttled=0x0 → throttled=0x0, Server 4631 MB, frei 3437 MB.

**Bildfragen** (Median je Bild)

| längste Kante | Bild+Frage Tokens | Prompt tok/s | Erzeugung tok/s | ja/nein (Dose) | Liste (40 Klassen) |
|---|---|---|---|---|---|
| 320 px | 124 | 8.0 | 3.6 | 17.43 s | 24.1 s |
| 448 px | 184 | 7.3 | 3.6 | 27.44 s | 34.99 s |
| 640 px | 344 | 6.5 | 3.6 | 55.06 s | 61.69 s |

**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|
| zielwahl | 70.01 s | 1132 | 12.14 s | 4 | 3.3 |
| chat | 50.41 s | 689 | 8.68 s | 4 | 3.4 |
| objekt | 27.83 s | 332 | 11.16 s | 4 | 3.4 |
| suchorte | 33.24 s | 219 | 14.26 s | 4 | 2.8 |

Hinweis: „nach Wechsel“ = der feste Teil des Prompts musste neu gerechnet werden (mit -np 1 hält der Server nur einen Prompt im Cache).
