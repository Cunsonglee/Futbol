import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import urllib.parse
import pytz 

# ================= 1. CONFIGURACIÓN =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="centered")

# --- IMPORTANTE: Reemplaza con tu URL real ---
MAIN_URL = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"

# Usamos la forma que te funcionó
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(worksheet):
    try:
        # ttl=0 para asegurar datos en tiempo real en votos y registros
        return conn.read(spreadsheet=MAIN_URL, worksheet=worksheet, ttl=0).dropna(how="all")
    except:
        return pd.DataFrame()

def save_data(worksheet, df):
    try:
        conn.create(spreadsheet=MAIN_URL, worksheet=worksheet, data=df)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Error al guardar: {e}")

def get_next_saturdays(n=4):
    saturdays = []
    d = datetime.now()
    while len(saturdays) < n:
        d += timedelta(days=1)
        if d.weekday() == 5: # 5 = Sábado
            saturdays.append(d.strftime('%Y-%m-%d'))
    return saturdays

# ================= 2. INTERFAZ =================
st.title("⚽ Gestión del Club")

tab_inicio, tab_votar, tab_publicar, tab_campos, tab_miembros, tab_historial = st.tabs([
    "🏠 Inicio", "🗳️ Votar", "📅 Publicar", "🥅 Campos", "🤼‍♂️ Miembros", "⏳ Historial"
])

# --- TAB 1: INICIO ---
with tab_inicio:
    st.subheader("Partidos Programados")
    df_e = load_data("Eventos")
    df_c = load_data("Campos")
    df_m = load_data("Miembros")
    
    if not df_e.empty:
        tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        # Filtramos partidos que no han pasado
        activos = df_e[df_e['datetime'] >= now].sort_values("datetime")
        
        if not activos.empty:
            for idx, event in activos.iterrows():
                with st.expander(f"📌 {event['datetime']} @ {event['venue']}", expanded=True):
                    v_match = df_c[df_c['name'] == event['venue']] if not df_c.empty else pd.DataFrame()
                    url_map = v_match.iloc[0]['map_url'] if not v_match.empty else "#"
                    
                    st.write(f"📍 **Lugar:** [{event['venue']}]({url_map})")
                    
                    players = [p.strip() for p in str(event['players']).split(",") if p.strip() and str(event['players']) != "nan"]
                    st.write(f"🏃 **Inscritos ({len(players)}):** {', '.join(players)}")
                    
                    non_signed = [m for m in df_m['name'].tolist() if m not in players] if not df_m.empty else []
                    
                    # Formulario de inscripción para evitar refrescos molestos
                    with st.container():
                        c_sel, c_btn = st.columns([3, 1])
                        p_name = c_sel.selectbox("Tu nombre:", ["-- Seleccionar --"] + non_signed, key=f"ins_{idx}")
                        if c_btn.button("Inscribirme", key=f"btn_{idx}"):
                            if p_name != "-- Seleccionar --":
                                players.append(p_name)
                                df_e.at[idx, 'players'] = ",".join(players)
                                save_data("Eventos", df_e)
                                st.rerun()
        else:
            st.info("No hay partidos confirmados. ¡Ve a la pestaña de Votar!")

# --- TAB 2: VOTAR ---
with tab_votar:
    st.subheader("Votación para el próximo Sábado")
    df_v = load_data("Votos")
    df_m = load_data("Miembros")
    
    sabs = get_next_saturdays()
    
    with st.form("form_votos", clear_on_submit=False):
        v_fecha = st.selectbox("Día del Sábado:", sabs)
        v_turno = st.radio("Turno:", ["Mañana", "Tarde"])
        lista_m = ["-- Seleccionar --"] + (df_m['name'].tolist() if not df_m.empty else [])
        v_user = st.selectbox("¿Quién eres?", lista_m)
        
        if st.form_submit_button("Enviar Voto"):
            if v_user != "-- Seleccionar --":
                exists = df_v[(df_v['fecha'] == v_fecha) & (df_v['turno'] == v_turno) & (df_v['usuario'] == v_user)]
                if exists.empty:
                    new_v = pd.DataFrame([{"fecha": v_fecha, "turno": v_turno, "usuario": v_user}])
                    df_v = pd.concat([df_v, new_v], ignore_index=True)
                    save_data("Votos", df_v)
                    st.success(f"¡Voto registrado para {v_user}!")
                    # No hacemos rerun aquí para que el usuario vea el mensaje de éxito
                else:
                    st.warning("Ya has votado por este turno.")
            else:
                st.error("Por favor, selecciona tu nombre.")

    st.divider()
    st.write("📊 **Progreso de votaciones:**")
    df_v_view = load_data("Votos") # Recargar para ver progreso
    if not df_v_view.empty:
        res = df_v_view.groupby(['fecha', 'turno']).size().reset_index(name='count')
        for _, r in res.iterrows():
            color = "green" if r['count'] >= 10 else "orange"
            st.write(f"📅 {r['fecha']} ({r['turno']}): **{r['count']}/10 votos**")
            st.progress(min(r['count'] / 10, 1.0))

