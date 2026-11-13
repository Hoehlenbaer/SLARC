# Was ist das? Ausschnitte ans VLM (08.11.2026 22:13)

400 Ausschnitte: je Klasse bis zu 5 COCO-Boxen mit kürzerer Kante ≥ 32 px, Rand 25% je Seite, quadratisch. „Unbekannt“ = die 40 COCO-Klassen, die SLARC nicht erkennt; „Haushalt“ = davon ohne Tiere/Fahrzeuge/Wintersport. Seed 7.

| Lauf | Treffer unbekannt | Haushalt | bekannt (Kontrolle) | sicher | Treffer wenn sicher | wenn unsicher | ungültig | Zeit (PC) | Prompt-Tokens |
|---|---|---|---|---|---|---|---|---|---|
| 4B|liste|160 | 0.795 | 0.777 | 0.495 | 1.0 | 0.795 | None | 0 | 0.3 s | 471 |
| 4B|liste|224 | 0.795 | 0.762 | 0.505 | 0.995 | 0.799 | 0.0 | 0 | 0.3 s | 495 |
| 4B|liste|320 | 0.83 | 0.785 | 0.535 | 0.985 | 0.843 | 0.0 | 0 | 0.33 s | 516 |
| 4B|frei|160 | 0.63 | 0.631 | 0.39 | 1.0 | 0.63 | None | 0 | 0.21 s | 110 |
| 4B|frei|224 | 0.665 | 0.7 | 0.42 | 1.0 | 0.665 | None | 0 | 0.21 s | 134 |
| 4B|frei|320 | 0.67 | 0.654 | 0.42 | 0.98 | 0.684 | 0.0 | 0 | 0.23 s | 185 |

**Je Klasse (4B|liste|320)**

