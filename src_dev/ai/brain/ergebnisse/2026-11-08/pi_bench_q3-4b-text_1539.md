# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 15:39)

Modell `Qwen3-4B-Instruct-2507-Q4_K_M.gguf`, mmproj `None`, Lauf `q3-4b-text`.

0 Bilder. Temperatur 53.5 → 66.1 °C, Drosselung throttled=0x0 → throttled=0x0, Server 5461 MB, frei 4321 MB.


**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 82.94 s | 1237 | 19.0 | 18.12 s | 1 | 2.8 |
| chat | 46.39 s | 746 | 20.0 | 9.49 s | 1 | 3.5 |
| objekt | 25.32 s | 348 | 21.0 | 8.96 s | 1 | 3.9 |
| suchorte | 21.91 s | 236 | 21.3 | 11.09 s | 1 | 4.0 |

Hinweis: „nach Wechsel“ = der feste Teil des Prompts musste neu gerechnet werden (mit -np 1 hält der Server nur einen Prompt im Cache).
