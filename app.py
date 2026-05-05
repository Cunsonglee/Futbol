import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse

# ================= 1. 基础配置 =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="centered")

# 建立连接
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 使用你提供的正确 URL ---
URL_M = "https://docs.google.com/spreadsheets/d/1tjTojyme8N-CaEdcewJHBwTPyDqbtF6JvWsz-Ej3HPU/edit"
URL_C = "https://docs.google.com/spreadsheets/d/1UWb__avGXO5wxIJLrqRh14zhDwMbqFTX38O-zBsDaPs/edit"
URL_E = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"

def load_sheet_data(url):
    """实时读取数据，清除空行"""
    return conn.read(spreadsheet=url, ttl=0).dropna(how="all")

def save_sheet_data(url, df):
    """保存数据到 Google Sheets[cite: 2]"""
    conn.update(spreadsheet=url, data=df)

# ================= 2. 辅助函数 (爬虫与格式化) =================
def fetch_venue_name(url):
    """自动抓取球场名[cite: 2]"""
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
    """价格显示逻辑[cite: 2]"""
    if is_free or is_free == 1: return "Gratis"
    try:
        unit_str = "días" if (num > 1 and unit == "día") else (unit + "s" if num > 1 else unit)
        return f"{float(price):.2f} € / {int(num)} {unit_str}"
    except: return "No especificado"

# ================= 3. 导航菜单 =================
menu = st.sidebar.radio("Seleccione", ["🏠 Inicio", "📅 Publicar", "🥅 Campos", "🤼‍♂️ Miembros", "⏳ Historial"])

# ================= 🤼‍♂️ 成员管理 =================
if menu == "🤼‍♂️ Miembros":
    st.title("🤼‍♂️ Miembros")
    df_m = load_sheet_data(URL_M)
    
    with st.form("add_member"):
        new_name = st.text_input("Nombre del compañero")
        if st.form_submit_button("Añadir"):
            if new_name and ('name' not in df_m.columns or new_name not in df_m['name'].values):
                df_m = pd.concat([df_m, pd.DataFrame([{"name": new_name}])], ignore_index=True)
                save_sheet_data(URL_M, df_m)
                st.success(f"Added: {new_name}")
                st.rerun()
    
    st.subheader(f"Lista Actual (Total: {len(df_m)})")
    if not df_m.empty and 'name' in df_m.columns:
        for i, row in df_m.sort_values("name").iterrows():
            c1, c2 = st.columns([4,1])
            c1.write(f"- {row['name']}")
            if c2.button("🗑️", key=f"m_{i}"):
                df_m = df_m.drop(i)
                save_sheet_data(URL_M, df_m)
                st.rerun()

# ================= 🥅 球场管理 =================
elif menu == "🥅 Campos":
    st.title("🥅 Campos")
    df_c = load_sheet_data(URL_C)
    
    auto_url = st.text_input("Enlace de Google Maps")
    is_free = st.checkbox("Gratis")
    col1, col2, col3 = st.columns(3)
    p = col1.number_input("Precio", min_value=0.0)
    n = col2.number_input("Cantidad", min_value=1, value=1)
    u = col3.selectbox("Unidad", ["hora", "día", "minuto"])
    
    if st.button("Extraer y Guardar"):
        v_name = fetch_venue_name(auto_url)
        if v_name:
            new_row = {"name": v_name, "map_url": auto_url, "is_free": int(is_free), 
                       "price": p, "duration_num": n, "duration_unit": u}
            df_c = pd.concat([df_c, pd.DataFrame([new_row])], ignore_index=True)
            save_sheet_data(URL_C, df_c)
            st.success(f"Guardado: {v_name}")
            st.rerun()

    st.divider()
    if not df_c.empty:
        for i, row in df_c.iterrows():
            precio_txt = formatear_precio(row.get('is_free',0), row.get('price',0), row.get('duration_num',1), row.get('duration_unit','hora'))
            st.write(f"🏟️ **{row['name']}** | {precio_txt}")
            if st.button("Eliminar", key=f"c_{i}"):
                df_c = df_c.drop(i)
                save_sheet_data(URL_C, df_c)
                st.rerun()

# ================= 📅 Página: Publicar Partido (发布比赛) =================
elif menu == "📅 Publicar":
    st.title("📅 Programar Partido")
    
    # 读取球场数据和比赛数据
    df_c = load_sheet_data(URL_C)
    df_e = load_sheet_data(URL_E)
    
    if df_c.empty:
        st.warning("⚠️ Todavía no hay campos guardados. ¡Ve a '🥅 Campos' para añadir uno!")
    else:
        # 修复点：删除了标注文字
        venue_list = df_c['name'].tolist()
        
        with st.form("pub_form"):
            col1, col2 = st.columns(2)
            with col1:
                event_date = st.date_input("Fecha del partido")
            with col2:
                event_time = st.time_input("Hora del partido")
                
            selected_venue = st.selectbox("Seleccionar campo", venue_list)
            submit_event = st.form_submit_button("Publicar Partido")
            
            if submit_event:
                # 格式化时间，包含日期和具体分钟
                datetime_str = f"{event_date.strftime('%Y-%m-%d')} {event_time.strftime('%H:%M')}"
                
                # 创建新条目
                new_e = {
                    "datetime": datetime_str, 
                    "venue": selected_venue, 
                    "players": ""
                }
                
                # 合并并保存
                df_e = pd.concat([df_e, pd.DataFrame([new_e])], ignore_index=True)
                
                try:
                    save_sheet_data(URL_E, df_e)
                    st.success(f"✅ ¡Partido publicado con éxito para el {datetime_str}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al guardar en Google Sheets: {e}")

