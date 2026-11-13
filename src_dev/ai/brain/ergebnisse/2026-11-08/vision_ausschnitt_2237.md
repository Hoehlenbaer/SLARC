# Was ist das? Ausschnitte ans VLM (08.11.2026 22:37)

397 Ausschnitte: je Klasse bis zu 5 COCO-Boxen mit kürzerer Kante ≥ 64 px, Rand 25% je Seite, quadratisch. „Unbekannt“ = die 40 COCO-Klassen, die SLARC nicht erkennt; „Haushalt“ = davon ohne Tiere/Fahrzeuge/Wintersport. Seed 7.

| Lauf | Treffer unbekannt | Haushalt | bekannt (Kontrolle) | sicher | Treffer wenn sicher | wenn unsicher | ungültig | Zeit (PC) | Prompt-Tokens |
|---|---|---|---|---|---|---|---|---|---|
| 4B|liste-voll|224 | 0.822 | 0.764 | 0.56 | 0.99 | 0.831 | 0.0 | 0 | 0.31 s | 488 |
| 4B|liste-voll|rahmen|224 | 0.838 | 0.764 | 0.68 | 0.995 | 0.842 | 0.0 | 0 | 0.34 s | 509 |
| 4B|liste-haushalt|224 | 0.503 | 0.78 | 0.54 | 0.975 | 0.516 | 0.0 | 0 | 0.31 s | 447 |
| 4B|liste-haushalt|rahmen|224 | 0.523 | 0.78 | 0.705 | 0.929 | 0.563 | 0.0 | 0 | 0.34 s | 468 |

**Je Klasse (4B|liste-voll|rahmen|224)**

