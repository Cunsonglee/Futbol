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

# ================= 1. 初始化设置 =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="wide")

# 从 Secrets 获取 GitHub 配置
GITHUB_TOKEN = st.secrets["github"]["token"]
REPO = st.secrets["github"]["repo"]
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

# ================= 2. GITHUB 数据读写逻辑 =================

def load_github_data(file_name, ttl=5):
    """
    从 GitHub 根目录读取 CSV 文件。
    注意：文件名必须与 GitHub 上的完全一致（包括空格和大小写）。
    """
    path = f"{file_name}.csv"
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    
    try:
        # 增加随机参数防止 GitHub API 缓存旧数据
        response = requests.get(f"{url}?t={datetime.now().timestamp()}", headers=HEADERS)
        if response.status_code == 200:
            content_json = response.json()
            csv_text = base64.b64decode(content_json['content']).decode('utf-8')
            df = pd.read_csv(StringIO(csv_text))
            return df.dropna(how="all"), content_json['sha']
        else:
            st.warning(f"Archivo {path} no encontrado, se creará uno nuevo al guardar.")
            return pd.DataFrame(), None
    except Exception as e:
        st.error(f"Error al cargar {file_name}: {e}")
        return pd.DataFrame(), None

def save_github_data(file_name, df, message="Actualización de datos"):
    """将 DataFrame 保存回 GitHub 根目录"""
    path = f"{file_name}.csv"
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    
    # 1. 获取当前的 SHA
    _, sha = load_github_data(file_name)
    
    # 2. 准备数据
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
        st.error(f"Error al guardar en GitHub: {response.text}")
        return False

# ================= 3. GOOGLE CALENDAR 逻辑 (保留) =================

def get_calendar_slots_grouped():
    try:
        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        # 使用 Secrets 里的 connections.gsheets 信息作为 Service Account 凭据
        creds_info = st.secrets["connections"]["gsheets"]
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        
        # 你的日历 ID
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
        st.error(f"Error al conectar con Google Calendar: {e}")
        return {}, datetime.now()

# ================= 4. UI 界面逻辑 =================

tab_main, tab_votaciones, tab_campos, tab_miembros = st.tabs([
    "🏠 Inicio", "🗳️ Votaciones", "🏟️ Campos", "🤼‍♂️ Miembros"
])

# --- TAB: Miembros ---
with tab_miembros:
    st.subheader("🤼‍♂️ Gestión de Miembros")
    # 注意文件名：使用你上传的完整文件名（不带.csv）
    df_m, _ = load_github_data("eventos - Miembros")
    
    with st.form("add_member"):
        nuevo_nombre = st.text_input("Nombre del nuevo miembro")
        if st.form_submit_button("Añadir"):
            if nuevo_nombre:
                new_row = pd.DataFrame([{"name": nuevo_nombre}])
                df_m = pd.concat([df_m, new_row], ignore_index=True)
                if save_github_data("eventos - Miembros", df_m):
                    st.success(f"{nuevo_nombre} añadido.")
                    st.rerun()

    if not df_m.empty:
        for i, row in df_m.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(row['name'])
            if c2.button("Eliminar", key=f"del_m_{i}"):
                df_m = df_m.drop(i)
                save_github_data("eventos - Miembros", df_m)
                st.rerun()

# --- TAB: Campos ---
with tab_campos:
    st.subheader("🏟️ Campos Registrados")
    df_c, _ = load_github_data("eventos - Campos")
    
    # 简化的添加表单示例
    with st.expander("➕ Añadir Campo"):
        with st.form("c_form"):
            name = st.text_input("Nombre del campo")
            url = st.text_input("Google Maps URL")
            if st.form_submit_button("Guardar"):
                new_c = pd.DataFrame([{"name": name, "map_url": url, "is_free": 0, "price": 0, "duration_num": 1, "duration_unit": "hora"}])
                df_c = pd.concat([df_c, new_c], ignore_index=True)
                save_github_data("eventos - Campos", df_c)
                st.rerun()

    if not df_c.empty:
        for i, row in df_c.iterrows():
            st.markdown(f"📍 **{row['name']}** - [Ver en Mapa]({row['map_url']})")

# --- TAB: Votaciones (核心逻辑) ---
with tab_votaciones:
    st.subheader("🗳️ Votaciones Abiertas")
    df_v, _ = load_github_data("eventos - Votaciones")
    slots, start_week = get_calendar_slots_grouped()
    
    # 这里放置你的投票逻辑，使用 df_v 进行操作
    # 提交投票时调用 save_github_data("eventos - Votaciones", updated_df)

# --- 首页提示 ---
with tab_main:
    st.title("⚽ Football Club Manager")
    st.info("Datos almacenados en GitHub. Calendario sincronizado con Google.")
