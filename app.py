import streamlit as st
import streamlit.components.v1 as components
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import urllib.parse
import pytz 

from googleapiclient.discovery import build
from google.oauth2 import service_account

# ================= 1. CONFIGURACIÓN BÁSICA =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="wide")

MAIN_URL = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet_data(worksheet_name, ttl=300):
    """Carga datos con TTL variable. Para votar usaremos 0 para que sea instantáneo"""
    try:
        # Forzamos la lectura fresca si ttl es 0
        return conn.read(spreadsheet=MAIN_URL, worksheet=worksheet_name, ttl=ttl).dropna(how="all")
    except Exception as e:
        # Si la pestaña no existe aún, devolvemos un DataFrame vacío con las columnas necesarias
        if worksheet_name == "Votaciones":
            return pd.DataFrame(columns=['Fecha', 'Jugadores'])
        st.error(f"Error al cargar {worksheet_name}: {e}")
        return pd.DataFrame()

def save_sheet_data(worksheet_name, df):
    """Guarda datos y fuerza la limpieza total de la memoria de Streamlit"""
    try:
        # Aseguramos que los nombres de las columnas sean limpios
        df.columns = [str(c).strip() for c in df.columns]
        # Limpiar caché antes de guardar
        st.cache_data.clear()
        conn.update(worksheet=worksheet_name, data=df)
        st.cache_data.clear()
    except Exception as e:
        try:
            conn.create(spreadsheet=MAIN_URL, worksheet=worksheet_name, data=df)
            st.cache_data.clear()
        except Exception as e2:
            st.error(f"Error al guardar: {e2}")

# ================= 2. FUNCIONES AUXILIARES (CALENDARIO) =================
def get_calendar_slots_grouped():
    try:
        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        creds_info = st.secrets["connections"]["gsheets"]
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        calendar_id = '07854ef03649a28b9507946bb4f7af183d0cf1f49535580916c12c2a4fd1933c@group.calendar.google.com'
        
        tz = pytz.timezone('Europe/Madrid')
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = today - timedelta(days=today.weekday()) 
        time_max = start_of_week + timedelta(weeks=6)
        
        events_result = service.events().list(
            calendarId=calendar_id, 
            timeMin=start_of_week.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True, 
            orderBy='startTime').execute()
            
        events = events_result.get('items', [])
        slots_by_date = {}
        
        for event in events:
            start_info = event.get('start', {})
            end_info = event.get('end', {})
            if 'dateTime' in start_info and 'dateTime' in end_info:
                start_dt = datetime.fromisoformat(start_info['dateTime']).astimezone(tz)
                end_dt = datetime.fromisoformat(end_info['dateTime']).astimezone(tz)
                date_str = start_dt.strftime('%Y-%m-%d')
                s_t, e_t = start_dt.strftime('%H:%M'), end_dt.strftime('%H:%M')
                if s_t == "07:00" and e_t == "13:00": franja = "Mañana"
                elif (s_t == "17:00" and e_t == "23:30") or (s_t == "13:00" and e_t == "23:30"): franja = "Tarde"
                else: franja = f"{s_t}-{e_t}"
            else:
                date_str = start_info.get('date', '')
                franja = "Todo el día"
            if date_str:
                if date_str not in slots_by_date: slots_by_date[date_str] = []
                slots_by_date[date_str].append(franja)
        return slots_by_date, start_of_week
    except Exception as e:
        st.error(f"Error Calendario: {e}")
        return {}, datetime.now()

# ================= 3. INTERFAZ =================
st.title("⚽ Gestión del Club")

tab_inicio, tab_votar, tab_calendario, tab_campos, tab_miembros, tab_historial = st.tabs([
    "🏠 Inicio", "🗳️ Votar", "📅 Calendario", "🥅 Campos", "🤼‍♂️ Miembros", "⏳ Historial"
])

# --- TAB: 🏠 Inicio ---
with tab_inicio:
    st.subheader("Próximo Partido Confirmado")
    df_e = load_sheet_data("Eventos")
    df_m = load_sheet_data("Miembros")
    df_c = load_sheet_data("Campos")
    if not df_e.empty and 'datetime' in df_e.columns:
        tz = pytz.timezone('Europe/Madrid') 
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        future_events = df_e[df_e['datetime'].astype(str) >= now].sort_values("datetime")
        if not future_events.empty:
            event = future_events.iloc[0]
            st.info(f"**⏰ Fecha:** {event['datetime']}\n\n**🏟️ Campo:** {event['venue']}")
            players = [p.strip() for p in str(event.get('players', "")).split(",") if p.strip() and str(event.get('players', "")) != "nan"]
            st.write(f"🏃‍♂️ **Inscritos ({len(players)}):** {', '.join(players)}")
        else: st.info("No hay partidos próximos.")

