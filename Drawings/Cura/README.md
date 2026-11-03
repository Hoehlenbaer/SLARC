# Cura-Projekte

`make_cura_3mf.py` erzeugt pro Druckteil ein fertiges Cura-Projekt `Drawings/STL files/AKP_<Teil>.3mf`: Modell in Druckausrichtung, mittig auf dem Bett, Drucker und Material aus der Vorlage.

## Quelle: Stückliste

Alles Teilspezifische steht in `Drawings/Macros/SLARC_Stueckliste.xlsx`, Blatt Druckteile:

| Spalte | Inhalt | Verwendung |
|---|---|---|
| C Material | PLA, PETG, TPU 95A | Vorlage und Profil. Für TPU gibt es noch keine Vorlage, die Zeile wird übersprungen. |
| J Füllung | z. B. „40 % Gyroid“ | erste Zahl = Fülldichte (pro Modell) |
| K Wände | Linien | Wandlinienanzahl (pro Modell) |
| M Stützen / Besonderes | Freitext | „Tree Support“ schaltet Stützen ein (pro Modell) und setzt die Platzierung auf „überall“ (global als Benutzeränderung), damit z. B. die obere Gabelwange von der unteren aus gestützt wird. „Brim N mm“ setzt Brim mit N mm. |
| N STL-Datei | Name ohne `.stl` | nur Zeilen mit Eintrag bekommen ein Projekt |
| O Cura-Ausrichtung | `-Z`, `+Z`, `+X`, `-X`, `+Y`, `-Y` | Fläche des Modells (Makro-Koordinaten), die aufs Bett kommt. `-Z` = wie modelliert, `+Z` = Oberseite (180°), `±X`/`±Y` = Seitenfläche (90°) |

Basiswerte pro Material (Profil „PLA SLARC“ / „PETG SLARC“) stehen in `BASE` im Skript und entsprechen dem Blatt Druckeinstellungen. Wer dort etwas ändert, ändert es auch im Skript.

## Aufruf

```
python make_cura_3mf.py               # alle Teile mit STL-Datei
python make_cura_3mf.py Cap Base      # nur Teile, deren Name den Text enthält
python make_cura_3mf.py --force Cap   # auch von Hand gespeicherte Projekte überschreiben
```

Benötigt `numpy` und `openpyxl`.

## Hinweise

- Vorlagen in `templates/`: von Marco in Cura 5.13 gespeicherte Projekte für den Anycubic Kobra Plus. PLA mit eSUN PLA+ Black (für Anycubic PLA+ verwendet), PETG mit eSUN PETG Black. Neue Cura-Version oder anderer Drucker: Vorlage neu speichern und ersetzen.
- Füllung, Wände und Stützen stehen als „Einstellungen pro Modell“ am Objekt. In Cura sichtbar über Modell anwählen → links „Einstellungen pro Modell“. Die rechte Leiste zeigt nur das Profil.
- Brim ist in Cura nur global einstellbar. Er steht deshalb als Benutzeränderung im Projekt (Profil mit „*“), nicht im Profil.
- Projekte, die nicht vom Skript stammen (von Hand in Cura gespeichert, z. B. `AKP_SLARC-Stereo_Mount.3mf`, `AKP_SLARC-Baseplate_Top_Front.3mf`), werden nicht überschrieben, außer mit `--force`. Erkannt am Kommentar `SLARC make_cura_3mf` im Modell.
- Beim ersten Öffnen fragt Cura nach dem Profil: „neu erstellen“, später „aktualisieren“.

Geprüft 2026-11-01: `AKP_SLARC_Leg_Test_Stand_Cap.3mf` öffnet in Cura 5.13, Einstellungen pro Modell (40 %, 4 Wände) kommen an. Noch nicht in Cura geprüft: PETG-Profil, Brim über Benutzeränderungen.
