# Vision-Sprachmodelle auf COCO (08.11.2026 14:52)

100 Bilder, Seed 7, alle, Bild max. 320 px. Bild-Ebene: Ist die Klasse im Bild? Recall „nicht klein“: nur Objekte ab 32×32 px.

| Modell | Precision | Recall | F1 | Recall nicht klein | ungültig | Zeit/Bild (PC) |
|---|---|---|---|---|---|---|
| 4B-f16 | 0.843 | 0.859 | 0.851 | 0.908 | 0 | 0.26 s |
| 4B-q8 | 0.84 | 0.863 | 0.851 | 0.908 | 0 | 0.27 s |
| 2B-f16 | 0.363 | 0.823 | 0.504 | 0.869 | 5 | 0.19 s |
| 2B-q8 | 0.371 | 0.835 | 0.514 | 0.879 | 3 | 0.18 s |

**4B-f16 übersieht am häufigsten:** handbag (4), stop sign (3), truck (3), person (3), chair (2), bird (2), bench (2), suitcase (2)
**4B-f16 erfindet am häufigsten:** book (6), backpack (6), bottle (4), teddy bear (3), clock (3), chair (2), tv (2), car (2)

**4B-q8 übersieht am häufigsten:** chair (3), handbag (3), stop sign (3), truck (3), person (3), bird (2), suitcase (2), cup (2)
**4B-q8 erfindet am häufigsten:** book (6), backpack (6), bottle (4), chair (3), teddy bear (3), clock (3), tv (2), car (2)

**2B-f16 übersieht am häufigsten:** person (5), dining table (4), cup (3), bowl (3), stop sign (3), handbag (3), chair (2), clock (2)
**2B-f16 erfindet am häufigsten:** bottle (18), cup (15), backpack (13), bowl (13), book (13), truck (11), tv (11), bench (10)

**2B-q8 übersieht am häufigsten:** person (4), dining table (3), laptop (3), couch (3), stop sign (3), handbag (3), book (2), chair (2)
**2B-q8 erfindet am häufigsten:** bottle (19), backpack (14), cup (14), bowl (13), truck (12), book (12), handbag (11), bench (11)
