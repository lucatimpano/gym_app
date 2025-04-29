import pandas as pd
import datetime
import streamlit as st
import matplotlib.pyplot as plt
import json
from pathlib import Path

# ————————————————————————————————————————————————————————————————
# CONFIGURAZIONE STREAMLIT
# ————————————————————————————————————————————————————————————————
st.set_page_config(page_title="Scheda Ipertrofia", layout="centered")
st.markdown("""
<style>
  .block-container { max-width: 800px; padding: 1rem; }
</style>
""", unsafe_allow_html=True)

# Applichiamo un tema matplotlib più gradevole
plt.style.use('ggplot')

file_path = '/home/luca/Scrivania/Personal/Scheda_Ipertrofia_Corsa_Excel.xlsx'
NOTE_FILE = Path('group_notes.json')

# ————————————————————————————————————————————————————————————————
# MAPPATURA FOGLI → GRUPPI
# ————————————————————————————————————————————————————————————————
GROUPS = {
    "Day 1 - Lower A": "Lower 1",
    "Day 2 - Upper A": "Upper 1",
    "Day 3 - Lower B": "Lower 2",
    "Day 4 - Upper B": "Upper 2",
    "Corsa - Venerdì":  "Corsa"
}

# ————————————————————————————————————————————————————————————————
# NOTE CONDIVISE
# ————————————————————————————————————————————————————————————————
def load_group_notes():
    if NOTE_FILE.exists():
        return json.loads(NOTE_FILE.read_text(encoding='utf-8'))
    return {g: "" for g in set(GROUPS.values())}

def save_group_note(group, text):
    notes = load_group_notes()
    notes[group] = text
    NOTE_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding='utf-8')

# ————————————————————————————————————————————————————————————————
# CARICA / SALVA STORICO
# ————————————————————————————————————————————————————————————————
def load_data():
    try:
        df = pd.read_excel(file_path, sheet_name='Peso Storico')
        for c in ['Data','Esercizio','Peso','Ripetizioni','Sforzo']:
            if c not in df.columns:
                df[c] = '' if c in ['Data','Esercizio'] else 0
        df['Data'] = pd.to_datetime(df['Data']).dt.date
    except:
        df = pd.DataFrame(columns=['Data','Esercizio','Peso','Ripetizioni','Sforzo'])
    # Metrica performance: session RPE = peso × ripetizioni × sforzo
    df['Performance'] = df['Peso'] * df['Ripetizioni'] * df['Sforzo']
    return df

def save_data(df):
    to_save = df.drop(columns=['Performance'], errors='ignore')
    with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as w:
        to_save.to_excel(w, sheet_name='Peso Storico', index=False)

# Caricamento dati e fogli programma
_df = load_data()
df = _df.copy()
try:
    xl = pd.ExcelFile(file_path)
    program_sheets = [s for s in xl.sheet_names if s != 'Peso Storico']
except:
    program_sheets = []

st.title("Scheda Interattiva: Monitor Allenamenti")

# ————————————————————————————————————————————————————————————————
# 1) Selezione giorno\# ————————————————————————————————————————————————————————————————
if program_sheets:
    sheet_sel = st.selectbox("Scegli giorno:", program_sheets)
    prog = pd.read_excel(file_path, sheet_name=sheet_sel)
    st.subheader(f"Programma: {sheet_sel}")
    st.table(prog[['Esercizio','Serie','Ripetizioni']])
    esercizi = prog['Esercizio'].dropna().unique().tolist()
else:
    st.warning("Nessun foglio trovato.")
    esercizi = []

# ————————————————————————————————————————————————————————————————
# 2) Note condivise\# ————————————————————————————————————————————————————————————————
grp = GROUPS.get(sheet_sel)
if grp:
    colors = {"Upper":"#e57373","Lower":"#81c784","Cardio":"#64b5f6","HITT":"#ffb74d","Corsa":"#ba68c8"}
    base = grp.split()[0]
    col  = colors.get(base, "#777")
    st.markdown(f"<span style='background:{col};color:#fff;padding:4px 8px;border-radius:4px'>{grp}</span>", unsafe_allow_html=True)
    notes = load_group_notes()
    text  = st.text_area(f"Nota per {grp}:", notes.get(grp, ""), height=120, key=grp)
    if st.button(f"💾 Salva nota {grp}", key=f"save_{grp}"):
        save_group_note(grp, text)
        st.success("Nota salvata!")
else:
    st.info("Seleziona un foglio valido per nota di gruppo.")

# ————————————————————————————————————————————————————————————————
# 3) Inserimento performance + record\# ————————————————————————————————————————————————————————————————
data_perf = st.date_input("Data:", datetime.date.today())
if esercizi:
    ex   = st.selectbox("Esercizio:", esercizi)
    peso = st.number_input("Peso (kg):", 0.0, 500.0, 20.0, 0.5)
    reps = st.number_input("Ripetizioni:", 1, 100, 10, 1)
    sforz= st.slider("Sforzo (1-10):", 1, 10, 5)
    if st.button("Registra"):
        perf = peso * reps * sforz
        prev = df[df['Esercizio']==ex]['Performance']
        is_pr= prev.empty or perf > prev.max()
        new = {'Data':data_perf,'Esercizio':ex,'Peso':peso,'Ripetizioni':reps,'Sforzo':sforz,'Performance':perf}
        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        save_data(df)
        st.success(f"Registrato: {ex} → Performance {perf:.0f}")
        if is_pr:
            st.balloons()
            st.success("🎉 Nuovo PR di Performance!")
else:
    st.info("Seleziona un foglio con esercizi.")

# ————————————————————————————————————————————————————————————————
# 4) Grafici di trend: Peso, Performance, Sforzo\# ————————————————————————————————————————————————————————————————
st.subheader("Trend per esercizio")
sel_ex = st.selectbox("Esercizio per grafici:", df['Esercizio'].dropna().unique(), key='gx')
metrics = {'Peso':'Peso','Performance':'Performance','Sforzo':'Sforzo'}
metric = st.selectbox("Metrica:", list(metrics.keys()), key='gm')
sub = df[df['Esercizio']==sel_ex]
fig, ax = plt.subplots()
ax.plot(pd.to_datetime(sub['Data']), sub[metrics[metric]], marker='o', linestyle='-')
ax.set(xlabel="Data", ylabel=metric, title=f"{metric} – {sel_ex}")
st.pyplot(fig)

# ————————————————————————————————————————————————————————————————
# 5) Eliminazione record errati\# ————————————————————————————————————————————————————————————————
st.subheader("Elimina record errati")
if not df.empty:
    temp = df.reset_index().rename(columns={'index':'ID'})
    temp['Descr'] = temp.apply(lambda r: f"{r.ID} | {r.Data} | {r.Esercizio} | {r.Peso}kg | {r.Ripetizioni} rep", axis=1)
    to_del = st.multiselect("Seleziona:", temp['Descr'])
    if st.button("Elimina"):
        ids = [int(x.split(' | ')[0]) for x in to_del]
        df = df.drop(ids).reset_index(drop=True)
        save_data(df)
        st.success("Record cancellati!")
