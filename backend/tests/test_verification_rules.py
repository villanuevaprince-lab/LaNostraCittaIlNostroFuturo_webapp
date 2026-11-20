"""Logica di decisione a tre livelli e filtro del linguaggio: codice puro, nessun modello."""
import pytest

from backend.services.verification_rules import (
    InvalidModelOutput, REVIEW_MESSAGE, Thresholds, decide, error_decision, merge_violations,
    parse_model_output, scan_language, Violation,
)
from verification_fakes import output


T = Thresholds(alta=0.9, bassa=0.7)


# --- tre livelli -------------------------------------------------------------

def test_no_violations_and_enough_confidence_is_published():
    decision = decide(output("pubblica", confidenza=0.8), T)
    assert decision.esito == "pubblica" and decision.violazioni == ()


def test_only_gravity_one_is_published():
    decision = decide(output("pubblica", [("linguaggio", 1, "Refuso nel titolo")], 0.75), T)
    assert decision.esito == "pubblica" and decision.violazioni[0].gravita == 1


def test_publication_needs_the_low_threshold():
    assert decide(output("pubblica", confidenza=0.69), T).esito == "revisione"


@pytest.mark.parametrize("confidence", [0.9, 0.97, 1.0])
def test_gravity_three_with_high_confidence_is_rejected(confidence):
    decision = decide(output("respingi", [("linguaggio", 3, "Insulto diretto al vicino")], confidence), T)
    assert decision.esito == "respingi"
    assert decision.motivazione == "Contenuto respinto automaticamente: Insulto diretto al vicino."


@pytest.mark.parametrize("confidence", [0.0, 0.5, 0.89, 0.8999])
def test_gravity_three_below_the_high_threshold_goes_to_review(confidence):
    assert decide(output("respingi", [("linguaggio", 3, "Insulto")], confidence), T).esito == "revisione"


@pytest.mark.parametrize("violation", [("scopo", 2, "In parte pubblicitario"), ("coerenza", 2, "Titolo e testo divergono"),
                                       ("plausibilita", 2, "Foto forse generata")])
def test_gravity_two_always_goes_to_review(violation):
    assert decide(output("pubblica", [violation], 0.99), T).esito == "revisione"
    assert decide(output("respingi", [violation], 0.99), T).esito == "revisione"


def test_gravity_two_never_rejects_even_with_full_confidence():
    decision = decide(output("respingi", [("scopo", 2, "Off-topic marginale")], 1.0), T)
    assert decision.esito == "revisione" and decision.motivazione == REVIEW_MESSAGE


@pytest.mark.parametrize("suggestion,violations,expected", [
    ("revisione", [], "revisione"),                                  # il modello stesso ha dubbi
    ("respingi", [], "revisione"),                                   # respingere senza violazioni gravi: incoerente
    ("pubblica", [("linguaggio", 3, "Insulto")], "revisione"),       # gravità 3 ma suggerisce di pubblicare
    ("revisione", [("linguaggio", 3, "Insulto")], "revisione"),      # gravità 3 ma il modello non è sicuro
])
def test_contradictory_model_answers_go_to_review(suggestion, violations, expected):
    assert decide(output(suggestion, violations, 0.99), T).esito == expected


def test_mixed_gravities_reject_only_on_gravity_three_and_explain_only_severe_ones():
    decision = decide(output("respingi", [("linguaggio", 3, "Bestemmia rivolta a una persona"),
                                          ("coerenza", 1, "Titolo vago")], 0.95), T)
    assert decision.esito == "respingi" and "Titolo vago" not in decision.motivazione


# --- criteri -----------------------------------------------------------------

@pytest.mark.parametrize("category,gravity,expected", [
    ("coerenza", 3, "respingi"), ("coerenza", 2, "revisione"), ("coerenza", 1, "pubblica"),
    ("scopo", 3, "respingi"), ("scopo", 2, "revisione"),
    ("linguaggio", 3, "respingi"), ("linguaggio", 2, "revisione"), ("linguaggio", 1, "pubblica"),
    ("plausibilita", 3, "respingi"), ("plausibilita", 2, "revisione"),
])
def test_each_criterion_follows_the_same_rules(category, gravity, expected):
    suggestion = {3: "respingi", 2: "revisione", 1: "pubblica"}[gravity]
    assert decide(output(suggestion, [(category, gravity, "Motivo")], 0.95), T).esito == expected


