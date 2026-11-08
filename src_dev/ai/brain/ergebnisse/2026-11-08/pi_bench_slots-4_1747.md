# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 17:47)

Modell `Qwen3.5-4B-Q4_K_M.gguf`, mmproj `mmproj-Qwen3.5-4B-Q8_0.gguf`, Lauf `slots-4`.

0 Bilder. Temperatur 51.8 → 66.1 °C, Drosselung throttled=0x0 → throttled=0x0, Server 6708 MB, frei 2909 MB.


**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 12.25 s | 4 | 9.7 | 12.28 s | 4 | 3.2 |
| chat | 8.85 s | 4 | 10.5 | 8.79 s | 4 | 3.3 |
| objekt | 11.24 s | 4 | 11.2 | 11.29 s | 4 | 3.4 |
| suchorte | 11.47 s | 4 | 11.1 | 11.43 s | 4 | 3.4 |

Hinweis: „nach Wechsel“ = vorher lief eine andere Aufgabe. Mit einem Slot muss der feste Teil neu gerechnet werden; mit --slots behält jede Aufgabe ihren Slot (hier 4 Slots).
