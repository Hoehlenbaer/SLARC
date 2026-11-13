# Cura-Projekte

`make_cura_3mf.py` erzeugt pro Druckteil ein fertiges Cura-Projekt `Drawings/STL files/AKP_<Teil>.3mf`: Modell in Druckausrichtung, mittig auf dem Bett, Drucker und Material aus der Vorlage.

## Quelle: Stückliste

Alles Teilspezifische steht in `Drawings/Macros/SLARC_Stueckliste.xlsx`, Blatt Druckteile:

| Spalte | Inhalt | Verwendung |
|---|---|---|
| C Material | PLA, PETG, TPU 95A | Vorlage und Profil |
| J Füllung | z. B. „40 % Gyroid“ | erste Zahl = Fülldichte (pro Modell) |
| K Wände | Linien | Wandlinienanzahl (pro Modell) |
| M Stützen / Besonderes | Freitext | „Tree Support“ schaltet Stützen ein (pro Modell), Platzierung nur vom Druckbett aus. Die Äste führen um die untere Gabelwange herum (in Cura geprüft). „Brim N mm“ setzt Brim mit N mm. |
| N STL-Datei | Name ohne `.stl` | nur Zeilen mit Eintrag bekommen ein Projekt |
| O Cura-Ausrichtung | `-Z`, `+Z`, `+X`, `-X`, `+Y`, `-Y` | Fläche des Modells (Makro-Koordinaten), die aufs Bett kommt. `-Z` = wie modelliert, `+Z` = Oberseite (180°), `±X`/`±Y` = Seitenfläche (90°) |
| P Cura-Extras | `key=value; …` | weitere Einstellungen pro Modell mit Cura-Schlüssel, z. B. `support_top_distance=0.2; support_roof_enable=True` |

Basiswerte pro Material (Profil „PLA SLARC“ / „PETG SLARC“) stehen in `BASE` im Skript und entsprechen dem Blatt Druckeinstellungen. Wer dort etwas ändert, ändert es auch im Skript.

## Aufruf

```
python make_cura_3mf.py               # alle Teile mit STL-Datei
python make_cura_3mf.py Cap Base      # nur Teile, deren Name den Text enthält
python make_cura_3mf.py --force Cap   # auch von Hand gespeicherte Projekte überschreiben
```

Benötigt `numpy` und `openpyxl`.

## Hinweise

- Vorlagen in `templates/`: von Marco in Cura 5.13 gespeicherte Projekte für den Anycubic Kobra Plus. PLA mit eSUN PLA+ Black (für Anycubic PLA+ verwendet), PETG mit eSUN PETG Black, TPU mit Generic TPU 95A (Rückzug, Lüfter, Bett, Beschleunigung und Ruck stehen im Profil). Neue Cura-Version oder anderer Drucker: Vorlage neu speichern und ersetzen.
- Füllung, Wände und Stützen stehen als „Einstellungen pro Modell“ am Objekt. In Cura sichtbar über Modell anwählen → links „Einstellungen pro Modell“. Die rechte Leiste zeigt nur das Profil.
- Stützen: Cura 5.13 hat keine eigene Lüfterdrehzahl für das Stützdach. Alle Profile setzen deshalb „Lüfterdrehzahl überschreiben“ mit „Lüfterdrehzahl für gestützte Haut“ 100 % (V1.6): Die erste Schicht über dem Stützdach wird voll gekühlt und haftet weniger am Dach. Die Einstellung ist nur global möglich und wirkt nur über Stützen. Weil die Stützen pro Modell und nicht global eingeschaltet sind, kann Cura sie ausgegraut anzeigen. Ob sie greift, zeigt der G-Code (M106 S255 vor der Haut über dem Stützdach). Noch nicht geprüft.
- Brim ist in Cura nur global einstellbar. Er steht deshalb als Benutzeränderung im Projekt (Profil mit „*“), nicht im Profil.
- Projekte, die nicht vom Skript stammen (von Hand in Cura gespeichert, z. B. `AKP_SLARC-Stereo_Mount.3mf`, `AKP_SLARC-Baseplate_Top_Front.3mf`), werden nicht überschrieben, außer mit `--force`. Erkannt am Kommentar `SLARC make_cura_3mf` im Modell.
- Beim ersten Öffnen fragt Cura nach dem Profil: „neu erstellen“, später „aktualisieren“.

Geprüft 2026-11-01: `AKP_SLARC_Leg_Test_Stand_Cap.3mf` öffnet in Cura 5.13, Einstellungen pro Modell (40 %, 4 Wände) kommen an. Noch nicht in Cura geprüft: PETG-Profil, Brim über Benutzeränderungen.
