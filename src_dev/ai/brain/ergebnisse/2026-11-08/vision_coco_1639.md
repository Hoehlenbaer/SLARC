# Vision-Sprachmodelle auf COCO (08.11.2026 16:39)

100 Bilder, Seed 7, alle, Bild max. 320 px. Bild-Ebene: Ist die Klasse im Bild? Recall „nicht klein“: nur Objekte ab 32×32 px.

| Modell | Precision | Recall | F1 | Recall nicht klein | ungültig | Zeit/Bild (PC) |
|---|---|---|---|---|---|---|
| 4B-f16 | 0.792 | 0.779 | 0.785 | 0.85 | 0 | 0.2 s |
| 4B-q8 | 0.796 | 0.767 | 0.781 | 0.84 | 0 | 0.23 s |

**4B-f16 übersieht am häufigsten:** handbag (5), laptop (4), bench (4), car (4), stop sign (4), suitcase (3), chair (3), cup (3)
**4B-f16 erfindet am häufigsten:** backpack (7), book (7), vase (4), bottle (4), chair (3), dining table (3), potted plant (3), teddy bear (2)

**4B-q8 übersieht am häufigsten:** handbag (5), chair (4), laptop (4), bench (4), car (4), stop sign (4), person (4), suitcase (3)
**4B-q8 erfindet am häufigsten:** book (7), backpack (6), bottle (4), vase (3), chair (3), dining table (3), potted plant (3), teddy bear (2)
