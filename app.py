import streamlit as st
import streamlit.components.v1 as components
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import urllib.parse
import pytz 

# --- NUEVOS IMPORTS PARA GOOGLE CALENDAR API ---
from googleapiclient.discovery import build
from google.oauth2 import service_account

# ================= 1. CONFIGURACIÓN BÁSICA =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="centered")

MAIN_URL = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet_data(worksheet_name):
    try:
        return conn.read(spreadsheet=MAIN_URL, worksheet=worksheet_name, ttl=300).dropna(how="all")
    except Exception as e:
        st.error(f"Error al cargar la pestaña {worksheet_name}: {e}")
        return pd.DataFrame()

def save_sheet_data(worksheet_name, df):
    try:
        conn.create(spreadsheet=MAIN_URL, worksheet=worksheet_name, data=df)
        st.cache_data.clear() 
    except Exception as e:
        st.error(f"Error al guardar en {worksheet_name}: {e}")

# ================= 2. FUNCIONES AUXILIARES =================
def fetch_venue_name(url):
    try:
        if "/place/" in url:
            part = url.split("/place/")[1].split("/")[0]
            name = urllib.parse.unquote(part).replace("+", " ")
            if name and "@" not in name: return name
    except: pass
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        name = soup.title.string.replace(" - Google Maps", "").strip()
        return name if name and "Sign in" not in name else None
    except: return None

def formatear_precio(is_free, price, num, unit):
    if is_free or is_free == 1: return "Gratis"
    try:
        unit_str = "días" if (num > 1 and unit == "día") else (unit + "s" if num > 1 else unit)
        return f"{float(price):.2f} € / {int(num)} {unit_str}"
    except: return "No especificado"

# --- NUEVA FUNCIÓN: LEER GOOGLE CALENDAR (Próximas 6 semanas con franja horaria) ---
def get_upcoming_calendar_slots():
    """Lee los eventos de las próximas 6 semanas y muestra la hora de inicio y fin"""
    try:
        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        creds_info = st.secrets["connections"]["gsheets"]
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        
        service = build('calendar', 'v3', credentials=creds)
        
        calendar_id = '07854ef03649a28b9507946bb4f7af183d0cf1f49535580916c12c2a4fd1933c@group.calendar.google.com'
        
        # 设定时间范围：从"现在"到"未来6个星期 (6 weeks)"
        now = datetime.utcnow()
        time_max = now + timedelta(weeks=6)
        
        events_result = service.events().list(
            calendarId=calendar_id, 
            timeMin=now.isoformat() + 'Z',
            timeMax=time_max.isoformat() + 'Z',  # 限制在 6 个星期内
            singleEvents=True, 
            orderBy='startTime').execute()
            
        events = events_result.get('items', [])
        
        formatted_slots = []
        for event in events:
            start_info = event.get('start', {})
            end_info = event.get('end', {})
            summary = event.get('summary', 'Fútbol')
            
            # 判断是否有具体的时间段 (Franja horaria)
            if 'dateTime' in start_info and 'dateTime' in end_info:
                start_dt = datetime.fromisoformat(start_info['dateTime'].replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_info['dateTime'].replace('Z', '+00:00'))
                
                # 格式化输出为: 2026-05-17 (07:00 - 13:00) | Fútbol
                slot_name = f"{start_dt.strftime('%Y-%m-%d')} ({start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}) | {summary}"
            else:
                # Todo el día (全天活动)
                date_str = start_info.get('date', '')
                slot_name = f"{date_str} (Todo el día) | {summary}"
                
            formatted_slots.append(slot_name)
            
        return formatted_slots
    except Exception as e:
        st.error(f"No se pudo conectar al Calendario: {e}")
        return []