def test_ai_generated_image_is_rejected_only_with_high_confidence():
    impossible = [("plausibilita", 3, "Immagine generata: auto che galleggia sul Naviglio")]
    assert decide(output("respingi", impossible, 0.93), T).esito == "respingi"
    assert decide(output("respingi", impossible, 0.8), T).esito == "revisione"


# --- filtro del linguaggio ---------------------------------------------------

@pytest.mark.parametrize("text", [
    "Che c4zz0 di buca", "v@ff4nculo al comune", "è uno str0nz0", "c*zzo che disastro", "porco d10",
    "f.u.c.k this road", "Stronz0!", "cazzzzzo", "PUTTANA", "hurensohn", "gilipollas",
])
def test_language_filter_catches_camouflaged_terms(text):
    found = scan_language(text)
    assert found and found[0].categoria == "linguaggio" and found[0].gravita == 2
    assert found[0].origine == "filtro_linguaggio"


@pytest.mark.parametrize("text", [
    "Il lampione di via Roma è spento", "L'autobus 90 è sempre ritardato", "la Madonnina del Duomo",
    "computazione e dati aperti", "c***o", "scritte sul muro della scuola", "Dio ci aiuti con il traffico",
])
def test_language_filter_ignores_clean_or_ambiguous_text(text):
    assert scan_language(text) == []


def test_mild_term_is_gravity_one_and_strong_wins():
    assert scan_language("questa strada è una merda")[0].gravita == 1
    assert scan_language("merda", "e anche cazzo")[0].gravita == 2


def test_language_filter_never_causes_rejection_alone():
    decision = decide(output("pubblica", [], 1.0), T, scan_language("sindaco stronzo"))
    assert decision.esito == "revisione"
    assert any(v.origine == "filtro_linguaggio" for v in decision.violazioni)


def test_filter_mild_term_still_allows_publication():
    decision = decide(output("pubblica", [], 0.9), T, scan_language("la piazza è una merda, servono panchine"))
    assert decision.esito == "pubblica" and decision.violazioni[0].gravita == 1


def test_merge_keeps_model_violation_when_already_as_severe():
    model = (Violation("linguaggio", 3, "Insulto"),)
    assert merge_violations(model, scan_language("stronzo")) == model


# --- risposta del modello ----------------------------------------------------

@pytest.mark.parametrize("payload", [
    [], {"esito_suggerito": "boh", "violazioni": [], "confidenza": 0.5},
    {"esito_suggerito": "pubblica", "violazioni": [], "confidenza": 1.5},
    {"esito_suggerito": "pubblica", "violazioni": [], "confidenza": "alta"},
    {"esito_suggerito": "pubblica", "violazioni": [], "confidenza": True},
    {"esito_suggerito": "pubblica", "violazioni": "nessuna", "confidenza": 0.5},
    {"esito_suggerito": "pubblica", "violazioni": [{"categoria": "scopo", "gravita": 4, "spiegazione": "x"}], "confidenza": 0.5},
    {"esito_suggerito": "pubblica", "violazioni": [{"categoria": "scopo", "gravita": True, "spiegazione": "x"}], "confidenza": 0.5},
    {"esito_suggerito": "pubblica", "violazioni": ["testo"], "confidenza": 0.5},
])
def test_invalid_model_output_is_rejected(payload):
    with pytest.raises(InvalidModelOutput):
        parse_model_output(payload)


def test_model_output_is_normalized():
    parsed = parse_model_output({"esito_suggerito": "revisione", "confidenza": 0.12345678, "note_moderatore": " n ",
                                 "violazioni": [{"categoria": "sconosciuta", "gravita": 2, "spiegazione": ""}],
                                 "categorie_suggerite": [3, 3, "x", True, 5, 6, 7]})
    assert parsed.confidenza == 0.1235 and parsed.note_moderatore == "n"
    assert parsed.violazioni[0].categoria == "altro" and parsed.violazioni[0].spiegazione == "Nessuna spiegazione."
    assert parsed.categorie_suggerite == (3, 5, 6)


def test_thresholds_are_validated():
    with pytest.raises(ValueError):
        Thresholds(alta=0.5, bassa=0.7)
    with pytest.raises(ValueError):
        Thresholds(alta=1.2, bassa=0.7)


def test_error_decision_goes_to_review():
    decision = error_decision("timeout del modello")
    assert decision.esito == "revisione" and "timeout" in decision.violazioni[0].spiegazione