| Klasse | Treffer | Antworten |
|---|---|---|
| airplane | 5/5 | flugzeug, flugzeug, flugzeug, flugzeug, flugzeug |
| apple | 3/5 | obst, orange, orange, apfel, obst |
| banana | 4/5 | banane, banane, banane, banane, apfel |
| baseball bat | 1/5 | drachen, föhn, fahrrad, fahrrad, schläger |
| baseball glove | 2/5 | socke, socke, ball, handschuh, handschuh |
| bear | 5/5 | bär, bär, bär, bär, bär |
| boat | 5/5 | boot, boot, boot, boot, boot |
| broccoli | 5/5 | brokkoli, brokkoli, brokkoli, brokkoli, brokkoli |
| cake | 3/5 | kuchen, donut, kuchen, kuchen, pizza |
| carrot | 3/5 | brokkoli, brokkoli, karotte, karotte, karotte |
| cow | 5/5 | kuh, kuh, kuh, kuh, kuh |
| donut | 4/5 | donut, donut, donut, hotdog, donut |
| elephant | 5/5 | elefant, elefant, elefant, elefant, elefant |
| fork | 5/5 | gabel, gabel, gabel, gabel, gabel |
| frisbee | 4/5 | glas, frisbee, frisbee, frisbee, frisbee |
| giraffe | 5/5 | giraffe, giraffe, giraffe, giraffe, giraffe |
| hair drier | 4/4 | föhn, föhn, föhn, föhn |
| horse | 5/5 | pferd, pferd, pferd, pferd, pferd |
| hot dog | 5/5 | hotdog, hotdog, hotdog, hotdog, hotdog |
| kite | 4/5 | drachen, drachen, frisbee, drachen, drachen |
| knife | 3/5 | messer, teller, messer, messer, löffel |
| mouse | 4/5 | computermaus, laptop, computermaus, computermaus, computermaus |
| orange | 3/5 | orange, obst, orange, glas, karotte |
| pizza | 4/5 | pizza, kuchen, pizza, pizza, pizza |
| sandwich | 5/5 | sandwich, sandwich, sandwich, sandwich, sandwich |
| scissors | 4/5 | schere, schere, schere, brille, schere |
| sheep | 5/5 | schaf, schaf, schaf, schaf, schaf |
| skateboard | 5/5 | skateboard, skateboard, skateboard, skateboard, skateboard |
| skis | 4/5 | ski, ski, ski, ski, schuh |
| snowboard | 5/5 | snowboard, snowboard, snowboard, snowboard, snowboard |
| spoon | 4/5 | löffel, löffel, löffel, messer, löffel |
| sports ball | 4/5 | ball, ball, tüte, ball, ball |
| surfboard | 5/5 | surfbrett, surfbrett, surfbrett, surfbrett, surfbrett |
| tennis racket | 2/5 | schläger, fernglas, spielzeug, schläger, fernglas? |
| tie | 5/5 | krawatte, krawatte, krawatte, krawatte, krawatte |
| toaster | 2/3 | stuhl, toaster, toaster |
| toothbrush | 5/5 | zahnbürste, zahnbürste, zahnbürste, zahnbürste, zahnbürste |
| train | 5/5 | zug, zug, zug, zug, zug |
| wine glass | 4/5 | tasse, weinglas, glas, glas, glas |
| zebra | 5/5 | zebra, zebra, zebra, zebra, zebra |
| backpack (bekannt) | 1/5 | person, krawatte, person, rucksack, person |
| bed (bekannt) | 3/5 | katze, bett, bett, bett, handy |
| bench (bekannt) | 2/5 | person, bank, tüte, katze, bank |
| bicycle (bekannt) | 4/5 | fahrrad, fahrrad, fahrrad, fahrrad, flasche |
| bird (bekannt) | 3/5 | vogel, vogel, drachen, vogel, pflanze |
| book (bekannt) | 4/5 | buch, fernglas, buch, buch, buch |
| bottle (bekannt) | 5/5 | flasche, flasche, flasche, flasche, flasche |
| bowl (bekannt) | 0/5 | tasse, brokkoli, glas, löffel, tasse |
| bus (bekannt) | 3/5 | bus, bus, kissen, bus, kissen |
| car (bekannt) | 3/5 | auto, auto, person, hydrant, auto |
| cat (bekannt) | 5/5 | katze, katze, katze, katze, katze |
| cell phone (bekannt) | 3/5 | handy, handy, fernbedienung, fernbedienung, handy |
| chair (bekannt) | 2/5 | karton, teddy, stuhl, socke, stuhl |
| clock (bekannt) | 4/5 | uhr, uhr, uhr, uhr, teller |
| couch (bekannt) | 4/5 | sofa, sofa, sofa, kissen, sofa |
| cup (bekannt) | 1/5 | glas, tasse, flasche, glas, glas |
| dining table (bekannt) | 0/5 | tasse, tasse, glas, teller, teller |
| dog (bekannt) | 3/5 | hund, katze, hund, katze, hund |
| fire hydrant (bekannt) | 4/5 | hydrant, hydrant, ampel, hydrant, hydrant |
| handbag (bekannt) | 1/5 | tasse, kissen, person, rucksack, handtasche |
| keyboard (bekannt) | 4/5 | tastatur, tastatur, tastatur, tasse, tastatur |
| laptop (bekannt) | 5/5 | laptop, laptop, laptop, laptop, laptop |
| microwave (bekannt) | 5/5 | mikrowelle, mikrowelle, mikrowelle, mikrowelle, mikrowelle |
| motorcycle (bekannt) | 4/5 | motorrad, motorrad, motorrad, drachen, motorrad |
| oven (bekannt) | 3/5 | topfpflanze, ofen, kühlschrank, ofen, ofen |
| parking meter (bekannt) | 4/5 | parkuhr, parkuhr, parkuhr, parkuhr, computermaus |
| person (bekannt) | 4/5 | person, handschuh, person, person, person |
| potted plant (bekannt) | 4/5 | pflanze, pflanze, pflanze, pflanze, flasche |
| refrigerator (bekannt) | 4/5 | tasse, kühlschrank, kühlschrank, kühlschrank, kühlschrank |
| remote (bekannt) | 4/5 | tasse, fernbedienung, fernbedienung, fernbedienung, fernbedienung |
| sink (bekannt) | 3/5 | waschbecken, katze, waschbecken, glas, waschbecken |
| stop sign (bekannt) | 5/5 | stoppschild, stoppschild, stoppschild, stoppschild, stoppschild |
| suitcase (bekannt) | 5/5 | koffer, koffer, koffer, koffer, koffer |
| teddy bear (bekannt) | 5/5 | teddy, teddy, teddy, teddy, teddy |
| toilet (bekannt) | 5/5 | toilette, toilette, toilette, toilette, toilette |
| traffic light (bekannt) | 5/5 | ampel, ampel, ampel, ampel, ampel |
| truck (bekannt) | 1/5 | lkw, auto, auto, motorrad, auto |
| tv (bekannt) | 4/5 | fernseher, pflanze, fernseher, fernseher, fernseher |
| umbrella (bekannt) | 4/5 | regenschirm, regenschirm, regenschirm, regenschirm, decke |
| vase (bekannt) | 3/5 | vase, vase, glas, vase, flasche |

**Häufigste Verwechslungen:** backpack → person (3), cup → glas (3), truck → auto (3), apple → orange (2), baseball bat → fahrrad (2), baseball glove → socke (2), bowl → tasse (2), bus → kissen (2), carrot → brokkoli (2), cell phone → fernbedienung (2), dining table → tasse (2), dining table → teller (2)

„?“ = Modell war unsicher.
