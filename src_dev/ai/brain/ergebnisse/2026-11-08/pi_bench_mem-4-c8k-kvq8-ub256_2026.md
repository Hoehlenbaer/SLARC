# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 20:26)

Modell `Qwen3.5-4B-Q4_K_M.gguf`, mmproj `mmproj-Qwen3.5-4B-Q8_0.gguf`, Lauf `mem-4-c8k-kvq8-ub256`.

0 Bilder. Temperatur 52.4 → 63.9 °C, Drosselung throttled=0x0 → throttled=0x0, Server 6701 MB (davon Arbeitsspeicher 4169 MB, Modelldatei 2532 MB), frei 3214 MB.


**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 11.92 s | 4 | 10.1 | 11.89 s | 4 | 3.3 |
| chat | 8.57 s | 4 | 10.8 | 8.58 s | 4 | 3.4 |
| objekt | 10.74 s | 4 | 11.1 | 10.59 s | 4 | 3.4 |
| suchorte | 12.26 s | 4 | 11.3 | 12.14 s | 4 | 3.5 |

Hinweis: „nach Wechsel“ = vorher lief eine andere Aufgabe. Mit einem Slot muss der feste Teil neu gerechnet werden; mit --slots behält jede Aufgabe ihren Slot (hier 4 Slots).
