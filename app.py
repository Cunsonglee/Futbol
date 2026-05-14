import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import urllib.parse
import pytz 
import base64
from io import StringIO

from googleapiclient.discovery import build
from google.oauth2 import service_account

# ================= 1. CONFIGURACIÓN BÁSICA & GITHUB LOGIC =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="wide")

# GitHub 配置
GITHUB_TOKEN = st.secrets["github"]["token"]
REPO = st.secrets["github"]["repo"]
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

def load_github_data(file_name):
    """从 GitHub 根目录读取 CSV"""
    path = f"{file_name}.csv"
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    try:
        # 增加时间戳防止缓存
        response = requests.get(f"{url}?t={datetime.now().timestamp()}", headers=HEADERS)
        if response.status_code == 200:
            content_json = response.json()
            csv_text = base64.b64decode(content_json['content']).decode('utf-8')
            df = pd.read_csv(StringIO(csv_text))
            return df.dropna(how="all"), content_json['sha']
        else:
            # 初始化默认列
            defaults = {
                "Votaciones": ['Fecha', 'Jugadores'],
                "Miembros": ['name'],
                "Campos": ['name', 'map_url', 'is_free', 'price', 'duration_num', 'duration_unit'],
                "Eventos": ['datetime', 'venue', 'players']
            }
            return pd.DataFrame(columns=defaults.get(file_name, [])), None
    except Exception:
        return pd.DataFrame(), None

def save_github_data(file_name, df, message="Update"):
    """保存 CSV 到 GitHub 根目录"""
    path = f"{file_name}.csv"
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    
    # 获取 SHA
    _, sha = load_github_data(file_name)
    
    csv_content = df.to_csv(index=False)
    encoded_content = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
    
    payload = {"message": message, "content": encoded_content}
    if sha: payload["sha"] = sha

    response = requests.put(url, headers=HEADERS, json=payload)
    if response.status_code in [200, 201]:
        st.cache_data.clear()
        return True
    else:
        st.error(f"Error GitHub: {response.text}")
        return False

# ================= 2. GOOGLE CALENDAR LOGIC (保持原样) =================

def get_calendar_slots_grouped():
    try:
        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        # 依然使用 Secrets 里的 Google 凭据
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
            start_str = event['start'].get('dateTime', event['start'].get('date'))
            dt = datetime.fromisoformat(start_str.replace('Z', '+00:00')).astimezone(tz)
            date_str = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M')
            if date_str not in slots_by_date: slots_by_date[date_str] = []
            slots_by_date[date_str].append(time_str)
        return slots_by_date, start_of_week
    except Exception as e:
        st.error(f"Error Calendario: {e}")
        return {}, datetime.now()

# ================= 3. FUNCIONES AUXILIARES (保留原样式逻辑) =================

def formatear_precio(is_free, price, dur_num, dur_unit):
    if is_free == 1 or price == 0: return "Gratis"
    return f"{price}€ / {dur_num} {dur_unit}"

COLOR_DISPONIBLE = "#e1f5fe"
COLOR_SELECCIONADO = "#4caf50"
COLOR_TEXTO_SELECCIONADO = "white"

def generar_html_slots(fecha, slots_dia, slots_seleccionados):
    html = '<div style="display: flex; flex-wrap: wrap; gap: 10px;">'
    for s in slots_dia:
        is_sel = (fecha == slots_seleccionados.get('fecha') and s == slots_seleccionados.get('hora'))
        bg = COLOR_SELECCIONADO if is_sel else COLOR_DISPONIBLE
        tx = COLOR_TEXTO_SELECCIONADO if is_sel else "black"
        html += f'<div style="background-color: {bg}; color: {tx}; padding: 8px 15px; border-radius: 20px; border: 1px solid #ccc; font-size: 14px; font-weight: 500;">{s}</div>'
    html += '</div>'
    return html

# ================= 4. INTERFAZ DE USUARIO (TABS) =================

tab_votacion, tab_historial, tab_campos, tab_miembros = st.tabs([
    "🗳️ Votaciones", "📊 Historial", "🏟️ Campos", "🤼‍♂️ Miembros"
])