# --- TAB: 🗳️ Votar (REPARADO) ---
with tab_votar:
    st.subheader("Inscribirse y Organizar Partidos")
    
    # 🔴 IMPORTANTE: ttl=0 para que siempre lea el dato real sin esperar 5 min
    df_v = load_sheet_data("Votaciones", ttl=0)
    if df_v.empty:
        df_v = pd.DataFrame(columns=['Fecha', 'Jugadores'])
    df_v['Fecha'] = df_v['Fecha'].astype(str).str.strip()
    
    df_m = load_sheet_data("Miembros")
    all_m = sorted(df_m['name'].tolist()) if not df_m.empty else []

    # 1. Calendario de Malla
    st.write("### 1. Seleccionar Fechas")
    slots_by_date, start_of_week = get_calendar_slots_grouped()
    selected_slots = []
    
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    cols_h = st.columns(7)
    for i, d in enumerate(dias): cols_h[i].markdown(f"**{d}**")
    
    curr = start_of_week
    for w in range(6):
        cols = st.columns(7)
        for i in range(7):
            d_str = curr.strftime('%Y-%m-%d')
            with cols[i]:
                st.caption(curr.strftime('%d/%m'))
                if d_str in slots_by_date:
                    for f in slots_by_date[d_str]:
                        s_val = f"{d_str} ({f})"
                        if st.checkbox(f, key=f"chk_{s_val}"): selected_slots.append(s_val)
                else: st.write("NON")
            curr += timedelta(days=1)
        st.write("---")

    st.write("**2. Seleccionar jugadores:**")
    sel_members = st.multiselect("Elige miembros:", all_m)
    
    # 🔴 BOTÓN CON LÓGICA DE ACTUALIZACIÓN FORZADA
    if st.button("Confirmar Jugadores", type="primary"):
        if not selected_slots: st.warning("Selecciona fecha")
        elif not sel_members: st.warning("Selecciona jugadores")
        else:
            with st.spinner("Guardando en Google Sheets..."):
                for s in selected_slots:
                    s = str(s).strip()
                    if s in df_v['Fecha'].values:
                        idx = df_v.index[df_v['Fecha'] == s][0]
                        existentes = [p.strip() for p in str(df_v.at[idx, 'Jugadores']).split(",") if p.strip() and str(df_v.at[idx, 'Jugadores']) != "nan"]
                        for m in sel_members:
                            if m not in existentes: existentes.append(m)
                        df_v.at[idx, 'Jugadores'] = ",".join(existentes)
                    else:
                        new_row = pd.DataFrame([{"Fecha": s, "Jugadores": ",".join(sel_members)}])
                        df_v = pd.concat([df_v, new_row], ignore_index=True)
                
                save_sheet_data("Votaciones", df_v)
                st.success("¡Guardado! Recargando datos...")
                st.rerun()

    st.divider()

    # 2. SECCIÓN DE ESTADO (Donde se ven los nombres)
    st.write("### 2. Estado de Votaciones")
    if not df_v.empty:
        for idx, row in df_v.iterrows():
            f, j_str = str(row['Fecha']), str(row['Jugadores'])
            jugadores = [p.strip() for p in j_str.split(",") if p.strip() and j_str != "nan"]
            
            # Solo mostrar si hay alguien apuntado
            if jugadores:
                with st.container():
                    c1, c2 = st.columns([3, 2])
                    c1.markdown(f"📅 **{f}**")
                    c2.write(f"🏃‍♂️ **{len(jugadores)} apuntados**")
                    st.write(f"👥 {', '.join(jugadores)}")
                    
                    # Lógica de Publicar (Mínimo 5)
                    if len(jugadores) >= 5:
                        with st.expander("🚀 Publicar Partido (Mínimo alcanzado)"):
                            df_c = load_sheet_data("Campos")
                            if not df_c.empty:
                                h = st.time_input("Hora", key=f"h_{f}")
                                campo = st.selectbox("Campo", df_c['name'].tolist(), key=f"c_{f}")
                                if st.button("Confirmar Partido", key=f"p_{f}"):
                                    dt = f"{f.split(' ')[0]} {h.strftime('%H:%M')}"
                                    df_e = load_sheet_data("Eventos")
                                    df_e = pd.concat([df_e, pd.DataFrame([{"datetime": dt, "venue": campo, "players": ",".join(jugadores)}])], ignore_index=True)
                                    save_sheet_data("Eventos", df_e)
                                    save_sheet_data("Votaciones", df_v.drop(idx))
                                    st.rerun()
                    else:
                        st.info(f"⏳ Faltan {5 - len(jugadores)} para abrir la publicación.")
                    st.write("---")
    else:
        st.info("No hay votos registrados.")

# (Resto de las pestañas: Calendario, Campos, Miembros, Historial se mantienen igual...)
with tab_calendario:
    components.iframe("https://calendar.google.com/calendar/embed?src=07854ef03649a28b9507946bb4f7af183d0cf1f49535580916c12c2a4fd1933c%40group.calendar.google.com&ctz=Europe%2FMadrid", height=600)

with tab_campos:
    st.subheader("Campos")
    df_c = load_sheet_data("Campos")
    with st.form("c_f"):
        u = st.text_input("Maps URL")
        if st.form_submit_button("Añadir"):
            name = fetch_venue_name(u)
            if name:
                save_sheet_data("Campos", pd.concat([df_c, pd.DataFrame([{"name": name, "map_url": u}])], ignore_index=True))
                st.rerun()

with tab_miembros:
    st.subheader("Miembros")
    df_m = load_sheet_data("Miembros")
    name = st.text_input("Nuevo miembro")
    if st.button("Añadir"):
        save_sheet_data("Miembros", pd.concat([df_m, pd.DataFrame([{"name": name}])], ignore_index=True))
        st.rerun()
    for i, r in df_m.iterrows(): st.write(f"👤 {r['name']}")

with tab_historial:
    st.subheader("Historial")
    df_e = load_sheet_data("Eventos")
    if not df_e.empty: st.write(df_e)
