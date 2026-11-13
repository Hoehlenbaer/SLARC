# Vision-Sprachmodelle auf COCO (07.11.2026 23:53)

100 Bilder, Seed 7, nur Innenraum, Bild max. 640 px. Bild-Ebene: Ist die Klasse im Bild? Recall „nicht klein“: nur Objekte ab 32×32 px.

| Modell | Precision | Recall | F1 | Recall nicht klein | ungültig | Zeit/Bild (PC) |
|---|---|---|---|---|---|---|
| 4B | 0.851 | 0.848 | 0.85 | 0.896 | 0 | 0.32 s |

**4B übersieht am häufigsten:** handbag (5), chair (5), bowl (5), backpack (3), potted plant (3), person (3), dining table (3), cup (3)
**4B erfindet am häufigsten:** potted plant (6), cup (5), chair (5), bottle (5), dining table (4), bench (3), backpack (3), cell phone (2)

**Beschreibungen zum Lesen**

- 000000105455.jpg (COCO: car, clock)
  - 4B: Ein kleiner Roboter in einem Raum beschreibt: Ein farbenfroher, historischer Uhrenturm mit goldenem Oberteil und blauen Wänden steht auf einer Straße vor einem Gebäudekomplex.
- 000000365208.jpg (COCO: chair, handbag, person, umbrella)
  - 4B: Ein kleiner Roboter beschreibt ein Schwarz-Weiß-Bild mit einer Person unter einem weißen Vorhang, einem Vogelkäfig und einem parasol auf Sand.
- 000000218362.jpg (COCO: clock)
  - 4B: Ich sehe eine Wand voller verschiedener Uhren, darunter eine mit LED-Zahlen und eine große goldene Spiegelrahmen.
- 000000129322.jpg (COCO: toilet)
  - 4B: Ich sehe ein altes Badezimmer mit einem Holztoilettsitz, einer alten Wandröhre und einer Badewanne mit Toilettenpapier.
- 000000232563.jpg (COCO: handbag, person, umbrella)
  - 4B: Ein kleiner Roboter im Raum sieht einen Mann mit Zebra-Regenschirm und einer Person mit rosa Regenschirm auf nasser Straße.
- 000000340697.jpg (COCO: bottle)
  - 4B: Ich sehe eine Regal mit vielen bunten Glasflaschen und Dosen, die wie kleine, leuchtende Kugeln aussehen.
- 000000502737.jpg (COCO: cup, person)
  - 4B: Ein kleiner Roboter zeigt ein Schokoriegel mit weißer Zuckerguss-Figur und ein Glas dunkles Getränk.
- 000000060449.jpg (COCO: chair, couch, dining table, laptop)
  - 4B: Ich sehe einen Laptop auf einem Tisch mit Blick zum Meer und Palmen.
- 000000296634.jpg (COCO: bowl)
  - 4B: Ich sehe drei weiße Teller mit Essen auf einem Holzboden: ein Salat, eine Gemüse-Salat-Mischung mit Dip und eine Suppe mit kleinen Brötchen.
- 000000548780.jpg (COCO: backpack, bench, bird, handbag, person, potted plant)
  - 4B: Zwei Frauen sitzen auf einer Parkbank, eine hält einen Rucksack, und zwei Tauben stehen auf dem Boden.
