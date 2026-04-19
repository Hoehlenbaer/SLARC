import json

dateipfad = "/home7slarc/datasets/coco/annotations/instances_train2017_robot35_pseudo.json"

# JSON-Datei laden
with open(dateipfad, 'r') as f:
    daten = json.load(f)

# Prüfen, ob "categories" existiert und auslesen
if "categories" in daten:
    anzahl_klassen = len(daten["categories"])
    klassen_namen = [kat["name"] for kat in daten["categories"]]
    
    print(f"Es sind {anzahl_klassen} Klassen definiert.")
    print(f"Das sind die Namen: {klassen_namen}")
else:
    print("Kein 'categories' Schlüssel gefunden.")