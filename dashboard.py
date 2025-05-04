# -*- coding: utf-8 -*-
import pandas as pd
import datetime
import streamlit as st
import matplotlib.pyplot as plt
import json
from pathlib import Path
import numpy as np # Per gestire NaN

# ————————————————————————————————————————————————————————————————
# CONFIGURAZIONE STREAMLIT E COSTANTI
# ————————————————————————————————————————————————————————————————
st.set_page_config(page_title="Scheda Allenamenti", layout="centered")
st.markdown("""
<style>
  .block-container { max-width: 800px; padding: 1rem; }
  /* Aggiungi altri stili se necessario */
</style>
""", unsafe_allow_html=True)

# Applichiamo un tema matplotlib più gradevole
plt.style.use('ggplot')

# !!! IMPORTANTE: MODIFICA QUESTO PERCORSO CON QUELLO DEL TUO FILE EXCEL !!!
EXCEL_FILE_PATH = Path('Scheda_Ipertrofia_Corsa_Excel.xlsx')

# Percorso per il file delle note di gruppo (JSON)
NOTE_FILE = Path('group_notes.json')

# --- NUOVO: Percorso per lo storico della corsa (CSV) ---
# Questo file verrà creato/usato nella stessa cartella dello script, se non specificato diversamente
RUNNING_HISTORY_FILE = Path('storico_corsa.csv')

# Mappatura Nomi Fogli Excel -> Nomi Gruppi per Note e Logica
GROUPS = {
    "Day 1 - Lower A": "Lower 1",
    "Day 2 - Upper A": "Upper 1",
    "Day 3 - Lower B": "Lower 2",
    "Day 4 - Upper B": "Upper 2",
    "Corsa - Venerdì":  "Corsa" # Assicurati che il nome del foglio corrisponda
    # Aggiungi altre mappature se necessario
}

# Colonne attese per il file CSV della corsa
RUN_COLS_EXPECTED = ['Data','Tipo Corsa','Distanza (km)','Tempo (min)','Passo Medio (min/km)','Battiti Medi (BPM)','Sforzo','Note']

