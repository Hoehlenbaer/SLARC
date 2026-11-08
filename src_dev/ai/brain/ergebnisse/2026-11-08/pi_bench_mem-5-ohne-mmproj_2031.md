# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 20:31)

Modell `Qwen3.5-4B-Q4_K_M.gguf`, mmproj `None`, Lauf `mem-5-ohne-mmproj`.

0 Bilder. Temperatur 51.8 → 63.4 °C, Drosselung throttled=0x0 → throttled=0x0, Server 6400 MB (davon Arbeitsspeicher 3813 MB, Modelldatei 2586 MB), frei 3558 MB.


**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|
| zielwahl | 11.83 s | 4 | 9.4 | 11.71 s | 4 | 3.4 |
| chat | 8.53 s | 4 | 10.7 | 8.52 s | 4 | 3.4 |
| objekt | 10.49 s | 4 | 11.3 | 10.57 s | 4 | 3.4 |
| suchorte | 11.88 s | 4 | 11.4 | 12.09 s | 4 | 3.5 |

Hinweis: „nach Wechsel“ = vorher lief eine andere Aufgabe. Mit einem Slot muss der feste Teil neu gerechnet werden; mit --slots behält jede Aufgabe ihren Slot (hier 4 Slots).
