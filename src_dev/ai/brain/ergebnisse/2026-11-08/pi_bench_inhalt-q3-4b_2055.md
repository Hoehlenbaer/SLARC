# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 20:55)

Modell `Qwen3-4B-Instruct-2507-Q4_K_M.gguf`, mmproj `None`, Lauf `inhalt-q3-4b`.

0 Bilder. Temperatur 51.2 → 63.4 °C, Drosselung throttled=0x0 → throttled=0x0, Server 5470 MB (davon Arbeitsspeicher 3094 MB, Modelldatei 2376 MB), frei 4306 MB.


**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | anderer Inhalt 1 / 2 | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|---|---|
| zielwahl | 14.85 s | 1 | 3.4 | 14.86 s | 1 | 22.77 s / 23.26 s | 134 / 153 | 3.4 |
| chat | 9.88 s | 1 | 3.8 | 9.67 s | 1 | 10.38 s / 9.79 s | 16 / 14 | 3.9 |
| objekt | 8.43 s | 1 | 4.2 | 8.43 s | 1 | 11.34 s / 11.23 s | 12 / 12 | 4.3 |
| suchorte | 10.36 s | 1 | 4.2 | 10.38 s | 1 | 13.04 s / 9.99 s | 21 / 24 | 4.2 |

„anderer Inhalt“: gleiche Aufgabe, gleicher fester Teil, anderer Zustand/Satz – so wie im Betrieb.

Hinweis: „nach Wechsel“ = vorher lief eine andere Aufgabe. Mit einem Slot muss der feste Teil neu gerechnet werden; mit --slots behält jede Aufgabe ihren Slot (hier 4 Slots).
