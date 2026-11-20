"""Regole di decisione della verifica AI: codice puro, nessuna rete e nessun database.

Il modello suggerisce; la decisione la prende sempre questo modulo:
- rifiuto automatico solo con una violazione di gravità 3, confidenza >= soglia alta
  e un modello che a sua volta suggerisce di respingere;
- pubblicazione automatica solo senza violazioni o con sole violazioni di gravità 1,
  confidenza >= soglia bassa e un modello che suggerisce di pubblicare;
- revisione umana in tutti gli altri casi (gravità 2, confidenza intermedia,
  indicazioni contraddittorie, errori del modello).
"""

import math
import re
import unicodedata
from dataclasses import dataclass, field


SUGGESTIONS = ("pubblica", "respingi", "revisione")
CATEGORIES = ("coerenza", "scopo", "linguaggio", "plausibilita", "altro")
CATEGORY_LABELS = {"coerenza": "Coerenza", "scopo": "Scopo civico", "linguaggio": "Linguaggio",
                   "plausibilita": "Plausibilità", "altro": "Altro"}
REVIEW_MESSAGE = "Il contenuto sarà esaminato da un moderatore del comitato prima della pubblicazione."


class InvalidModelOutput(ValueError):
    """La risposta del modello non rispetta lo schema atteso."""


@dataclass(frozen=True)
class Violation:
    categoria: str
    gravita: int
    spiegazione: str
    origine: str = "modello"


@dataclass(frozen=True)
class ModelOutput:
    esito_suggerito: str
    violazioni: tuple
    confidenza: float
    note_moderatore: str = ""
    categorie_suggerite: tuple = ()


@dataclass(frozen=True)
class Decision:
    esito: str  # pubblica / respingi / revisione
    motivazione: str  # testo per l'utente
    violazioni: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class Thresholds:
    alta: float = 0.90  # rifiuto automatico
    bassa: float = 0.70  # pubblicazione automatica

    def __post_init__(self):
        if not (0 <= self.bassa <= self.alta <= 1):
            raise ValueError("Le soglie devono rispettare 0 <= bassa <= alta <= 1.")


# --- validazione della risposta del modello ---------------------------------

def _text(value, limit):
    return str(value or "").strip()[:limit]


def parse_model_output(data):
    """Valida il JSON del modello; qualunque deviazione dallo schema è un errore del modello."""
    if not isinstance(data, dict):
        raise InvalidModelOutput("la risposta non è un oggetto JSON")
    suggestion = data.get("esito_suggerito")
    if suggestion not in SUGGESTIONS:
        raise InvalidModelOutput("esito_suggerito non valido")
    confidence = data.get("confidenza")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
        raise InvalidModelOutput("confidenza non valida")
    if not 0 <= confidence <= 1:
        raise InvalidModelOutput("confidenza fuori intervallo")
    raw_violations = data.get("violazioni")
    if not isinstance(raw_violations, list):
        raise InvalidModelOutput("violazioni non è una lista")
    violations = []
    for item in raw_violations[:20]:
        if not isinstance(item, dict):
            raise InvalidModelOutput("violazione non valida")
        category, gravity = item.get("categoria"), item.get("gravita")
        if category not in CATEGORIES:
            category = "altro"
        if isinstance(gravity, bool) or gravity not in (1, 2, 3):
            raise InvalidModelOutput("gravità non valida")
        violations.append(Violation(category, int(gravity), _text(item.get("spiegazione"), 500) or "Nessuna spiegazione."))
    categories = data.get("categorie_suggerite") or []
    if not isinstance(categories, list):
        categories = []
    categories = tuple(dict.fromkeys(c for c in categories if isinstance(c, int) and not isinstance(c, bool)))[:3]
    return ModelOutput(suggestion, tuple(violations), round(float(confidence), 4),
                       _text(data.get("note_moderatore"), 2000), categories)


# --- filtro deterministico del linguaggio ------------------------------------
# Rete di sicurezza: intercetta parolacce, bestemmie e insulti anche camuffati con
# asterischi, numeri o separatori. Non decide mai un rifiuto (gravità massima 2):
# una citazione, ad esempio di scritte offensive su un muro, va valutata da una persona.