# --- TAB: 🗳️ Votaciones ---
with tab_votacion:
    st.subheader("🗳️ Votación de Próximo Partido")
    slots_grouped, start_week = get_calendar_slots_grouped()
    df_v, _ = load_github_data("Votaciones")
    df_m, _ = load_github_data("Miembros")

    if not slots_grouped:
        st.info("No hay horarios disponibles en el calendario.")
    else:
        with st.form("form_votacion"):
            user_name = st.selectbox("¿Quién eres?", df_m['name'].tolist() if not df_m.empty else ["Añade miembros primero"])
            
            st.write("Selecciona el día y la hora:")
            dates = list(slots_grouped.keys())
            cols_radio = st.columns(len(dates))
            selected_date = st.radio("Fecha", dates, horizontal=True)
            selected_hour = st.selectbox("Hora", slots_grouped[selected_date])
            
            if st.form_submit_button("Confirmar Votación"):
                fecha_full = f"{selected_date} {selected_hour}"
                # 更新逻辑：如果人已存在，更新其投票
                if not df_v.empty and user_name in df_v['Jugadores'].values:
                    df_v.loc[df_v['Jugadores'] == user_name, 'Fecha'] = fecha_full
                else:
                    new_v = pd.DataFrame([{"Fecha": fecha_full, "Jugadores": user_name}])
                    df_v = pd.concat([df_v, new_v], ignore_index=True)
                
                if save_github_data("Votaciones", df_v):
                    st.success(f"¡Voto registrado para {user_name}!")
                    st.rerun()

    # 统计展示
    if not df_v.empty:
        st.write("---")
        st.subheader("📊 Recuento de Votos")
        stats = df_v.groupby('Fecha')['Jugadores'].apply(list).reset_index()
        stats['Total'] = stats['Jugadores'].apply(len)
        for _, row in stats.sort_values('Total', ascending=False).iterrows():
            with st.expander(f"📅 {row['Fecha']} — {row['Total']} Jugadores"):
                st.write(", ".join(row['Jugadores']))

# --- TAB: 📊 Historial ---
with tab_historial:
    st.subheader("📊 Historial de Partidos")
    df_e, _ = load_github_data("Eventos")
    st.dataframe(df_e, use_container_width=True)

# --- TAB: 🏟️ Campos ---
with tab_campos:
    st.subheader("🏟️ Gestión de Campos")
    df_c, _ = load_github_data("Campos")
    
    with st.expander("➕ Añadir nuevo campo"):
        with st.form("new_c"):
            c_name = st.text_input("Nombre")
            c_url = st.text_input("URL Google Maps")
            if st.form_submit_button("Guardar"):
                new_c = pd.DataFrame([{"name": c_name, "map_url": c_url, "is_free": 0, "price": 0, "duration_num": 1, "duration_unit": "hora"}])
                df_c = pd.concat([df_c, new_c], ignore_index=True)
                save_github_data("Campos", df_c)
                st.rerun()

    if not df_c.empty:
        for i, row in df_c.iterrows():
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"📍 **[{row['name']}]({row['map_url']})**")
            if c2.button("🗑️", key=f"del_c_{i}"):
                df_c = df_c.drop(i)
                save_github_data("Campos", df_c)
                st.rerun()

# --- TAB: 🤼‍♂️ Miembros ---
with tab_miembros:
    st.subheader("🤼‍♂️ Miembros del Club")
    df_m, _ = load_github_data("Miembros")
    
    with st.form("m_add"):
        m_name = st.text_input("Nombre del miembro")
        if st.form_submit_button("Añadir"):
            if m_name:
                df_m = pd.concat([df_m, pd.DataFrame([{"name": m_name}])], ignore_index=True)
                save_github_data("Miembros", df_m)
                st.rerun()
    
    if not df_m.empty:
        for i, row in df_m.iterrows():
            c1, c2 = st.columns([5, 1])
            c1.write(row['name'])
            if c2.button("🗑️", key=f"del_m_{i}"):
                df_m = df_m.drop(i)
                save_github_data("Miembros", df_m)
                st.rerun()
