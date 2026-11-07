# brain – bedürfnisgesteuertes High-Level-Brain von SLARC
# Version 0.2 (07.11.2026). Konzept: Documentation/Brain_Konzept.md (Abschnitt 15: Rollen Code/LLM)
#
# Module:
#   datatypes  Beobachtung, Objekte, Personen, Bitten, Menü-Optionen
#   memory     Gewöhnung, Gewichte der Dienste, Tagebuch, Persistenz
#   needs      Bedürfnismodell (energie, neugier, nuetzlichkeit, gesellschaft, unbehagen)
#   safety     harte Grenzen mit Veto
#   behaviors  Verhaltenskatalog, Menübau, Code-Auswahl, Stimmungen
#   arbiter    Entscheidungszyklus 1 Hz, Auslöser fürs LLM
#   prompt     Systemprompt, Few-Shot, Zustandstext, GBNF-Grammatik
#   llm        llama.cpp-Anbindung und Mock-Backend
#   semantic   LLM-Aufgaben: Chat deuten, Objekt einschätzen, Suchorte, Tagebuch
#   scenarios / run_decision_suite       Zielwahl (Code gegen LLM)
#   open_scenarios / run_open_suite      semantische Aufgaben
#   perception_classes  die 41 Klassen der Detektion V5.0, Synonyme, Raum-Anker
#   sim/world, sim/bt, sim/day           simulierte Wohnung, Behavior-Tree-Schicht, Tageslauf
