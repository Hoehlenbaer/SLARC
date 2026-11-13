# Vision-Sprachmodelle auf COCO (08.11.2026 16:40)

100 Bilder, Seed 7, alle, Bild max. 448 px. Bild-Ebene: Ist die Klasse im Bild? Recall „nicht klein“: nur Objekte ab 32×32 px.

| Modell | Precision | Recall | F1 | Recall nicht klein | ungültig | Zeit/Bild (PC) |
|---|---|---|---|---|---|---|
| 4B-f16 | 0.816 | 0.819 | 0.818 | 0.883 | 0 | 0.24 s |
| 4B-q8 | 0.811 | 0.827 | 0.819 | 0.883 | 0 | 0.22 s |

**4B-f16 übersieht am häufigsten:** handbag (4), stop sign (4), cup (4), person (4), truck (3), car (3), chair (2), bench (2)
**4B-f16 erfindet am häufigsten:** backpack (10), book (5), vase (4), bottle (3), car (3), dining table (3), bowl (2), tv (2)

**4B-q8 übersieht am häufigsten:** handbag (4), stop sign (4), person (4), chair (3), cup (3), truck (3), car (3), bench (2)
**4B-q8 erfindet am häufigsten:** backpack (10), book (6), bottle (4), vase (4), car (3), dining table (3), bowl (2), tv (2)
