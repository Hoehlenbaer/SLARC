# SLARC – URDF aus dem CAD-Modell

`slarc_cad.urdf` wurde aus `Drawings/Macros/SLARC.FCStd` erzeugt (Stand 23.10.2026). Grundlage sind Bein V9 mit Femur 150 mm, Tibia 175 mm, Knick 38,6° und Fußsegment 140 mm, Baseplates V2.5, Kamerahalter V1.4 und Panzer V1.1.

Die Datei ist ein Drop-in für `slarc_primitives.urdf` aus `slarc_sim_V10.py`. Link- und Gelenknamen sind identisch (`front_right_coxa_joint`, …, `rear_left_foot`), die Vorzeichen auch: Coxa um +z, Femur und Tibia um +y, + = nach unten. Die linken Beine sind gespiegelte Geometrie, die Gelenkvorzeichen bleiben gleich. Die Drehrichtung der gespiegelten Servos dreht erst die Firmware um.

## Laden

```python
robot = p.loadURDF("slarc_urdf/slarc_cad.urdf", [0, 0, 0.25],
                   flags=p.URDF_USE_INERTIA_FROM_FILE)
```

Der Ordner `meshes/` muss neben der URDF liegen. Die Meshes sind in mm und werden in der URDF mit 0,001 skaliert.

## Was sich gegenüber der Primitiv-URDF ändert

| | Primitiv-URDF (Sim V10) | CAD-URDF |
|---|---|---|
| Gesamtmasse | 2,58 kg | **3,79 kg** |
| Rumpf | 1,29 kg, Box 400×150×40 symmetrisch um den Ursprung | **2,26 kg**; Ursprung = Oberkante Coxa-Servos (wie CAD), Unterseite bei z = −39 mm, Panzer bis z ≈ +96 mm |
| Coxa-Link | 80 g | 77 g |
| Femur-Link | 95 g, 175 mm | **102 g, 150 mm** |
| Tibia-Link | 25 g, gerade 150 mm | **58 g, geknickt** (siehe unten) |
| Fuß | Kugel r 15, 15 g | Kugel **r 16**, 17 g |
| Femur-Gelenk | auf Höhe des Coxa-Gelenks | **17,0 mm tiefer** (x 60, z −17.025 im Coxa-Frame) |
| Gelenkgrenzen | ±180° | Coxa ±95° (Freischnitt Baseplate), Femur ±112°, Tibia ±112° (Bein V9.1 mit Fase: Berührung im CAD ab 117°) |
| Servo | effort 3.0, velocity 3.14 | effort 2.94 Nm, velocity 4.71 rad/s (45 U/min) |

Die Massen stammen aus den CAD-Volumen: PETG 1,27 g/cm³ × 0,8 (Beine), × 0,85 (Platten), × 0,9 (Panzer), PLA massiv, TPU × 0,8. Dazu kommen Servos mit je 55 g, Akku 600 g, Elektronik 420 g sowie Kabel und Schrauben 200 g (als Quader zwischen den Platten). Trägheiten und Schwerpunkte sind aus der Geometrie gerechnet, nicht geschätzt.

## Tibia-Geometrie für die IK

Der Tibia-Frame zeigt mit x entlang Segment 1, also bei q_tibia = 0 in Verlängerung des Femurs. Kontaktpunkt ist die Fußkugel:

- **Kugelmitte** im Tibia-Frame: (139,14 / 0 / −77,36) mm. Abstand vom Knie **159,2 mm**, **29,07°** unter Segment 1.
- **Fußspitze** (Kugel unten): 175,0 mm, 29,94° unter Segment 1. Das ist `tibia_len` und `tib_delta` aus dem Makro.

Eine IK, die mit einer geraden Tibia rechnet, braucht deshalb:

```
TIBIA_L   = 0.1592            # Knie -> Kugelmitte
TIBIA_OFF = math.radians(29.07)
q_tibia_urdf = q_tibia_ik - TIBIA_OFF     # IK-Winkel der geraden Ersatz-Tibia -> Gelenkwinkel
FEMUR_L   = 0.150
COXA_L    = 0.060
FEMUR_Z   = -0.017025         # Femur-Achse unter der Coxa-Achse
FOOT_R    = 0.016
```

## Kollision

- **Rumpf:** Platten mit Coxa-Servos als Box (400 × 150 × 42 mm), Box für die Lappen der mittleren Coxas, Kamerahalter als Box und die **Außenform des Panzers** als konvexes Mesh. Damit stimmt das Abrollen über den First.
- **Coxa, Femur:** Hüllquader.
- **Tibia:** Gabel, Segment 1 und das schräge Segment 2 als drei Boxen.
- **Fuß:** Kugel r 16 mm, Link `*_foot` wie bisher. Die Kontaktabfrage der Sim bleibt also gleich.

## Kurztest in PyBullet (DIRECT, Ebene)

- Die URDF lädt sauber: 24 Gelenke, 3,786 kg, Grenzen wie oben.
- **Stehpose** q_femur −15° / q_tibia +100° mit den Servo-Parametern der Sim (Gain 0.03): Der Rumpf liegt mit dem Ursprung bei 130 mm, das ergibt 91 mm Bodenfreiheit. 5 von 6 Füßen haben Kontakt, kein anderer Teil berührt den Boden. Femur max. 1,43 Nm (49 % Stall), Tibia 0,68 Nm.
- **Rückenlage** mit Beinen in Stehpose: SLARC liegt auf dem Panzerfirst und stützt sich auf einem Knie ab, gekippt etwa 3°. Allein dreht er sich also nicht um, das müssen die Beine erledigen.

## Neu erzeugen

`tools/make_urdf.py` (mit `freecadcmd` ausführen) liest `SLARC.FCStd`, schreibt die Meshes und `urdf_data.json`. Danach schreibt `tools/gen_urdf.py` (normales Python) die URDF. Die Pfade oben in beiden Skripten musst du an dein System anpassen.
