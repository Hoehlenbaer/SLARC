# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 20:17)

Modell `Qwen3.5-4B-Q4_K_M.gguf`, mmproj `mmproj-Qwen3.5-4B-Q8_0.gguf`, Lauf `mem-2-c8k`.

0 Bilder. Temperatur 50.7 → 63.9 °C, Drosselung throttled=0x0 → throttled=0x0, Server 6677 MB (davon Arbeitsspeicher 4331 MB, Modelldatei 2345 MB), frei 3026 MB.


**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 12.07 s | 4 | 9.8 | 12.06 s | 4 | 3.3 |
| chat | 8.74 s | 4 | 10.4 | 8.65 s | 4 | 3.4 |
| objekt | 11.09 s | 4 | 11.1 | 10.76 s | 4 | 3.6 |
| suchorte | 10.87 s | 4 | 11.6 | 11.04 s | 4 | 3.6 |

Hinweis: „nach Wechsel“ = vorher lief eine andere Aufgabe. Mit einem Slot muss der feste Teil neu gerechnet werden; mit --slots behält jede Aufgabe ihren Slot (hier 4 Slots).
