# Vision-Sprachmodelle auf COCO (08.11.2026 17:09)

100 Bilder, Seed 7, alle, Bild max. 320 px. Bild-Ebene: Ist die Klasse im Bild? Recall „nicht klein“: nur Objekte ab 32×32 px.

| Modell | Precision | Recall | F1 | Recall nicht klein | ungültig | Zeit/Bild (PC) |
|---|---|---|---|---|---|---|
| q4km | 0.796 | 0.767 | 0.781 | 0.84 | 0 | 0.2 s |
| q40 | 0.785 | 0.763 | 0.774 | 0.83 | 0 | 0.19 s |

**q4km übersieht am häufigsten:** handbag (5), chair (4), laptop (4), bench (4), car (4), stop sign (4), person (4), suitcase (3)
**q4km erfindet am häufigsten:** book (7), backpack (6), bottle (4), vase (3), dining table (3), chair (3), potted plant (3), clock (2)

**q40 übersieht am häufigsten:** person (5), handbag (5), car (5), dining table (4), laptop (4), stop sign (4), truck (4), suitcase (3)
**q40 erfindet am häufigsten:** backpack (9), book (6), handbag (5), bottle (3), car (3), bench (3), teddy bear (2), clock (2)
