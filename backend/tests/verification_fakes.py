"""Finto modello di verifica per i test: nessuna rete, risposte programmate."""
from backend.services.verification_rules import parse_model_output
from backend.services.verifier import Verifier


def output(esito="pubblica", violazioni=(), confidenza=0.95, note="", categorie=()):
    return parse_model_output({"esito_suggerito": esito, "confidenza": confidenza, "note_moderatore": note,
                               "violazioni": [{"categoria": c, "gravita": g, "spiegazione": s} for c, g, s in violazioni],
                               "categorie_suggerite": list(categorie)})


class FakeVerifier(Verifier):
    name = "fake:test"

    def __init__(self, results=None, available=True):
        self.results = list(results or [])  # ModelOutput oppure eccezioni da sollevare, in ordine
        self.is_available = available
        self.calls = []

    def available(self):
        return self.is_available

    def verify(self, item):
        self.calls.append(item)
        result = self.results.pop(0) if self.results else output()
        if isinstance(result, Exception):
            raise result
        return result