| Klasse | Treffer | Antworten |
|---|---|---|
| airplane | 4/5 | flugzeug, flugzeug, flugzeug, flugzeug, koffer |
| apple | 5/5 | apfel, apfel, obst, apfel, apfel |
| banana | 5/5 | banane, banane, banane, banane, banane |
| baseball bat | 3/5 | schläger, spielzeug, schläger, schläger, person |
| baseball glove | 5/5 | handschuh, handschuh, handschuh, handschuh, handschuh |
| bear | 5/5 | bär, bär, bär, bär, bär |
| boat | 4/5 | boot, hund, boot, boot, boot |
| broccoli | 5/5 | brokkoli, brokkoli, brokkoli, brokkoli, brokkoli |
| cake | 4/5 | kuchen, kuchen, kuchen, donut, kuchen |
| carrot | 3/5 | apfel, karotte, karotte, brokkoli, karotte |
| cow | 5/5 | kuh, kuh, kuh, kuh, kuh |
| donut | 5/5 | donut, donut, donut, donut, donut |
| elephant | 5/5 | elefant, elefant, elefant, elefant, elefant |
| fork | 4/5 | pizza, gabel, gabel, gabel, gabel |
| frisbee | 5/5 | frisbee, frisbee, frisbee, frisbee, frisbee |
| giraffe | 5/5 | giraffe, giraffe, giraffe, giraffe, giraffe |
| hair drier | 5/5 | föhn, föhn, föhn, föhn, föhn |
| horse | 5/5 | pferd, pferd, pferd, pferd, pferd |
| hot dog | 3/5 | hotdog, hotdog, sandwich, pizza, hotdog |
| kite | 4/5 | drachen, drachen, drachen, frisbee, drachen |
| knife | 1/5 | teller, obst, sandwich, stift, messer |
| mouse | 5/5 | computermaus, computermaus, computermaus, computermaus, computermaus |
| orange | 4/5 | orange, orange, obst, glas, orange |
| pizza | 5/5 | pizza, pizza, pizza, pizza, pizza |
| sandwich | 2/5 | donut, pizza, brot, pizza, sandwich |
| scissors | 5/5 | schere, schere, schere, schere, schere |
| sheep | 5/5 | schaf, schaf, schaf, schaf, schaf |
| skateboard | 4/5 | skateboard, skateboard, skateboard, skateboard, schuh |
| skis | 5/5 | ski, ski, ski, ski, ski |
| snowboard | 4/5 | person, snowboard, snowboard, snowboard, snowboard |
| spoon | 3/5 | löffel, teller, gabel, löffel, löffel |
| sports ball | 4/5 | ball, ball, ball, teddy?, ball |
| surfboard | 3/5 | surfbrett, person, surfbrett, person, surfbrett |
| tennis racket | 1/5 | frisbee, spielzeug?, teddy, spielzeug?, schläger |
| tie | 4/5 | kleidung, krawatte, krawatte, krawatte, krawatte |
| toaster | 5/5 | toaster, toaster, toaster, toaster, toaster |
| toothbrush | 4/5 | zahnbürste, zahnbürste, zahnbürste, zahnbürste, flasche |
| train | 5/5 | zug, zug, zug, zug, zug |
| wine glass | 3/5 | glas, teller, pizza, glas, glas |
| zebra | 5/5 | zebra, zebra, zebra, zebra, zebra |
| backpack (bekannt) | 1/5 | koffer, rucksack, person, person, flasche |
| bed (bekannt) | 1/5 | bett, kleidung, person, kleidung, teddy |
| bench (bekannt) | 2/5 | koffer, person, bank, person, bank |
| bicycle (bekannt) | 4/5 | obst, fahrrad, fahrrad, fahrrad, fahrrad |
| bird (bekannt) | 4/5 | vogel, vogel, vogel, kuh, vogel |
| book (bekannt) | 3/5 | karton, buch, socke, buch, buch |
| bottle (bekannt) | 2/5 | glas, flasche, flasche, tasse, tasse |
| bowl (bekannt) | 0/5 | teller, teller, sandwich, pizza, teller |
| bus (bekannt) | 2/5 | bus, person, auto, person, bus |
| car (bekannt) | 1/5 | stuhl, glas, katze, person, auto |
| cat (bekannt) | 4/5 | katze, glas, katze, katze, katze |
| cell phone (bekannt) | 4/5 | handy, handy, fernglas, handy, handy |
| chair (bekannt) | 1/5 | schuh, katze, stuhl, person, kleidung |
| clock (bekannt) | 5/5 | uhr, uhr, uhr, uhr, uhr |
| couch (bekannt) | 1/5 | kissen, teller, teddy, sofa, brille |
| cup (bekannt) | 2/5 | glas, glas, glas, tasse, tasse |
| dining table (bekannt) | 0/5 | pizza, tasse, stuhl, pizza, kuchen |
| dog (bekannt) | 4/5 | hund, hund, frisbee, hund, hund |
| fire hydrant (bekannt) | 4/5 | hydrant, hydrant, hydrant, hund, hydrant |
| handbag (bekannt) | 1/5 | handtasche, brille, rucksack, rucksack, tüte |
| keyboard (bekannt) | 2/5 | laptop, laptop, tastatur, katze, tastatur |
| laptop (bekannt) | 4/5 | laptop, laptop, katze, laptop, laptop |
| microwave (bekannt) | 3/5 | flasche, mikrowelle, tasse, mikrowelle, mikrowelle |
| motorcycle (bekannt) | 3/5 | person, motorrad, fahrrad, motorrad, motorrad |
| oven (bekannt) | 0/5 | kühlschrank, mikrowelle, toaster, kühlschrank, kühlschrank |
| parking meter (bekannt) | 3/5 | parkuhr, parkuhr, lampe, glas, parkuhr |
| person (bekannt) | 2/5 | person, laptop, person, hotdog, kleidung |
| potted plant (bekannt) | 2/5 | person, topfpflanze, vase, katze, pflanze |
| refrigerator (bekannt) | 3/5 | person, toaster, kühlschrank, kühlschrank, kühlschrank |
| remote (bekannt) | 5/5 | fernbedienung, fernbedienung, fernbedienung, fernbedienung, fernbedienung |
| sink (bekannt) | 3/5 | tasse, waschbecken, waschbecken, tasse, waschbecken |
| stop sign (bekannt) | 5/5 | stoppschild, stoppschild, stoppschild, stoppschild, stoppschild |
| suitcase (bekannt) | 5/5 | koffer, koffer, koffer, koffer, koffer |
| teddy bear (bekannt) | 3/5 | teddy, bär, person, teddy, teddy |
| toilet (bekannt) | 5/5 | toilette, toilette, toilette, toilette, toilette |
| traffic light (bekannt) | 4/5 | ampel, ampel, ampel, ampel, drachen |
| truck (bekannt) | 0/5 | hund, auto, ampel, auto, flasche |
| tv (bekannt) | 1/5 | computermaus, computermaus, tasse, schüssel, fernseher |
| umbrella (bekannt) | 3/5 | decke, regenschirm, decke, regenschirm, regenschirm |
| vase (bekannt) | 5/5 | vase, vase, vase, vase, vase |

**Häufigste Verwechslungen:** bowl → teller (3), cup → glas (3), oven → kühlschrank (3), backpack → person (2), bed → kleidung (2), bench → person (2), bottle → tasse (2), bus → person (2), dining table → pizza (2), handbag → rucksack (2), keyboard → laptop (2), sandwich → pizza (2)

„?“ = Modell war unsicher.
