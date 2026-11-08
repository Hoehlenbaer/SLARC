# VLM/LLM-Geschwindigkeit auf slarc (aarch64, 08.11.2026 20:47)

Modell `Qwen3.5-4B-Q4_K_M.gguf`, mmproj `mmproj-Qwen3.5-4B-Q8_0.gguf`, Lauf `inhalt-q35-4b`.

0 Bilder. Temperatur 50.1 → 63.9 °C, Drosselung throttled=0x0 → throttled=0x0, Server 6526 MB (davon Arbeitsspeicher 4174 MB, Modelldatei 2352 MB), frei 3197 MB.


**Brain-Aufgaben ohne Bild**

| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | anderer Inhalt 1 / 2 | Tokens neu | Erzeugung tok/s |
|---|---|---|---|---|---|---|---|---|
| zielwahl | 11.69 s | 4 | 10.0 | 11.62 s | 4 | 19.41 s / 19.08 s | 132 / 144 | 3.4 |
| chat | 8.43 s | 4 | 10.7 | 8.4 s | 4 | 9.74 s / 8.85 s | 22 / 21 | 3.5 |
| objekt | 10.05 s | 4 | 10.9 | 10.03 s | 4 | 14.96 s / 14.06 s | 25 / 25 | 3.6 |
| suchorte | 12.02 s | 4 | 11.6 | 12.07 s | 4 | 14.98 s / 11.51 s | 33 / 34 | 3.5 |

„anderer Inhalt“: gleiche Aufgabe, gleicher fester Teil, anderer Zustand/Satz – so wie im Betrieb.

Hinweis: „nach Wechsel“ = vorher lief eine andere Aufgabe. Mit einem Slot muss der feste Teil neu gerechnet werden; mit --slots behält jede Aufgabe ihren Slot (hier 4 Slots).