STRONG_TERMS = (
    # italiano
    "cazzo", "cazzate", "minchia", "stronzo", "stronza", "stronzi", "stronze", "vaffanculo", "fanculo",
    "coglione", "coglioni", "cogliona", "puttana", "troia", "bastardo", "bastarda", "bastardi",
    "porco dio", "dio cane", "dio porco", "porca madonna", "madonna puttana", "figlio di puttana",
    "pezzo di merda", "testa di cazzo", "idiota", "deficiente", "imbecille", "cretino",
    # inglese
    "fuck", "fucking", "motherfucker", "asshole", "bitch", "bastard", "dickhead",
    # francese, spagnolo, tedesco
    "putain", "connard", "salope", "puta", "cabron", "gilipollas", "arschloch", "hurensohn",
)
MILD_TERMS = ("merda", "merdoso", "shit", "merde", "mierda", "scheisse")

_LEET = {"a": "a4@*", "e": "e3*", "i": "i1!|*", "o": "o0*", "s": "s5$*", "t": "t7*", "g": "g9*", "z": "z2*"}


def _strip_accents(text):
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _term_pattern(term):
    parts = []
    for index, char in enumerate(term):
        if char == " ":
            parts.append(r"[\s._\-]*")
            continue
        variants = _LEET.get(char, char + "*")
        if index == 0:
            variants = variants.replace("*", "")  # la prima lettera deve essere reale
        parts.append("[" + re.escape(variants) + "]+" + r"[._\-]?")
    return re.compile(r"(?<![a-z0-9])" + "".join(parts) + r"(?![a-z0-9])", re.IGNORECASE)


_PATTERNS = [(term, 2, _term_pattern(term)) for term in STRONG_TERMS] + \
            [(term, 1, _term_pattern(term)) for term in MILD_TERMS]


def scan_language(*texts):
    """Restituisce al massimo una violazione 'linguaggio' (la più grave trovata)."""
    text = _strip_accents(" ".join(t for t in texts if t)).lower()
    found = []
    for term, gravity, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            fragment = match.group(0)
            letters = sum(ch.isalpha() for ch in fragment)
            if letters * 2 < len(fragment.replace(" ", "")):  # troppi simboli: non è una parola
                continue
            found.append((gravity, term))
            break
    if not found:
        return []
    gravity = max(g for g, _ in found)
    terms = sorted({t for g, t in found if g == gravity})
    kind = "termini volgari o offensivi" if gravity == 2 else "un termine volgare"
    return [Violation("linguaggio", gravity, f"Il filtro automatico ha trovato {kind}: {', '.join(terms)}.",
                      "filtro_linguaggio")]


def merge_violations(model_violations, filter_violations):
    """Aggiunge le violazioni del filtro solo se il modello non ne ha già una pari o più grave."""
    merged = list(model_violations)
    for extra in filter_violations:
        if not any(v.categoria == extra.categoria and v.gravita >= extra.gravita for v in merged):
            merged.append(extra)
    return tuple(merged)


# --- decisione a tre livelli --------------------------------------------------

def decide(output, thresholds, extra_violations=()):
    violations = merge_violations(output.violazioni, extra_violations)
    max_gravity = max((v.gravita for v in violations), default=0)
    confidence = output.confidenza
    severe = [v for v in violations if v.gravita == 3]

    if severe and confidence >= thresholds.alta and output.esito_suggerito == "respingi":
        reasons = "; ".join(v.spiegazione.rstrip(".") for v in severe)
        return Decision("respingi", f"Contenuto respinto automaticamente: {reasons}.", violations)
    if max_gravity <= 1 and confidence >= thresholds.bassa and output.esito_suggerito == "pubblica":
        return Decision("pubblica", "Verifica superata: il contenuto è pubblico.", violations)
    return Decision("revisione", REVIEW_MESSAGE, violations)


def error_decision(error_message):
    """Il modello ha fallito troppe volte: decide una persona."""
    return Decision("revisione", REVIEW_MESSAGE,
                    (Violation("altro", 2, f"Verifica automatica non riuscita: {error_message[:300]}", "modello"),))