# ================= 3. DISEÑO DE INTERFAZ (TABS) =================
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
        df_e['datetime'] = df_e['datetime'].astype(str)
        future_events = df_e[df_e['datetime'] >= now].sort_values("datetime")

        if not future_events.empty:
            event = future_events.iloc[0]
            idx = future_events.index[0]

            v_info = df_c[df_c['name'] == event['venue']] if not df_c.empty else pd.DataFrame()
            precio, map_link = "No especificado", "#"
            if not v_info.empty:
                v = v_info.iloc[0]
                precio = formatear_precio(v.get('is_free',0), v.get('price',0), v.get('duration_num',1), v.get('duration_unit','hora'))
                map_link = v.get('map_url', '#')

            st.info(f"**⏰ Fecha y Hora:** {event['datetime']}\n\n**🏟️ Campo:** [{event['venue']}]({map_link})\n\n**💰 Precio:** {precio}")

            players_str = str(event.get('players', ""))
            current_players = [p.strip() for p in players_str.split(",") if p.strip() and players_str != "nan"]
            all_m = sorted(df_m['name'].tolist()) if not df_m.empty else []
            available = [m for m in all_m if m not in current_players]

            st.write("---")
            st.subheader("🙋‍♂️ Inscripción de Última Hora")
            sel = st.selectbox("Selecciona tu nombre para inscribirte:", ["-- Seleccionar --"] + available)
            if st.button("Confirmar Inscripción", type="primary"):
                if sel != "-- Seleccionar --":
                    current_players.append(sel)
                    df_e.at[idx, 'players'] = ",".join(current_players)
                    save_sheet_data("Eventos", df_e)
                    st.success(f"¡{sel} inscrito con éxito!")
                    st.rerun()

            st.divider()
            st.write(f"🏃‍♂️ **Inscritos actualmente: {len(current_players)}**")
            for p in current_players:
                c1, c2 = st.columns([5, 1])
                c1.write(f"✅ {p}")
                if c2.button("❌", key=f"del_{p}"):
                    current_players.remove(p)
                    df_e.at[idx, 'players'] = ",".join(current_players)
                    save_sheet_data("Eventos", df_e)
                    st.rerun()
        else:
            st.info("No hay partidos programados próximamente. ¡Ve a la pestaña 'Votar'!")

# --- TAB: 🗳️ Votar (NUEVO: Integrado con Google Calendar) ---
with tab_votar:
    st.subheader("Votar y Organizar Próximos Partidos")
    
    df_v = load_sheet_data("Votaciones")
    if df_v.empty or 'Fecha' not in df_v.columns:
        df_v = pd.DataFrame(columns=['Fecha', 'Jugadores'])

    df_m = load_sheet_data("Miembros")
    all_m = sorted(df_m['name'].tolist()) if not df_m.empty else []

    # 1. Proponer fecha desde Google Calendar
    with st.expander("➕ Abrir inscripción desde el Calendario"):
        with st.spinner("Sincronizando con Google Calendar..."):
            calendar_slots = get_upcoming_calendar_slots()
        
        if calendar_slots:
            selected_slot = st.selectbox("Selecciona un horario de tu calendario:", calendar_slots)
            if st.button("Abrir Votación para esta fecha"):
                if selected_slot not in df_v['Fecha'].astype(str).values:
                    nueva_fila = pd.DataFrame([{"Fecha": selected_slot, "Jugadores": ""}])
                    df_v = pd.concat([df_v, nueva_fila], ignore_index=True)
                    save_sheet_data("Votaciones", df_v)
                    st.success(f"Inscripción abierta para: {selected_slot}")
                    st.rerun()
                else:
                    st.warning("Esta fecha ya está abierta para votación.")
        else:
            st.write("No se encontraron eventos futuros en el calendario.")

    st.divider()

    # 2. Mostrar fechas abiertas para apuntarse
    if not df_v.empty:
        for idx, row in df_v.iterrows():
            fecha = str(row['Fecha'])
            jugadores_str = str(row['Jugadores'])
            jugadores_actuales = [p.strip() for p in jugadores_str.split(",") if p.strip() and jugadores_str != "nan"]
            
            st.write(f"### 📅 {fecha}")
            st.write(f"🏃‍♂️ **Apuntados ({len(jugadores_actuales)}):** {', '.join(jugadores_actuales) if jugadores_actuales else 'Nadie todavía'}")
            
            # Anotarse
            disponibles = [m for m in all_m if m not in jugadores_actuales]
            c1, c2 = st.columns([3, 1])
            with c1:
                sel = st.selectbox(f"Anotarme:", ["-- Seleccionar --"] + disponibles, key=f"sel_v_{fecha}")
            with c2:
                st.write("") 
                st.write("")
                if st.button("Anotarme", key=f"btn_v_{fecha}"):
                    if sel != "-- Seleccionar --":
                        jugadores_actuales.append(sel)
                        df_v.at[idx, 'Jugadores'] = ",".join(jugadores_actuales)
                        save_sheet_data("Votaciones", df_v)
                        st.success(f"¡{sel} anotado!")
                        st.rerun()
            
            # Publicar Oficialmente
            with st.expander(f"🚀 Publicar oficialmente este partido"):
                df_c = load_sheet_data("Campos")
                if not df_c.empty:
                    # Extraer solo la fecha principal (Ej: "2026-05-17") de la cadena del calendario
                    fecha_limpia = fecha.split(" ")[0] if " " in fecha else fecha
                    
                    hora_encuentro = st.time_input("Hora de encuentro confirmada", key=f"hora_{fecha}")
                    campo_seleccionado = st.selectbox("Seleccionar Campo", df_c['name'].tolist(), key=f"campo_{fecha}")
                    
                    if st.button("Confirmar Partido", key=f"pub_{fecha}", type="primary"):
                        dt_str = f"{fecha_limpia} {hora_encuentro.strftime('%H:%M')}"
                        df_e = load_sheet_data("Eventos")
                        
                        # Guardar en Eventos
                        new_row = pd.DataFrame([{"datetime": dt_str, "venue": campo_seleccionado, "players": ",".join(jugadores_actuales)}])
                        df_e = pd.concat([df_e, new_row], ignore_index=True)
                        save_sheet_data("Eventos", df_e)
                        
                        # Borrar de Votaciones
                        df_v = df_v.drop(idx).reset_index(drop=True)
                        save_sheet_data("Votaciones", df_v)
                        
                        st.success("¡Partido confirmado! Aparecerá en Inicio.")
                        st.rerun()
                else:
                    st.warning("No hay campos. Añade uno en la pestaña 'Campos'.")
            st.divider()
    else:
        st.info("No hay inscripciones abiertas. ¡Abre una desde el calendario arriba!")

