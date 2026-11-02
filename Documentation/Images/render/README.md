# Render des Gesamtmodells

Erzeugt `../slarc_iso.png` (Bild in der Haupt-`README.md`) aus den FreeCAD-Makros.

1. Export (FreeCAD, headless): `freecadcmd export_assembly.py`. Baut `slarc_assembly_v1.py` auf und schreibt je sichtbarem Teil eine STL nach `parts/` plus `parts/manifest.json` mit Farbkategorie (print, servo, deco, pcb …). Der Bein-Prüfstand und die Coxa-Aufnahme des Einzelbeins werden ausgelassen.
2. Render (three.js im Headless-Chromium):
   ```
   npm install three@0.160.0 playwright
   python3 -m http.server 8765 --bind 127.0.0.1 &
   node shot.js iso.png "dir=1.25,-0.85,1.05"
   ```
   `dir` ist die Blickrichtung (Robot-Koordinaten, X vorn, Y links, Z oben), orthografisch. Farben in `index.html` (`M`).
3. Weißen Rand beschneiden und auf 1600 px Breite verkleinern (z. B. mit Pillow).

`parts/` und `node_modules/` gehören nicht ins Repo.
