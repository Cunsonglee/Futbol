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

# 🟢 优化配额：根据数据类型设置不同的缓存时间
def load_sheet_data(worksheet_name, ttl=600):
    """
    Miembros/Campos: 600s (10 min)
    Votaciones/Eventos: 5s (Evita el Error 429)
    """
    try:
        df = conn.read(spreadsheet=MAIN_URL, worksheet=worksheet_name, ttl=ttl)
        return df.dropna(how="all")
    except Exception as e:
        if worksheet_name == "Votaciones":
            return pd.DataFrame(columns=['Fecha', 'Jugadores'])
        st.error(f"Error al cargar {worksheet_name}: {e}")
        return pd.DataFrame()

def save_sheet_data(worksheet_name, df):
    """保存数据并强制清除缓存，确保下次读取是最新的"""
    try:
        st.cache_data.clear() # 关键：保存前先清空本地缓存
        conn.update(worksheet=worksheet_name, data=df)
        st.cache_data.clear() # 保存后再次清空，确保 rerun 读取的是新数据
    except Exception as e:
        try:
            conn.create(spreadsheet=MAIN_URL, worksheet=worksheet_name, data=df)
        except Exception as e2:
            st.error(f"Error al guardar: {e2}")

# ================= 2. FUNCIONES AUXILIARES =================
def fetch_venue_name(url):
    """恢复：从 Google Maps 链接中提取球场名称"""
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
    """恢复：格式化球场价格显示"""
    if is_free or is_free == 1: return "Gratis"
    try:
        unit_str = "días" if (num > 1 and unit == "día") else (unit + "s" if num > 1 else unit)
        return f"{float(price):.2f} € / {int(num)} {unit_str}"
    except: return "No especificado"

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

# ================= 3. DISEÑO DE INTERFAZ =================
st.title("⚽ Gestión del Club")

tab_inicio, tab_votar, tab_calendario, tab_campos, tab_miembros, tab_historial = st.tabs([
    "🏠 Inicio", "🗳️ Votar", "📅 Calendario", "🥅 Campos", "🤼‍♂️ Miembros", "⏳ Historial"
])

# --- TAB: 🏠 Inicio ---
with tab_inicio:
    st.subheader("Próximo Partido Confirmado")
    df_e = load_sheet_data("Eventos", ttl=5)
    df_c = load_sheet_data("Campos", ttl=600)
    if not df_e.empty and 'datetime' in df_e.columns:
        tz = pytz.timezone('Europe/Madrid') 
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        future_events = df_e[df_e['datetime'].astype(str) >= now].sort_values("datetime")
        if not future_events.empty:
            event = future_events.iloc[0]
            st.info(f"**⏰ Fecha:** {event['datetime']}\n\n**🏟️ Campo:** {event['venue']}")
            players = [p.strip() for p in str(event.get('players', "")).split(",") if p.strip() and str(event.get('players', "")) != "nan"]
            st.write(f"🏃‍♂️ **Inscritos ({len(players)}):** {', '.join(players)}")
        else: st.info("No hay partidos próximos programados.")

