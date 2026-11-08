# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 17:42)

Modell `Qwen3.5-4B-Q4_K_M.gguf`, mmproj `mmproj-Qwen3.5-4B-Q8_0.gguf`, Lauf `slots-1`.

0 Bilder. Temperatur 50.1 → 63.4 °C, Drosselung throttled=0x0 → throttled=0x0, Server 5808 MB, frei 3938 MB.


**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 71.66 s | 1132 | 19.1 | 12.64 s | 4 | 3.1 |
| chat | 43.69 s | 689 | 19.7 | 9.37 s | 4 | 3.1 |
| objekt | 28.95 s | 332 | 19.1 | 12.04 s | 4 | 3.2 |
| suchorte | 23.09 s | 219 | 19.4 | 12.23 s | 4 | 3.2 |

Hinweis: „nach Wechsel“ = vorher lief eine andere Aufgabe. Mit einem Slot muss der feste Teil neu gerechnet werden; mit --slots behält jede Aufgabe ihren Slot.