# --- TAB: 📅 Calendario ---
with tab_calendario:
    st.subheader("Calendario General de Partidos")
    calendar_url = "https://calendar.google.com/calendar/embed?src=07854ef03649a28b9507946bb4f7af183d0cf1f49535580916c12c2a4fd1933c%40group.calendar.google.com&ctz=Europe%2FMadrid"
    components.iframe(calendar_url, height=600, scrolling=True)

# --- TAB: 🥅 Campos ---
with tab_campos:
    st.subheader("Gestión de Campos de Fútbol")
    df_c = load_sheet_data("Campos")
    with st.form("campo_form"):
        u = st.text_input("Enlace de Google Maps")
        free = st.checkbox("Campo gratuito")
        col1, col2, col3 = st.columns(3)
        price = col1.number_input("Precio", min_value=0.0)
        num = col2.number_input("Cantidad", min_value=1, value=1)
        unit = col3.selectbox("Unidad", ["hora", "día", "minuto"])
        if st.form_submit_button("Extraer Nombre y Guardar"):
            if u:
                with st.spinner("Buscando nombre del campo..."):
                    name = fetch_venue_name(u)
                    if name:
                        new_c = pd.DataFrame([{"name": name, "map_url": u, "is_free": int(free), "price": price, "duration_num": num, "duration_unit": unit}])
                        df_c = pd.concat([df_c, new_c], ignore_index=True)
                        save_sheet_data("Campos", df_c)
                        st.success(f"Campo añadido: {name}")
                        st.rerun()
                    else: st.error("No se pudo identificar el nombre del lugar.")

    st.write("---")
    st.write("### Lista de Campos")
    if not df_c.empty:
        for i, row in df_c.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"🏟️ **[{row['name']}]({row['map_url']})**")
            if c2.button("Eliminar", key=f"c_{i}"):
                df_c = df_c.drop(i).reset_index(drop=True)
                save_sheet_data("Campos", df_c)
                st.rerun()

# --- TAB: 🤼‍♂️ Miembros ---
with tab_miembros:
    st.subheader("Lista de Miembros")
    df_m = load_sheet_data("Miembros")
    with st.form("m_form"):
        name = st.text_input("Nombre del nuevo miembro")
        if st.form_submit_button("Añadir Miembro"):
            if name:
                df_m = pd.concat([df_m, pd.DataFrame([{"name": name}])], ignore_index=True)
                save_sheet_data("Miembros", df_m)
                st.success(f"¡{name} añadido!")
                st.rerun()
    
    st.write(f"Total de miembros: {len(df_m)}")
    for i, row in df_m.iterrows():
        c1, c2 = st.columns([4, 1])
        c1.write(f"👤 {row['name']}")
        if c2.button("Eliminar", key=f"m_{i}"):
            df_m = df_m.drop(i).reset_index(drop=True)
            save_sheet_data("Miembros", df_m)
            st.rerun()

# --- TAB: ⏳ Historial ---
with tab_historial:
    st.subheader("Historial de Partidos Pasados")
    df_e = load_sheet_data("Eventos")
    if not df_e.empty:
        tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        past = df_e[df_e['datetime'] < now].sort_values("datetime", ascending=False)
        if not past.empty:
            for _, row in past.iterrows():
                with st.expander(f"📅 {row['datetime']} - {row['venue']}"):
                    p_list = str(row['players']).split(",")
                    n_players = len([x for x in p_list if x.strip() and x != "nan"])
                    st.write(f"**Participantes ({n_players}):** {row['players']}")
        else:
            st.info("No hay partidos en el historial.")
