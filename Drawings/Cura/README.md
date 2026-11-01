# Cura-Projekte

`make_cura_3mf.py` erzeugt pro Druckteil ein fertiges Cura-Projekt `Drawings/STL files/AKP_<Teil>.3mf`: Modell in Druckausrichtung, mittig auf dem Bett, Drucker und Material aus der Vorlage.

- Vorlagen in `templates/`: von Marco in Cura 5.13 gespeicherte Projekte für den Anycubic Kobra Plus. PLA mit eSUN PLA+ Black (für Anycubic PLA+ verwendet), PETG mit eSUN PETG Black.
- Ein Profil pro Material („PLA SLARC“, „PETG SLARC“). Basiswerte in `BASE` im Skript.
- Abweichungen pro Teil (Füllung, Wände) stehen als „Einstellungen pro Modell“ am Objekt. In Cura sichtbar über Modell anwählen → links „Einstellungen pro Modell“. Die rechte Leiste zeigt nur das Profil.
- Neues Teil: Eintrag in `PARTS` (STL-Name, Material, Ausrichtung, Einstellungen pro Modell), Werte wie in der Stückliste (Blatt Druckteile), dann `python make_cura_3mf.py <Teilname>`.
- Achtung: Das Skript überschreibt vorhandene `AKP_<Teil>.3mf` ohne Rückfrage. Von Hand gespeicherte Projekte (z. B. `AKP_SLARC-Stereo_Mount.3mf`) daher nicht in `PARTS` aufnehmen oder vorher umbenennen.
- Beim ersten Öffnen fragt Cura nach dem Profil: „neu erstellen“, später „aktualisieren“.
- Neue Cura-Version oder anderer Drucker: Vorlage neu in Cura speichern und hier ersetzen (setting_version muss passen).

Geprüft 2026-11-01: `AKP_SLARC_Leg_Test_Stand_Cap.3mf` öffnet in Cura 5.13, Einstellungen pro Modell (40 %, 4 Wände) kommen an.
