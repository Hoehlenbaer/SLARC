# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 20:21)

Modell `Qwen3.5-4B-Q4_K_M.gguf`, mmproj `mmproj-Qwen3.5-4B-Q8_0.gguf`, Lauf `mem-3-c8k-kvq8`.

0 Bilder. Temperatur 50.7 → 64.5 °C, Drosselung throttled=0x0 → throttled=0x0, Server 6738 MB (davon Arbeitsspeicher 4211 MB, Modelldatei 2527 MB), frei 3167 MB.


**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 11.73 s | 4 | 10.4 | 11.72 s | 4 | 3.4 |
| chat | 8.41 s | 4 | 10.8 | 8.76 s | 4 | 3.3 |
| objekt | 8.99 s | 4 | 10.7 | 8.94 s | 4 | 3.5 |
| suchorte | 12.32 s | 4 | 11.3 | 12.5 s | 4 | 3.4 |

Hinweis: „nach Wechsel“ = vorher lief eine andere Aufgabe. Mit einem Slot muss der feste Teil neu gerechnet werden; mit --slots behält jede Aufgabe ihren Slot (hier 4 Slots).