# ================= 🏠 Página: Inicio (主页 - 仅显示未来比赛) =================
elif menu == "🏠 Inicio":
    st.title("⚽ Próximo Partido")
    
    # 1. 实时读取数据
    df_e = load_sheet_data(URL_E)
    df_m = load_sheet_data(URL_M)
    df_c = load_sheet_data(URL_C)
    
    if not df_e.empty and 'datetime' in df_e.columns:
        # 2. 获取当前系统精确时间 (格式需与表格一致)
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        # 3. 核心修改：筛选“大于或等于现在”的比赛
        # 这会自动过滤掉所有已经过去的比赛
        future_events = df_e[df_e['datetime'] >= now].sort_values("datetime")
        
        if not future_events.empty:
            # 获取最近的一场未来比赛
            event = future_events.iloc[0]
            idx = future_events.index[0]
            
            # 获取球场价格信息
            v_info = df_c[df_c['name'] == event['venue']] if not df_c.empty else pd.DataFrame()
            precio = "No especificado"
            if not v_info.empty:
                v = v_info.iloc[0]
                precio = formatear_precio(v.get('is_free',0), v.get('price',0), v.get('duration_num',1), v.get('duration_unit','hora'))
            
            # --- 界面展示 ---
            st.info(f"**⏰ Fecha y Hora:** {event['datetime']}\n\n**🏟️ Campo:** {event['venue']}\n\n**💰 Precio:** {precio}")
            
            st.divider()
            st.subheader("🙋‍♂️ Zona de Inscripción")
            
            # 4. 解析名单 (处理空值)[cite: 2]
            raw_players = str(event.get('players', ""))
            if raw_players == "nan" or not raw_players.strip():
                current_players_list = []
            else:
                current_players_list = [p.strip() for p in raw_players.split(",") if p.strip()]
            
            # 5. 报名操作[cite: 2]
            member_names = sorted(df_m['name'].tolist()) if not df_m.empty else []
            sel = st.selectbox("Selecciona tu nombre:", ["-- Seleccionar --"] + member_names)
            
            if st.button("Inscribirse / Cancelar", type="primary"):
                if sel != "-- Seleccionar --":
                    if sel in current_players_list:
                        current_players_list.remove(sel)
                    else:
                        current_players_list.append(sel)
                    
                    # 写入数据[cite: 2]
                    df_e['players'] = df_e['players'].astype(object) 
                    df_e.at[idx, 'players'] = ",".join(current_players_list)
                    save_sheet_data(URL_E, df_e)
                    st.rerun() 
            
            # 6. 名单实时显示
            st.divider()
            st.subheader(f"🏃‍♂️ Inscritos: {len(current_players_list)}")
            for p in current_players_list:
                st.write(f"✅ {p}")
        else:
            # 如果所有比赛都过期了[cite: 2]
            st.info("No hay partidos programados. Los partidos pasados se han movido a 'Historial'.")
    else:
        st.write("Configura tus datos para empezar.")

# ================= ⏳ Página: Historial (历史记录 - 显示日期和时间) =================
elif menu == "⏳ Historial":
    st.title("⏳ Historial de Partidos")
    
    # 1. 实时读取比赛数据
    df_e = load_sheet_data(URL_E)
    
    if not df_e.empty and 'datetime' in df_e.columns:
        # 2. 获取当前系统时间
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        # 3. 筛选已经过去的比赛（时间小于现在），并按时间倒序排列（最近的排最前）
        past_events = df_e[df_e['datetime'] < now].sort_values("datetime", ascending=False)
        
        if not past_events.empty:
            st.write("Aquí puedes ver los partidos pasados y quiénes participaron:")
            
            for i, row in past_events.iterrows():
                # 直接显示 row['datetime']，它包含了日期和时间[cite: 2]
                event_label = f"📅 {row['datetime']} | 🏟️ {row['venue']}"
                
                with st.expander(event_label):
                    # 4. 解析报名名单字符串[cite: 2]
                    raw_p = str(row.get('players', ""))
                    if raw_p == "nan" or not raw_p.strip():
                        players_list = []
                    else:
                        players_list = [p.strip() for p in raw_p.split(",") if p.strip()]
                    
                    # 5. 显示参与详情[cite: 2]
                    st.markdown(f"**Total de participantes:** {len(players_list)}")
                    
                    if players_list:
                        # 用逗号连接名字并显示
                        st.write("🏃 Jugadores: " + ", ".join(players_list))
                    else:
                        st.write("Nadie se inscribió en este partido.")
        else:
            st.info("Aún no hay partidos en el historial.")
    else:
        st.info("No hay datos de partidos grabados.")