# --- TAB: 🗳️ Votar (解决不显示/429问题) ---
with tab_votar:
    st.subheader("🗳️ Panel de Votación y Registro")
    
    # 使用极短的 TTL 以保证刷新，但不为 0 以节省配额
    df_v = load_sheet_data("Votaciones", ttl=5)
    df_m = load_sheet_data("Miembros", ttl=600)
    all_m = sorted(df_m['name'].tolist()) if not df_m.empty else []

    st.write("### 1. Seleccionar Fechas (Malla Lunes-Domingo)")
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

    st.write("### 2. Seleccionar Miembros")
    sel_members = st.multiselect("Elige a los miembros que asistirán:", all_m)
    
    if st.button("Confirmar Jugadores", type="primary"):
        if not selected_slots: st.warning("⚠️ Selecciona al menos una fecha.")
        elif not sel_members: st.warning("⚠️ Selecciona al menos un miembro.")
        else:
            with st.spinner("Guardando votos..."):
                # 重新读取数据防止覆盖
                df_v_fresh = load_sheet_data("Votaciones", ttl=0)
                for s in selected_slots:
                    s = str(s).strip()
                    if not df_v_fresh.empty and s in df_v_fresh['Fecha'].astype(str).values:
                        idx = df_v_fresh.index[df_v_fresh['Fecha'].astype(str) == s][0]
                        existentes = [p.strip() for p in str(df_v_fresh.at[idx, 'Jugadores']).split(",") if p.strip() and str(df_v_fresh.at[idx, 'Jugadores']) != "nan"]
                        for m in sel_members:
                            if m not in existentes: existentes.append(m)
                        df_v_fresh.at[idx, 'Jugadores'] = ",".join(existentes)
                    else:
                        new_row = pd.DataFrame([{"Fecha": s, "Jugadores": ",".join(sel_members)}])
                        df_v_fresh = pd.concat([df_v_fresh, new_row], ignore_index=True)
                
                save_sheet_data("Votaciones", df_v_fresh)
                st.success("✅ ¡Votos guardados! La página se actualizará...")
                st.rerun()

    st.divider()
    st.write("### 3. Estado de Votaciones y Publicación")
    
    # 重新读取用于显示的实时数据
    if not df_v.empty:
        for idx, row in df_v.iterrows():
            f, j_str = str(row['Fecha']), str(row['Jugadores'])
            jugadores = [p.strip() for p in j_str.split(",") if p.strip() and j_str != "nan"]
            
            if jugadores:
                with st.container():
                    c1, c2 = st.columns([3, 1])
                    c1.markdown(f"📅 **{f}**")
                    c2.write(f"🏃‍♂️ **{len(jugadores)}**")
                    st.write(f"👥 {', '.join(jugadores)}")
                    
                    if len(jugadores) >= 5:
                        with st.expander("🚀 Publicar Partido (Mínimo 5 alcanzado)"):
                            df_c = load_sheet_data("Campos", ttl=600)
                            h = st.time_input("Hora", key=f"h_{f}")
                            campo = st.selectbox("Campo", df_c['name'].tolist() if not df_c.empty else ["No hay campos"], key=f"c_{f}")
                            if st.button("Confirmar y Publicar", key=f"p_{f}", type="primary"):
                                dt = f"{f.split(' ')[0]} {h.strftime('%H:%M')}"
                                df_e = load_sheet_data("Eventos", ttl=0)
                                new_e = pd.DataFrame([{"datetime": dt, "venue": campo, "players": ",".join(jugadores)}])
                                save_sheet_data("Eventos", pd.concat([df_e, new_e], ignore_index=True))
                                # 发布后删除投票
                                df_v_upd = load_sheet_data("Votaciones", ttl=0)
                                df_v_upd = df_v_upd[df_v_upd['Fecha'].astype(str) != f]
                                save_sheet_data("Votaciones", df_v_upd)
                                st.rerun()
                    else:
                        st.info(f"⏳ Faltan {5 - len(jugadores)} para poder publicar.")
                    st.write("---")
    else:
        st.info("No hay votos registrados actualmente.")

# --- TAB: 📅 Calendario ---
with tab_calendario:
    st.subheader("Google Calendar")
    components.iframe("https://calendar.google.com/calendar/embed?src=07854ef03649a28b9507946bb4f7af183d0cf1f49535580916c12c2a4fd1933c%40group.calendar.google.com&ctz=Europe%2FMadrid", height=600)

# --- TAB: 🥅 Campos (功能已找回) ---
with tab_campos:
    st.subheader("🥅 Gestión de Campos")
    df_c = load_sheet_data("Campos", ttl=600)
    
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
                        save_sheet_data("Campos", pd.concat([df_c, new_c], ignore_index=True))
                        st.success(f"Campo añadido: {name}")
                        st.rerun()
                    else: st.error("No se pudo identificar el lugar.")

    st.write("### Campos Registrados")
    if not df_c.empty:
        for i, row in df_c.iterrows():
            c1, c2 = st.columns([4, 1])
            precio_f = formatear_precio(row.get('is_free',0), row.get('price',0), row.get('duration_num',1), row.get('duration_unit','hora'))
            c1.markdown(f"🏟️ **[{row['name']}]({row['map_url']})** — {precio_f}")
            if c2.button("Eliminar", key=f"del_c_{i}"):
                df_c_new = df_c.drop(i).reset_index(drop=True)
                save_sheet_data("Campos", df_c_new)
                st.rerun()

# --- TAB: 🤼‍♂️ Miembros ---
with tab_miembros:
    st.subheader("🤼‍♂️ Miembros del Club")
    df_m = load_sheet_data("Miembros", ttl=600)
    with st.form("m_form"):
        new_name = st.text_input("Nombre del miembro")
        if st.form_submit_button("Añadir"):
            if new_name:
                save_sheet_data("Miembros", pd.concat([df_m, pd.DataFrame([{"name": new_name}])], ignore_index=True))
                st.rerun()
    
    if not df_m.empty:
        for i, r in df_m.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(f"👤 {r['name']}")
            if c2.button("Eliminar", key=f"m_del_{i}"):
                save_sheet_data("Miembros", df_m.drop(i))
                st.rerun()

# --- TAB: ⏳ Historial ---
with tab_historial:
    st.subheader("⏳ Historial de Partidos")
    df_e = load_sheet_data("Eventos", ttl=30)
    if not df_e.empty:
        st.dataframe(df_e.sort_values("datetime", ascending=False), use_container_width=True)
