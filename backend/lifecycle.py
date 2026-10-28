"""Vocabolario unico dei cicli di vita, condiviso con i client via /api/stati."""
REPORT_STATES = {
    "inviata": "Inviata", "presa_in_carico": "Presa in carico",
    "in_lavorazione": "In lavorazione", "risolta": "Risolta",
    "archiviata": "Respinta / Archiviata",
}
PROPOSAL_STATES = {
    "in_valutazione": "In valutazione", "approvata": "Approvata",
    "archiviata": "Respinta / Archiviata",
}

def states_for(kind):
    return PROPOSAL_STATES if kind == "proposta" else REPORT_STATES

# Le riaperture sono consentite, comprese le segnalazioni risolte/archiviate.
STATE_TRANSITIONS = {code: set(REPORT_STATES) - {code} for code in REPORT_STATES}
for code in PROPOSAL_STATES:
    STATE_TRANSITIONS.setdefault(code, set()).update(set(PROPOSAL_STATES) - {code})
