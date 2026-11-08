# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 20:12)

Modell `Qwen3.5-4B-Q4_K_M.gguf`, mmproj `mmproj-Qwen3.5-4B-Q8_0.gguf`, Lauf `mem-1-c12k`.

0 Bilder. Temperatur 51.8 → 64.5 °C, Drosselung throttled=0x0 → throttled=0x0, Server 6705 MB (davon Arbeitsspeicher 4450 MB, Modelldatei 2255 MB), frei 2898 MB.


**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 12.39 s | 4 | 9.6 | 12.15 s | 4 | 3.2 |
| chat | 8.71 s | 4 | 10.5 | 8.49 s | 4 | 3.5 |
| objekt | 10.89 s | 4 | 10.5 | 10.84 s | 4 | 3.5 |
| suchorte | 12.19 s | 4 | 11.7 | 11.17 s | 4 | 3.5 |

Hinweis: „nach Wechsel“ = vorher lief eine andere Aufgabe. Mit einem Slot muss der feste Teil neu gerechnet werden; mit --slots behält jede Aufgabe ihren Slot (hier 4 Slots).
