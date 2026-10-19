import math
import random

# --- STEP 1: La Funzione Calcolo Punti ---
def calcola_punti(importo_spesa):
    """Restituisce i punti fedeltà: 1 punto ogni 10 euro."""
    punti = math.floor(importo_spesa / 10)
    return punti


# --- STEP 2: La Funzione Estrazione Premio ---
def estrai_premio_bonus():
    """Estrae un premio casuale da una lista."""
    premi = ["Buono Caffè", "Sconto 10%", "Nessun Premio", "Ombrello"]
    premio_vinto = random.choice(premi)
    return premio_vinto


# --- STEP 3: La Procedura di Stampa ---
def stampa_scontrino_fidelita(nome_cliente, punti, premio):
    """Stampa il riepilogo del cliente e del bonus ottenuto."""
    print("\n========== RICEVUTA FIDELITÀ ==========")
    print(f"Cliente: {nome_cliente}")
    print(f"Punti totali accumulati: {punti}")
    print(f"Premio Bonus Estratto: {premio}")
    print("=======================================")


# --- STEP 4: Il Main (La Regia) ---
def main():
    cliente = "Mario Rossi"
    spesa_totale = 87.60  # Con 87.60 € deve ottenere 8 punti

    punti_accumulati = calcola_punti(spesa_totale)
    bonus = estrai_premio_bonus()
    stampa_scontrino_fidelita(cliente, punti_accumulati, bonus)


if __name__ == "__main__":
    main()