# ————————————————————————————————————————————————————————————————
# NOTE CONDIVISE (Gestione file JSON)
# ————————————————————————————————————————————————————————————————
def load_group_notes():
    """Carica le note di gruppo dal file JSON."""
    if NOTE_FILE.exists():
        try:
            return json.loads(NOTE_FILE.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            st.error(f"Errore nella lettura del file delle note ({NOTE_FILE}). File corrotto?")
            return {g: "" for g in set(GROUPS.values())} # Ritorna vuoto in caso di errore
    return {g: "" for g in set(GROUPS.values())} # Ritorna vuoto se il file non esiste

def save_group_note(group, text):
    """Salva una nota per un gruppo specifico nel file JSON."""
    notes = load_group_notes()
    notes[group] = text
    try:
        NOTE_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    except Exception as e:
        st.error(f"Errore nel salvataggio delle note ({NOTE_FILE}): {e}")

# ————————————————————————————————————————————————————————————————
# CARICAMENTO / SALVATAGGIO DATI STORICI
# ————————————————————————————————————————————————————————————————

# --- Funzione per caricare STORICO PESI (da Excel 'Peso Storico') ---
def load_weights_data(file_path):
    """Carica lo storico degli allenamenti di pesi dal foglio 'Peso Storico' dell'Excel."""
    df_weights = pd.DataFrame(columns=['Data','Esercizio','Peso','Ripetizioni','Sforzo','Performance']) # Def dataframe default
    try:
        df_weights = pd.read_excel(file_path, sheet_name='Peso Storico')

        # Validazione e pulizia colonne Pesi
        required_cols = ['Data','Esercizio','Peso','Ripetizioni','Sforzo']
        for col in required_cols:
            if col not in df_weights.columns:
                 st.warning(f"Colonna '{col}' mancante nel foglio 'Peso Storico'. Verrà creata vuota.")
                 df_weights[col] = '' if col in ['Data', 'Esercizio'] else 0

        # Conversione e gestione errori
        df_weights['Data'] = pd.to_datetime(df_weights['Data'], errors='coerce').dt.date
        df_weights = df_weights.dropna(subset=['Data']) # Rimuove righe senza data valida

        num_cols_w = ['Peso', 'Ripetizioni', 'Sforzo']
        for col in num_cols_w:
            df_weights[col] = pd.to_numeric(df_weights[col], errors='coerce').fillna(0)
        df_weights['Ripetizioni'] = df_weights['Ripetizioni'].astype(int)
        df_weights['Sforzo'] = df_weights['Sforzo'].astype(int)

        # Calcola metrica Performance (ignorando errori se i dati non sono numerici)
        df_weights['Performance'] = pd.to_numeric(df_weights['Peso'], errors='coerce') * \
                                    pd.to_numeric(df_weights['Ripetizioni'], errors='coerce') * \
                                    pd.to_numeric(df_weights['Sforzo'], errors='coerce')
        df_weights['Performance'] = df_weights['Performance'].fillna(0) # Riempi NaN con 0

    except FileNotFoundError:
         st.warning(f"File Excel non trovato: {file_path}. Verrà creato al primo salvataggio di dati Pesi.")
    except Exception as e:
        # Gestisce il caso in cui il foglio specifico non esista
        if "No sheet named 'Peso Storico'" in str(e):
            st.warning("Il foglio 'Peso Storico' non è stato trovato nel file Excel. Verrà creato al primo salvataggio.")
        else:
            st.error(f"Errore imprevisto nel caricamento di 'Peso Storico': {e}")
            # Ritorna comunque un dataframe vuoto per evitare errori downstream
            df_weights = pd.DataFrame(columns=['Data','Esercizio','Peso','Ripetizioni','Sforzo','Performance'])

    return df_weights.reset_index(drop=True) # Resetta indice dopo caricamento/pulizia

# --- NUOVA: Funzione per caricare STORICO CORSA (da CSV) ---
def load_running_data(csv_path):
    """Carica lo storico degli allenamenti di corsa dal file CSV specificato."""
    if csv_path.exists():
        try:
            df_runs = pd.read_csv(csv_path, parse_dates=['Data']) # Prova a parsare le date subito

            # Verifica e aggiungi colonne mancanti se necessario
            for col in RUN_COLS_EXPECTED:
                if col not in df_runs.columns:
                    st.warning(f"Colonna '{col}' mancante nel file {csv_path}. Verrà aggiunta.")
                    if col in ['Data', 'Tipo Corsa', 'Note']:
                        df_runs[col] = ''
                    elif col == 'Passo Medio (min/km)':
                         df_runs[col] = 0.0 # Float per passo
                    else:
                         df_runs[col] = 0 # Int o Float per altre metriche numeriche

            # Conversione e pulizia colonne Corsa
            df_runs['Data'] = pd.to_datetime(df_runs['Data'], errors='coerce').dt.date
            df_runs = df_runs.dropna(subset=['Data']) # Rimuovi righe senza data valida

            num_cols_run = ['Distanza (km)', 'Tempo (min)', 'Passo Medio (min/km)', 'Battiti Medi (BPM)', 'Sforzo']
            for col in num_cols_run:
                 df_runs[col] = pd.to_numeric(df_runs[col], errors='coerce').fillna(0)
                 # Mantieni interi dove appropriato
                 if col in ['Battiti Medi (BPM)', 'Sforzo']:
                     df_runs[col] = df_runs[col].astype(int)

            # Ricalcola passo medio per coerenza (opzionale, sovrascrive quello letto se presente)
            mask = (df_runs['Distanza (km)'] > 0) & (df_runs['Tempo (min)'] > 0)
            df_runs.loc[mask, 'Passo Medio (min/km)'] = df_runs.loc[mask, 'Tempo (min)'] / df_runs.loc[mask, 'Distanza (km)']
            df_runs['Passo Medio (min/km)'] = df_runs['Passo Medio (min/km)'].replace([np.inf, -np.inf], np.nan).fillna(0)

            return df_runs[RUN_COLS_EXPECTED].reset_index(drop=True) # Assicura ordine colonne e resetta indice

        except pd.errors.EmptyDataError:
             st.warning(f"Il file dello storico corsa ({csv_path}) è vuoto.")
             return pd.DataFrame(columns=RUN_COLS_EXPECTED)
        except Exception as e:
            st.error(f"Errore nel caricamento o processamento di {csv_path}: {e}")
            return pd.DataFrame(columns=RUN_COLS_EXPECTED) # Ritorna vuoto in caso di errore grave
    else:
        st.info(f"File storico corsa ({csv_path}) non trovato. Verrà creato al primo salvataggio.")
        return pd.DataFrame(columns=RUN_COLS_EXPECTED) # Ritorna vuoto se il file non esiste

# --- Funzione per salvare STORICO PESI (in Excel 'Peso Storico') ---
def save_weights_data(df_to_save, file_path):
    """Salva il DataFrame dei pesi nel foglio 'Peso Storico' dell'Excel, preservando gli altri fogli."""
    # Rimuovi colonna calcolata 'Performance' prima di salvare
    df_cleaned = df_to_save.drop(columns=['Performance'], errors='ignore')

    # Assicurati che la colonna Data sia solo data
    if 'Data' in df_cleaned.columns:
        df_cleaned['Data'] = pd.to_datetime(df_cleaned['Data']).dt.date

    try:
        # Leggi tutti i fogli esistenti per non sovrascriverli
        all_sheets = {}
        try:
            # Usa ExcelFile per gestire meglio file potenzialmente grandi o complessi
            with pd.ExcelFile(file_path) as xls:
                all_sheets = {name: pd.read_excel(xls, name) for name in xls.sheet_names}
        except FileNotFoundError:
            # Il file non esiste ancora, verrà creato
            pass
        except Exception as e:
             st.error(f"Errore nella lettura preliminare di {file_path} prima del salvataggio: {e}")
             # Potrebbe essere rischioso continuare, ma proviamo a salvare solo il nuovo foglio
             all_sheets = {}


        # Aggiorna (o aggiungi) il foglio 'Peso Storico'
        all_sheets['Peso Storico'] = df_cleaned

        # Scrivi TUTTI i fogli (vecchi e aggiornati) nel file Excel
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            for name, df_sheet in all_sheets.items():
                 # Assicurati che anche i fogli non modificati abbiano le date corrette
                 if 'Data' in df_sheet.columns and name != 'Peso Storico':
                      df_sheet['Data'] = pd.to_datetime(df_sheet['Data'], errors='coerce').dt.date
                 df_sheet.to_excel(writer, sheet_name=name, index=False)

    except PermissionError:
        st.error(f"Errore di Permesso durante il salvataggio su '{file_path}'. Assicurati che il file non sia aperto in Excel o un altro programma.")
    except Exception as e:
        st.error(f"Errore generico durante il salvataggio dei dati Pesi su Excel: {e}")


# --- NUOVA: Funzione per salvare STORICO CORSA (in CSV) ---
def save_running_data(df_to_save, csv_path):
     """Salva il DataFrame della corsa nel file CSV specificato."""
     # Assicurati che la colonna Data sia solo data
     df_cleaned = df_to_save.copy()
     if 'Data' in df_cleaned.columns:
          df_cleaned['Data'] = pd.to_datetime(df_cleaned['Data']).dt.date

     # Salva usando le colonne definite per coerenza
     df_to_save_ordered = df_cleaned[RUN_COLS_EXPECTED]

     try:
        df_to_save_ordered.to_csv(csv_path, index=False, encoding='utf-8', date_format='%Y-%m-%d')
     except PermissionError:
         st.error(f"Errore di Permesso durante il salvataggio su '{csv_path}'. Il file potrebbe essere aperto altrove.")
     except Exception as e:
        st.error(f"Errore durante il salvataggio dello storico Corsa su {csv_path}: {e}")


# ————————————————————————————————————————————————————————————————
# CARICAMENTO DATI INIZIALE E LETTURA FOGLI PROGRAMMA
# ————————————————————————————————————————————————————————————————
df_weights = load_weights_data(EXCEL_FILE_PATH)
df_runs = load_running_data(RUNNING_HISTORY_FILE)

# Crea copie per operazioni interne, così i dati originali non vengono modificati fino al salvataggio
_df_weights = df_weights.copy()
_df_runs = df_runs.copy()

# Leggi nomi fogli programma dall'Excel
program_sheets = []
try:
    # Usa pd.ExcelFile per efficienza se leggi più fogli
    with pd.ExcelFile(EXCEL_FILE_PATH) as xls:
        # Escludi il foglio dello storico pesi dai fogli selezionabili come programma
        program_sheets = [s for s in xls.sheet_names if s.lower() != 'peso storico'] # Confronto case-insensitive
except FileNotFoundError:
    st.warning(f"File Excel '{EXCEL_FILE_PATH.name}' non trovato. Impossibile caricare i programmi.")
except Exception as e:
    st.error(f"Errore nella lettura dei nomi dei fogli da Excel: {e}")


# ————————————————————————————————————————————————————————————————
# INTERFACCIA UTENTE STREAMLIT
# ————————————————————————————————————————————————————————————————
st.title("Scheda Interattiva: Monitor Allenamenti")
st.caption(f"Dati Pesi da: '{EXCEL_FILE_PATH.name}' (Foglio: 'Peso Storico') | Dati Corsa da: '{RUNNING_HISTORY_FILE.name}'")


# --- Sezione 1: Selezione Giorno e Visualizzazione Programma (da Excel) ---
st.header("🗓️ Programma del Giorno")
if not program_sheets:
    st.warning("Nessun foglio di programma trovato nel file Excel o file non accessibile.")
    sheet_sel = None
    esercizi = []
else:
    # Metti l'opzione "Seleziona..." per prima
    sheet_options = ["-- Seleziona Giorno --"] + program_sheets
    sheet_sel = st.selectbox("Scegli il programma di oggi:", sheet_options)

# Determina il tipo di allenamento (Pesi o Corsa) e ottieni esercizi se è pesi
current_group = None
is_running_day = False
esercizi = []

if sheet_sel and sheet_sel != "-- Seleziona Giorno --":
    current_group = GROUPS.get(sheet_sel) # Trova il gruppo corrispondente (es. "Lower 1", "Corsa")
    is_running_day = (current_group == "Corsa")

    try:
        # Leggi il foglio del programma selezionato dall'Excel
        prog_df = pd.read_excel(EXCEL_FILE_PATH, sheet_name=sheet_sel)
        st.subheader(f"Programma: {sheet_sel}")

        if not prog_df.empty:
            if is_running_day:
                # Mostra colonne rilevanti per il programma di corsa (leggile dal tuo Excel)
                # Adatta queste colonne ai nomi presenti nel tuo foglio Excel per la corsa
                cols_to_show_run = [col for col in ['Tipo', 'Obiettivo', 'Durata', 'Intensità', 'Note Programma', 'Esercizio'] if col in prog_df.columns]
                if not cols_to_show_run: cols_to_show_run = list(prog_df.columns) # Fallback: mostra tutte le colonne
                st.dataframe(prog_df[cols_to_show_run], use_container_width=True)
                # Nessun esercizio specifico da selezionare per la registrazione della corsa
            else:
                # Mostra programma pesi, assicurati che le colonne esistano
                cols_to_show_weights = [col for col in ['Esercizio','Serie','Ripetizioni', 'Recupero', 'Note'] if col in prog_df.columns]
                if 'Esercizio' not in cols_to_show_weights: cols_to_show_weights = list(prog_df.columns) # Fallback
                st.dataframe(prog_df[cols_to_show_weights], use_container_width=True)

                # Estrai lista esercizi UNICI per il dropdown di registrazione
                if 'Esercizio' in prog_df.columns:
                    esercizi = prog_df['Esercizio'].dropna().unique().tolist()
                else:
                    st.warning("Colonna 'Esercizio' non trovata nel programma per popolare l'elenco.")
        else:
            st.info(f"Il foglio del programma '{sheet_sel}' è vuoto.")

    except Exception as e:
        st.error(f"Impossibile leggere il foglio del programma '{sheet_sel}' da Excel: {e}")

elif sheet_sel == "-- Seleziona Giorno --":
    st.info("Seleziona un giorno dall'elenco per vedere il programma e registrare l'allenamento.")
else:
     # Questo caso non dovrebbe verificarsi se program_sheets è gestito correttamente
     st.info("Seleziona un giorno valido.")


# --- Sezione 2: Note Condivise (da file JSON) ---
st.header("📝 Note di Gruppo")
if current_group: # Mostra solo se un giorno valido è selezionato e mappato a un gruppo
    # Colori per i badge dei gruppi
    colors = {"Upper":"#e57373","Lower":"#81c784","Cardio":"#64b5f6","HITT":"#ffb74d","Corsa":"#ba68c8", None:"#777"}
    base = current_group.split()[0] if current_group else None # Es. Estrae "Lower" da "Lower 1"
    col  = colors.get(base, "#777") # Colore di default grigio

    # Mostra badge e area note
    st.markdown(f"Note per il gruppo: <span style='background:{col};color:#fff;padding:4px 8px;border-radius:4px;margin-left:5px;'>{current_group}</span>", unsafe_allow_html=True)
    notes_data = load_group_notes()
    current_note = notes_data.get(current_group, "") # Ottieni nota attuale o stringa vuota
    note_text_area = st.text_area(f"Scrivi o modifica la nota per {current_group}:", current_note, height=100, key=f"note_area_{current_group}")

    if st.button(f"💾 Salva Nota {current_group}", key=f"save_note_{current_group}"):
        if note_text_area != current_note: # Salva solo se c'è una modifica
             save_group_note(current_group, note_text_area)
             st.success(f"Nota per '{current_group}' salvata!")
        else:
             st.info("Nessuna modifica alla nota da salvare.")
elif sheet_sel and sheet_sel != "-- Seleziona Giorno --":
     st.info(f"Il foglio '{sheet_sel}' non è associato a nessun gruppo definito nella mappa GROUPS.")
else:
    st.info("Seleziona un giorno per vedere o modificare le note di gruppo.")


# --- Sezione 3: Inserimento Performance (Condizionale Pesi/Corsa) ---
st.header("💪 Registra Allenamento")

# Se nessun giorno è selezionato, non mostrare la sezione di registrazione
if not sheet_sel or sheet_sel == "-- Seleziona Giorno --":
    st.info("Seleziona prima un giorno dal menu 'Programma del Giorno' per poter registrare.")
else:
    data_allenamento = st.date_input("Data Allenamento:", datetime.date.today())

    if is_running_day:
        # --- Input per la CORSA (salva su CSV)---
        st.subheader("🏃 Dettagli Corsa")
        # Usa colonne per layout più compatto
        col1, col2 = st.columns(2)
        with col1:
            tipo_corsa = st.text_input("Tipo di Corsa:", "Corsa Standard")
            distanza_km = st.number_input("Distanza (km):", min_value=0.0, value=5.0, step=0.1, format="%.2f")
            battiti_medi = st.number_input("Battiti Medi (BPM, 0 se non misurati):", min_value=0, max_value=250, value=0, step=1) # Default 0
        with col2:
            tempo_min = st.number_input("Tempo (minuti totali):", min_value=0.0, value=30.0, step=0.5, format="%.1f")
            sforzo_corsa = st.slider("Sforzo percepito (RPE 1-10):", 1, 10, 6) # Default RPE 6

        note_corsa = st.text_area("Note sulla corsa (materiale, sensazioni, meteo, ecc.):")

        # Calcola e mostra passo medio al volo per feedback
        passo_medio_display = 0.0
        if distanza_km > 0 and tempo_min > 0:
            passo_medio_display = tempo_min / distanza_km
            minuti = int(passo_medio_display)
            secondi = int((passo_medio_display - minuti) * 60)
            st.metric("Passo Medio Calcolato", f"{minuti:02d}:{secondi:02d} min/km")
        else:
            st.caption("Inserisci distanza e tempo (>0) per vedere il passo medio calcolato.")

        if st.button("✅ Registra Corsa", type="primary"):
            if distanza_km <= 0 or tempo_min <= 0:
                st.error("Errore: Inserisci valori validi per Distanza (>0) e Tempo (>0).")
            else:
                passo_medio_calc = tempo_min / distanza_km # Ricalcola per salvare
                new_run_data = {
                    'Data': data_allenamento,
                    'Tipo Corsa': tipo_corsa.strip() if tipo_corsa else "Non specificato", # Rimuovi spazi e metti default
                    'Distanza (km)': distanza_km,
                    'Tempo (min)': tempo_min,
                    'Passo Medio (min/km)': round(passo_medio_calc, 3), # Arrotonda per salvataggio
                    'Battiti Medi (BPM)': battiti_medi if battiti_medi > 0 else np.nan, # Salva NaN se 0 o non inserito
                    'Sforzo': sforzo_corsa,
                    'Note': note_corsa.strip() # Rimuovi spazi dalle note
                }
                # Aggiungi al DataFrame della corsa e salva su CSV
                # Usa la copia _df_runs per aggiungere la nuova riga
                updated_df_runs = pd.concat([_df_runs, pd.DataFrame([new_run_data])], ignore_index=True)
                save_running_data(updated_df_runs, RUNNING_HISTORY_FILE)
                st.success(f"Corsa registrata ({distanza_km:.2f} km in {tempo_min:.1f} min)!")

                # Aggiorna la copia cache in memoria dopo il salvataggio
                _df_runs = updated_df_runs.copy()
                # Opzionale: st.rerun() per pulire i campi, ma può essere fastidioso

    elif not is_running_day and esercizi: # Se è un giorno di pesi e ci sono esercizi definiti
        # --- Input per i PESI (salva su Excel) ---
        st.subheader("🏋️ Dettagli Serie Pesi")

        esercizio_sel = st.selectbox("Seleziona Esercizio:", esercizi)

        # Layout in colonne per compattezza
        col_w1, col_w2, col_w3 = st.columns(3)
        with col_w1:
             peso_kg = st.number_input("Peso (kg):", min_value=0.0, value=20.0, step=0.5, format="%.1f")
        with col_w2:
             ripetizioni = st.number_input("Ripetizioni:", min_value=1, value=10, step=1)
        with col_w3:
             sforzo_peso = st.slider("Sforzo (RPE 1-10):", 1, 10, 7) # Default RPE 7

        if st.button("✅ Registra Serie Pesi", type="primary"):
            # Calcola performance per feedback e controllo PR
            performance_calc = peso_kg * ripetizioni * sforzo_peso

            # Controllo PR (usa _df_weights, che è la copia dei dati caricati)
            # Filtra per l'esercizio selezionato
            prev_perf = _df_weights[_df_weights['Esercizio'] == esercizio_sel]['Performance']
            is_pr = prev_perf.empty or performance_calc > prev_perf.max()

            new_weight_data = {
                'Data': data_allenamento,
                'Esercizio': esercizio_sel,
                'Peso': peso_kg,
                'Ripetizioni': ripetizioni,
                'Sforzo': sforzo_peso,
                'Performance': performance_calc # Calcolato per feedback/PR, verrà rimosso prima di salvare
            }
            # Aggiungi al DataFrame dei pesi (usando la copia _df_weights) e salva su Excel
            updated_df_weights = pd.concat([_df_weights, pd.DataFrame([new_weight_data])], ignore_index=True)

            save_weights_data(updated_df_weights, EXCEL_FILE_PATH) # La funzione rimuove 'Performance'
            st.success(f"Registrato: {esercizio_sel} ({peso_kg}kg x {ripetizioni} reps) - Performance: {performance_calc:.0f}")
            if is_pr:
                 st.balloons()
                 st.success("🎉 Nuovo Record Personale di Performance per questo esercizio!")

            # Aggiorna la copia cache in memoria
            _df_weights = updated_df_weights.copy()
            # Rimuovi la colonna Performance dalla copia cache se non serve più dopo il salvataggio
            if 'Performance' in _df_weights.columns:
                 _df_weights = _df_weights.drop(columns=['Performance'])
             # Ricarica la colonna performance per i grafici successivi
            _df_weights['Performance'] = _df_weights['Peso'] * _df_weights['Ripetizioni'] * _df_weights['Sforzo']


            # Opzionale: st.rerun() per pulire i campi

    elif not is_running_day and not esercizi:
         st.info("Nessun esercizio definito nel programma di questo giorno per la registrazione.")
    # else: gestito all'inizio della sezione


# --- Sezione 4: Grafici di Trend (Condizionale Pesi/Corsa) ---
st.header("📊 Trend Storici")

# Se non ci sono dati in nessuno dei due storici, non mostrare nulla
if _df_weights.empty and _df_runs.empty:
    st.info("Nessun dato storico trovato. Inizia a registrare i tuoi allenamenti!")
else:
    # Opzioni per il radio button, mostra solo i tipi di dati disponibili
    trend_options = []
    if not _df_weights.empty: trend_options.append("Sollevamento Pesi")
    if not _df_runs.empty: trend_options.append("Corsa")

    if not trend_options: # Dovrebbe essere coperto dal check precedente, ma per sicurezza
         st.info("Nessun dato storico disponibile.")
    else:
        # Se c'è solo un tipo di dato, non mostrare il radio button
        if len(trend_options) == 1:
            trend_type = trend_options[0]
        else:
             trend_type = st.radio("Visualizza trend per:", trend_options, horizontal=True, key='trend_radio')

        # Grafici per Sollevamento Pesi
        if trend_type == "Sollevamento Pesi":
            st.subheader("📈 Trend Sollevamento Pesi")
            exercises_with_data = sorted(_df_weights['Esercizio'].dropna().unique())
            if exercises_with_data:
                sel_ex_weights = st.selectbox("Seleziona Esercizio:", exercises_with_data, key='gx_weights')
                # Filtra i dati per l'esercizio scelto
                sub_df_weights = _df_weights[_df_weights['Esercizio'] == sel_ex_weights].sort_values('Data')

                if not sub_df_weights.empty:
                    metrics_weights = {'Peso Sollevato (kg)':'Peso','Volume (Peso*Reps*Sforzo)':'Performance','Ripetizioni':'Ripetizioni','Sforzo (RPE)':'Sforzo'}
                    metric_weights_sel = st.selectbox("Scegli la Metrica da visualizzare:", list(metrics_weights.keys()), key='gm_weights')
                    metric_col_name_w = metrics_weights[metric_weights_sel] # Nome colonna nel DataFrame

                    # Crea il grafico
                    fig_w, ax_w = plt.subplots(figsize=(10, 5)) # Grafico più largo
                    ax_w.plot(pd.to_datetime(sub_df_weights['Data']), sub_df_weights[metric_col_name_w], marker='o', linestyle='-', color='tab:blue')
                    ax_w.set_xlabel("Data", fontsize=10)
                    ax_w.set_ylabel(metric_weights_sel, fontsize=10)
                    ax_w.set_title(f"Andamento {metric_weights_sel} - {sel_ex_weights}", fontsize=12)
                    ax_w.tick_params(axis='x', rotation=45, labelsize=8)
                    ax_w.tick_params(axis='y', labelsize=8)
                    ax_w.grid(True, linestyle='--', alpha=0.6) # Griglia più leggera
                    fig_w.tight_layout() # Migliora layout
                    st.pyplot(fig_w)
                else:
                    st.info(f"Nessun dato storico trovato per l'esercizio '{sel_ex_weights}'.")
            else:
                st.info("Non ci sono ancora dati registrati per il sollevamento pesi.")

        # Grafici per Corsa
        elif trend_type == "Corsa":
            st.subheader("📈 Trend Corsa")
            if not _df_runs.empty:
                 # Filtro opzionale per tipo di corsa
                 run_types_available = ["Tutte"] + sorted(_df_runs['Tipo Corsa'].dropna().unique())
                 sel_run_type = st.selectbox("Filtra per Tipo di Corsa (opzionale):", run_types_available, key='run_type_filter')

                 # Filtra il dataframe se un tipo specifico è selezionato
                 sub_df_runs = _df_runs.copy()
                 if sel_run_type != "Tutte":
                     sub_df_runs = sub_df_runs[sub_df_runs['Tipo Corsa'] == sel_run_type]

                 if not sub_df_runs.empty:
                    metrics_runs = {
                        'Distanza (km)': 'Distanza (km)',
                        'Tempo (min)': 'Tempo (min)',
                        'Passo Medio (min/km)': 'Passo Medio (min/km)',
                        'Battiti Medi (BPM)': 'Battiti Medi (BPM)',
                        'Sforzo (RPE)': 'Sforzo'
                    }
                    metric_runs_sel = st.selectbox("Scegli la Metrica da visualizzare:", list(metrics_runs.keys()), key='gm_runs')
                    metric_col_name_r = metrics_runs[metric_runs_sel]

                    # Prepara i dati per il plot (rimuovi NaN e zeri non significativi per alcune metriche)
                    plot_data_r = sub_df_runs[['Data', metric_col_name_r]].dropna(subset=[metric_col_name_r]).sort_values('Data')
                    # Rimuovi zeri per Passo e BPM dove non hanno senso
                    if metric_col_name_r in ['Passo Medio (min/km)', 'Battiti Medi (BPM)']:
                        plot_data_r = plot_data_r[plot_data_r[metric_col_name_r] > 0]

                    if not plot_data_r.empty:
                         fig_r, ax_r = plt.subplots(figsize=(10, 5))
                         ax_r.plot(pd.to_datetime(plot_data_r['Data']), plot_data_r[metric_col_name_r], marker='o', linestyle='-', color='tab:green')
                         ax_r.set_xlabel("Data", fontsize=10)
                         ax_r.set_ylabel(metric_runs_sel, fontsize=10)
                         # Titolo dinamico basato sul filtro
                         title_r = f"Andamento {metric_runs_sel}"
                         if sel_run_type != "Tutte":
                             title_r += f" - Tipo: {sel_run_type}"
                         ax_r.set_title(title_r, fontsize=12)
                         ax_r.tick_params(axis='x', rotation=45, labelsize=8)
                         ax_r.tick_params(axis='y', labelsize=8)
                         ax_r.grid(True, linestyle='--', alpha=0.6)

                         # Inverti asse Y per il passo (valori più bassi sono migliori)
                         if metric_col_name_r == 'Passo Medio (min/km)':
                             # Solo se ci sono dati validi da plottare
                             if not plot_data_r.empty and plot_data_r[metric_col_name_r].max() > 0:
                                  ax_r.invert_yaxis()

                         fig_r.tight_layout()
                         st.pyplot(fig_r)
                    else:
                         st.info(f"Nessun dato valido (non nullo o > 0 dove richiesto) per la metrica '{metric_runs_sel}' con i filtri applicati.")

                 else:
                     st.info(f"Nessun dato storico trovato per il tipo di corsa '{sel_run_type}'.")
            else:
                 st.info("Non ci sono ancora dati registrati per la corsa.")


# --- Sezione 5: Eliminazione Record (Condizionale Pesi/Corsa) ---
st.header("🗑️ Gestione Record")

# Se non ci sono dati, non mostrare la sezione
if _df_weights.empty and _df_runs.empty:
    st.info("Nessun record da gestire.")
else:
    # Opzioni per il radio button di eliminazione
    delete_options = []
    if not _df_weights.empty: delete_options.append("Sollevamento Pesi")
    if not _df_runs.empty: delete_options.append("Corsa")

    if not delete_options:
         st.info("Nessun record disponibile per l'eliminazione.")
    else:
        # Se c'è solo un tipo di dato, preselezionalo
        if len(delete_options) == 1:
            delete_type = delete_options[0]
            st.subheader(f"Elimina Record di {delete_type}")
        else:
             delete_type = st.radio("Seleziona il tipo di record da gestire:", delete_options, horizontal=True, key="delete_type_radio")
             st.subheader(f"Elimina Record di {delete_type}")

        # Interfaccia per eliminazione Pesi
        if delete_type == "Sollevamento Pesi":
            st.caption("Seleziona uno o più record di sollevamento pesi da eliminare permanentemente.")
            # Aggiungi un ID univoco temporaneo basato sull'indice del DataFrame caricato (_df_weights)
            temp_weights_del = _df_weights.reset_index().rename(columns={'index':'ID_Record'})
            # Crea una descrizione leggibile per ogni record
            temp_weights_del['Descrizione'] = temp_weights_del.apply(
                lambda r: f"ID:{r.ID_Record} | {r.Data.strftime('%Y-%m-%d')} | {r.Esercizio} | {r.Peso}kg x {r.Ripetizioni} reps | RPE:{r.Sforzo}",
                axis=1
            )
            # Mostra gli ultimi N record per evitare liste troppo lunghe nel multiselect
            num_to_show_del_w = st.slider("Quanti record recenti mostrare per la selezione (Pesi)?", min_value=5, max_value=max(20, len(temp_weights_del)), value=min(20, max(5, len(temp_weights_del))), key="del_slider_w")
            # Crea la lista di opzioni per multiselect (dal più recente al meno recente)
            options_w_del = temp_weights_del.sort_values('Data', ascending=False).head(num_to_show_del_w)['Descrizione'].tolist()

            if not options_w_del:
                 st.info("Nessun record di sollevamento pesi disponibile per l'eliminazione.")
            else:
                records_to_delete_w_desc = st.multiselect(
                    "Seleziona i record da eliminare:",
                    options_w_del,
                    key="delete_multi_w"
                )

                if st.button("❌ Elimina Selezionati (Pesi)", type="secondary", key="delete_button_w"):
                    if records_to_delete_w_desc:
                        # Estrai gli ID originali (indici) dalle stringhe selezionate
                        ids_to_delete_w = [int(desc.split('|')[0].split(':')[1]) for desc in records_to_delete_w_desc]

                        # Rimuovi le righe dal DataFrame usando gli indici originali
                        df_weights_after_delete = _df_weights.drop(index=ids_to_delete_w).reset_index(drop=True)

                        # Salva il DataFrame aggiornato nell'Excel
                        save_weights_data(df_weights_after_delete, EXCEL_FILE_PATH)
                        st.success(f"{len(ids_to_delete_w)} record di sollevamento pesi eliminati con successo!")

                        # Ricarica i dati per aggiornare la vista e forza rerun
                        _df_weights = load_weights_data(EXCEL_FILE_PATH) # Ricarica da Excel
                        st.rerun()
                    else:
                        st.warning("Nessun record selezionato per l'eliminazione.")

        # Interfaccia per eliminazione Corsa
        elif delete_type == "Corsa":
            st.caption("Seleziona uno o più record di corsa da eliminare permanentemente.")
            # Aggiungi ID temporaneo
            temp_runs_del = _df_runs.reset_index().rename(columns={'index':'ID_Record'})
            # Crea descrizione
            temp_runs_del['Descrizione'] = temp_runs_del.apply(
                 lambda r: f"ID:{r.ID_Record} | {r.Data.strftime('%Y-%m-%d')} | {r['Tipo Corsa']} | {r['Distanza (km)']:.1f}km / {r['Tempo (min)']:.1f}min | Passo:{r['Passo Medio (min/km)']:.2f} | RPE:{r.Sforzo}",
                axis=1
            )
            # Slider per numero record
            num_to_show_del_r = st.slider("Quanti record recenti mostrare per la selezione (Corsa)?", min_value=5, max_value=max(20, len(temp_runs_del)), value=min(20, max(5, len(temp_runs_del))), key="del_slider_r")
            # Opzioni multiselect
            options_r_del = temp_runs_del.sort_values('Data', ascending=False).head(num_to_show_del_r)['Descrizione'].tolist()

            if not options_r_del:
                 st.info("Nessun record di corsa disponibile per l'eliminazione.")
            else:
                records_to_delete_r_desc = st.multiselect(
                    "Seleziona i record da eliminare:",
                    options_r_del,
                    key="delete_multi_r"
                )

                if st.button("❌ Elimina Selezionati (Corsa)", type="secondary", key="delete_button_r"):
                    if records_to_delete_r_desc:
                        ids_to_delete_r = [int(desc.split('|')[0].split(':')[1]) for desc in records_to_delete_r_desc]

                        df_runs_after_delete = _df_runs.drop(index=ids_to_delete_r).reset_index(drop=True)

                        save_running_data(df_runs_after_delete, RUNNING_HISTORY_FILE) # Salva su CSV
                        st.success(f"{len(ids_to_delete_r)} record di corsa eliminati con successo!")

                        _df_runs = load_running_data(RUNNING_HISTORY_FILE) # Ricarica da CSV
                        st.rerun()
                    else:
                        st.warning("Nessun record selezionato per l'eliminazione.")

# --- Footer o altre informazioni ---
st.divider()
st.caption(f"Applicazione di monitoraggio allenamenti - Dati aggiornati al: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
