import streamlit as st
import pandas as pd
import requests
import base64
from io import StringIO
from datetime import datetime, timedelta
import pytz
import urllib.parse
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from google.oauth2 import service_account

# ================= 1. CONFIGURACIÓN BÁSICA =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="wide")

# 从 Secrets 获取 GitHub 配置
GITHUB_TOKEN = st.secrets["github"]["token"]
REPO = st.secrets["github"]["repo"]
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

# ================= 2. GITHUB 数据读写逻辑 (替换原有 GSheets) =================

def load_github_data(file_name):
    """
    从 GitHub 根目录读取 CSV 文件
    """
    path = f"{file_name}.csv"
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    try:
        # 增加时间戳参数防止 API 缓存旧数据
        response = requests.get(f"{url}?t={datetime.now().timestamp()}", headers=HEADERS)
        if response.status_code == 200:
            content_json = response.json()
            csv_text = base64.b64decode(content_json['content']).decode('utf-8')
            df = pd.read_csv(StringIO(csv_text))
            return df.dropna(how="all"), content_json['sha']
        else:
            # 如果文件不存在，初始化一个空的 DataFrame
            cols = {
                "Miembros": ["name"],
                "Campos": ["name", "map_url", "is_free", "price", "duration_num", "duration_unit"],
                "Votaciones": ["Fecha", "Jugadores"],
                "Eventos": ["datetime", "venue", "players"]
            }
            return pd.DataFrame(columns=cols.get(file_name, [])), None
    except Exception as e:
        st.error(f"Error al cargar {file_name} desde GitHub: {e}")
        return pd.DataFrame(), None

def save_github_data(file_name, df, message="Actualización de datos"):
    """
    将 DataFrame 保存到 GitHub 根目录
    """
    path = f"{file_name}.csv"
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    
    # 1. 获取最新的 SHA
    _, sha = load_github_data(file_name)
    
    # 2. 准备内容
    csv_content = df.to_csv(index=False)
    encoded_content = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
    
    payload = {
        "message": message,
        "content": encoded_content
    }
    if sha:
        payload["sha"] = sha

    # 3. 提交更新
    response = requests.put(url, headers=HEADERS, json=payload)
    if response.status_code in [200, 201]:
        st.cache_data.clear()
        return True
    else:
        st.error(f"Error al guardar {file_name}: {response.text}")
        return False

# ================= 3. GOOGLE CALENDAR (保留原有逻辑) =================

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
            start_str = event['start'].get('dateTime', event['start'].get('date'))
            dt = datetime.fromisoformat(start_str.replace('Z', '+00:00')).astimezone(tz)
            date_str = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M')
            if date_str not in slots_by_date:
                slots_by_date[date_str] = []
            slots_by_date[date_str].append(time_str)
        return slots_by_date, start_of_week
    except Exception as e:
        st.error(f"Error al conectar con el calendario: {e}")
        return {}, datetime.now()

# ================= 4. FUNCIONES AUXILIARES (保留原有逻辑) =================

def formatear_precio(is_free, price, dur_num, dur_unit):
    if is_free == 1 or price == 0:
        return "Gratis"
    return f"{price}€ / {dur_num} {dur_unit}"

def get_google_maps_name(url):
    try:
        if "maps" not in url: return "Ver Mapa"
        res = requests.get(url, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        title = soup.find('title').text
        return title.replace(" - Google Maps", "")
    except:
        return "Ver Mapa"

# ================= 5. INTERFAZ DE USUARIO (TABS) =================

tab_votacion, tab_eventos, tab_campos, tab_miembros = st.tabs([
    "🗳️ Votaciones", "📅 Partidos", "🏟️ Campos", "🤼‍♂️ Miembros"
])

# --- TAB: 🗳️ Votaciones ---
with tab_votacion:
    st.subheader("Votación de horarios")
    slots, start_week = get_calendar_slots_grouped()
    df_v, _ = load_github_data("Votaciones")
    df_m, _ = load_github_data("Miembros")
    
    if not slots:
        st.info("No hay horarios disponibles en el calendario.")
    else:
        # 这里保留你原有的选日期、选人、投票逻辑
        col1, col2 = st.columns(2)
        with col1:
            fecha_voto = st.radio("Selecciona Fecha", list(slots.keys()), horizontal=True)
        with col2:
            hora_voto = st.selectbox("Selecciona Hora", slots[fecha_voto])
            
        nombre_voto = st.selectbox("¿Quién eres?", df_m['name'].tolist() if not df_m.empty else [])
        
        if st.button("Confirmar Votación"):
            # 简化逻辑：在 Votaciones.csv 中保存记录
            # 注意：需根据你原本的 CSV 结构调整列名
            new_vote = pd.DataFrame([{"Fecha": f"{fecha_voto} {hora_voto}", "Jugadores": nombre_voto}])
            df_v = pd.concat([df_v, new_vote], ignore_index=True)
            if save_github_data("Votaciones", df_v):
                st.success("Voto guardado en GitHub")
                st.rerun()

# --- TAB: 📅 Partidos (Eventos) ---
with tab_eventos:
    st.subheader("📅 Historial de Partidos")
    df_e, _ = load_github_data("Eventos")
    st.dataframe(df_e, use_container_width=True)

# --- TAB: 🏟️ Campos ---
with tab_campos:
    st.subheader("🏟️ Gestión de Campos")
    df_c, _ = load_github_data("Campos")
    
    with st.expander("➕ Añadir nuevo campo"):
        with st.form("new_campo"):
            c_name = st.text_input("Nombre del campo")
            c_url = st.text_input("URL Google Maps")
            if st.form_submit_button("Guardar Campo"):
                new_c = pd.DataFrame([{"name": c_name, "map_url": c_url, "is_free": 0, "price": 0, "duration_num": 1, "duration_unit": "hora"}])
                df_c = pd.concat([df_c, new_c], ignore_index=True)
                save_github_data("Campos", df_c)
                st.rerun()
    
    if not df_c.empty:
        for i, row in df_c.iterrows():
            st.write(f"📍 {row['name']}")

# --- TAB: 🤼‍♂️ Miembros ---
with tab_miembros:
    st.subheader("🤼‍♂️ Miembros del Club")
    df_m, _ = load_github_data("Miembros")
    
    with st.form("m_form"):
        new_member = st.text_input("Nombre del nuevo miembro")
        if st.form_submit_button("Añadir"):
            if new_member:
                df_m = pd.concat([df_m, pd.DataFrame([{"name": new_member}])], ignore_index=True)
                save_github_data("Miembros", df_m)
                st.rerun()
    
    if not df_m.empty:
        st.table(df_m)