# --- TAB 3: PUBLICAR ---
with tab_publicar:
    st.subheader("Publicar Partido (Solo >= 10 votos)")
    df_v = load_data("Votos")
    df_c = load_data("Campos")
    
    if not df_v.empty:
        summary = df_v.groupby(['fecha', 'turno']).size().reset_index(name='count')
        ready = summary[summary['count'] >= 10]
        
        if ready.empty:
            st.warning("Aún no hay turnos con 10 personas.")
        else:
            with st.form("form_pub"):
                labels = [f"{r['fecha']} ({r['turno']})" for _, r in ready.iterrows()]
                selected_v = st.selectbox("Turnos listos:", labels)
                f_time = st.time_input("Hora de encuentro:")
                f_venue = st.selectbox("Seleccionar Campo:", df_c['name'].tolist() if not df_c.empty else [])
                
                if st.form_submit_button("🚀 Publicar Partido"):
                    f_date = selected_v.split(" (")[0]
                    dt_str = f"{f_date} {f_time.strftime('%H:%M')}"
                    df_e = load_data("Eventos")
                    new_match = pd.DataFrame([{"datetime": dt_str, "venue": f_venue, "players": ""}])
                    df_e = pd.concat([df_e, new_match], ignore_index=True)
                    save_data("Eventos", df_e)
                    st.success("¡Partido publicado en Inicio!")
                    st.rerun()

# --- TAB 4: CAMPOS ---
with tab_campos:
    st.subheader("Gestión de Campos")
    df_c = load_data("Campos")
    with st.form("add_campo"):
        u = st.text_input("URL Google Maps:")
        if st.form_submit_button("Guardar Campo"):
            try:
                res = requests.get(u, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                name = BeautifulSoup(res.text, 'html.parser').title.string.replace(" - Google Maps", "").strip()
                df_c = pd.concat([df_c, pd.DataFrame([{"name": name, "map_url": u}])], ignore_index=True)
                save_data("Campos", df_c)
                st.rerun()
            except: st.error("Error al obtener el nombre.")
    for i, r in df_c.iterrows():
        c1, c2 = st.columns([4,1])
        c1.markdown(f"🏟️ [{r['name']}]({r['map_url']})")
        if c2.button("Eliminar", key=f"dc_{i}"):
            df_c = df_c.drop(i)
            save_data("Campos", df_c)
            st.rerun()

# --- TAB 5: MIEMBROS ---
with tab_miembros:
    st.subheader("Gestión de Miembros")
    df_m = load_data("Miembros")
    with st.form("add_m"):
        n = st.text_input("Nombre:")
        if st.form_submit_button("Añadir"):
            df_m = pd.concat([df_m, pd.DataFrame([{"name": n}])], ignore_index=True)
            save_data("Miembros", df_m)
            st.rerun()
    for i, r in df_m.iterrows():
        c1, c2 = st.columns([4,1])
        c1.write(f"👤 {r['name']}")
        if c2.button("Eliminar", key=f"dm_{i}"):
            df_m = df_m.drop(i)
            save_data("Miembros", df_m)
            st.rerun()

# --- TAB 6: HISTORIAL ---
with tab_historial:
    st.subheader("Partidos Pasados")
    df_e = load_data("Eventos")
    if not df_e.empty:
        tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        pasados = df_e[df_e['datetime'] < now].sort_values("datetime", ascending=False)
        for i, row in pasados.iterrows():
            with st.expander(f"📅 {row['datetime']} - {row['venue']}"):
                p_list = [p.strip() for p in str(row['players']).split(",") if p.strip() and str(row['players']) != "nan"]
                st.write(f"**Participantes ({len(p_list)}):** {', '.join(p_list)}")
