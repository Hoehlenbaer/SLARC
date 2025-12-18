import ollama
import json
import time
from typing import Dict, Any, List

# Importiere den zuvor definierten System-Prompt
# WICHTIG: Ersetzen Sie dies durch den tatsächlichen, oben definierten Prompt-Inhalt.
FINAL_SYSTEM_PROMPT = """
Du bist die autonome Planungs- und Entscheidungszentrale eines Hexapod-Roboters. 
Deine Aufgabe ist es, basierend auf den aktuellen Sensordaten und dem Verlauf präzise, quantifizierte Befehlsketten zu erstellen, um das Ziel zu erreichen oder Schaden zu vermeiden.

WICHTIGSTE REGEL: Antworte IMMER NUR mit EINEM validen JSON-Objekt.

NEUE KRITISCHE SICHERHEITSREGELN:
- Bei Entfernungen < 0.1 METER (Extreme Nähe/Kontakt) MUSS der erste Befehl im "actions"-Array IMMER "STOP" oder eine "WALK" Richtung "BACK" sein.
- Drehungen ("TURN") sind erst ab einem Mindestabstand von 0.2 METER von einem Hindernis erlaubt.

STRUKTUR DER ANTWORT:
Das JSON-Objekt MUSS folgende Felder enthalten:
1. "reasoning": (String) Eine knappe Begründung deiner Entscheidung (maximal 15 Wörter).
2. "actions": (Array) Eine Liste von mindestens einem, maximal drei sequenziellen Befehls-Objekten.

VERFÜGBARE BEFEHLE (actions):
- {"command": "WALK", "direction": "FORWARD"|"BACK", "value": FLOAT, "unit": "M"}
- {"command": "TURN", "direction": "LEFT"|"RIGHT", "value": INTEGER, "unit": "DEG"}
- {"command": "INTERACT", "target": STRING, "type": "GRAB"|"PUSH"|"WAVE"}
- {"command": "STOP", "reason": STRING}

Beachte den aktuellen Status und Verlauf, um Doppelbefehle oder Fehlreaktionen zu vermeiden.
"""

class HexabotBrain:
    """
    Klasse zur Verwaltung der LLM-Entscheidungslogik via Ollama.
    """
    def __init__(self, model_tag: str):
        self.model_tag = model_tag
        print(f"🧠 HexabotBrain initialisiert. Modell: {self.model_tag}")

    def _parse_output(self, json_string: str) -> Dict[str, Any]:
        """Versucht, den JSON-String zu parsen und gibt bei Misserfolg einen Not-Stopp zurück."""
        try:
            decision = json.loads(json_string)
            # Einfache Validierung des Schemas
            if not isinstance(decision.get('actions'), list):
                 raise ValueError("JSON-Struktur ist ungültig (actions ist keine Liste).")
            return decision
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[FEHLER] Ungültiges JSON-Format oder Strukturfehler: {e}")
            return {
                "reasoning": "Fehler im Modell-Output-Format",
                "actions": [{"command": "STOP", "reason": "Parsing failed"}]
            }

    def get_decision(self, history: str, vision_input: str) -> Dict[str, Any]:
        """Sendet den Kontext an Ollama und gibt eine geparste Entscheidungs-Aktion zurück."""
        
        user_input = f"Status: {history}. Input: {vision_input}. Was soll der Roboter tun?"
        
        messages = [
            # Der System-Prompt wird explizit gesendet, um maximale Zuverlässigkeit zu gewährleisten.
            {'role': 'system', 'content': FINAL_SYSTEM_PROMPT}, 
            {'role': 'user', 'content': user_input}
        ]
        
        print(f"\n[INFO] Sende Kontext: {user_input[:80]}...")
        start_time = time.time()
        
        try:
            response = ollama.chat(
                model=self.model_tag,
                format='json',
                messages=messages
            )
            
            end_time = time.time()
            latency = end_time - start_time
            print(f"[INFO] Latenz: {latency:.2f} Sekunden.")

            json_string = response['message']['content']
            return self._parse_output(json_string)

        except ollama.RequestError as e:
            print(f"[FEHLER] Ollama Server ist nicht erreichbar: {e}")
            return {"reasoning": "Ollama Server ist offline", "actions": [{"command": "STOP", "reason": "Server offline"}]}


# --- Testroutine ---
def run_hexabot_tests(brain: HexabotBrain):
    """Führt die definierten Tests durch und zeigt die Ergebnisse."""
    
    TESTFÄLLE = [
        {
            "name": "Kollisionsvermeidung",
            "history": "FREI",
            "vision": "Stereo-Vision erkennt eine große rote Kiste in 1.2m direkt voraus (0 Grad). Der Weg rechts ist frei."
        },
        {
            "name": "Sicherheitsregel-Check (Blockade)",
            "history": "BLOCKIERT",
            "vision": "Stereo-Vision sieht eine massive, unbewegliche Wand in 0.05m."
        }
    ]
    
    print("\n" + "="*50)
    print(f"STARTE ROBUSTEN TESTLAUF FÜR MODELL: {brain.model_tag}")
    print("="*50 + "\n")

    for case in TESTFÄLLE:
        print("-" * 50)
        print(f"TESTFALL: {case['name']}")
        
        result = brain.get_decision(case['history'], case['vision'])
        
        print("\n[OUTPUT] Generierter Befehl:")
        print(f"  > Reasoning: {result.get('reasoning', 'N/A')}")
        
        for i, action in enumerate(result.get('actions', [])):
            cmd = action.get('command')
            if cmd in ["WALK", "TURN"]:
                val = action.get('value', 'N/A')
                unit = action.get('unit', 'N/A')
                direction = action.get('direction', 'N/A')
                print(f"  > Action {i+1}: {cmd} {direction} {val} {unit}")
            elif cmd in ["INTERACT", "STOP"]:
                param = action.get('target', action.get('reason'))
                print(f"  > Action {i+1}: {cmd} ({param})")
        
        print("-" * 50)
        time.sleep(1) 

if __name__ == "__main__":
    # Verwenden Sie den tatsächlichen Tag, den Sie in Ihrer Modelfile erstellt haben
    HEXABOT_MODEL_TAG = 'SLARC-brain' 
    
    robot_brain = HexabotBrain(model_tag=HEXABOT_MODEL_TAG)
    
    # Führt die Testfälle aus und zeigt die Latenz sowie die robuste Verarbeitung
    run_hexabot_tests(robot_brain)