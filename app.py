import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse
import pytz 

# ================= 1. 基础配置 =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="centered")

conn = st.connection("gsheets", type=GSheetsConnection)

URL_M = "https://docs.google.com/spreadsheets/d/1tjTojyme8N-CaEdcewJHBwTPyDqbtF6JvWsz-Ej3HPU/edit"
URL_C = "https://docs.google.com/spreadsheets/d/1UWb__avGXO5wxIJLrqRh14zhDwMbqFTX38O-zBsDaPs/edit"
URL_E = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"

def load_sheet_data(url):
    return conn.read(spreadsheet=url, ttl=0).dropna(how="all")

def save_sheet_data(url, df):
    conn.update(spreadsheet=url, data=df)

# ================= 2. 辅助函数 =================
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
            # 球场管理页面显示可点击链接
            st.markdown(f"🏟️ **[{row['name']}]({row['map_url']})** | {precio_txt}")
            if st.button("Eliminar", key=f"c_{i}"):
                df_c = df_c.drop(i)
                save_sheet_data(URL_C, df_c)
                st.rerun()

# ================= 📅 发布比赛 =================
elif menu == "📅 Publicar":
    st.title("📅 Programar Partido")
    df_c = load_sheet_data(URL_C)
    df_e = load_sheet_data(URL_E)
    
    if df_c.empty:
        st.warning("⚠️ Todavía no hay campos guardados.")
    else:
        venue_list = df_c['name'].tolist()
        with st.form("pub_form"):
            col1, col2 = st.columns(2)
            with col1:
                event_date = st.date_input("Fecha")
            with col2:
                event_time = st.time_input("Hora")
            selected_venue = st.selectbox("Campo", venue_list)
            if st.form_submit_button("Publicar"):
                datetime_str = f"{event_date.strftime('%Y-%m-%d')} {event_time.strftime('%H:%M')}"
                new_e = {"datetime": datetime_str, "venue": selected_venue, "players": ""}
                df_e = pd.concat([df_e, pd.DataFrame([new_e])], ignore_index=True)
                try:
                    save_sheet_data(URL_E, df_e)
                    st.success("¡Publicado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

# ================= 🏠 Página: Inicio (主页) =================
elif menu == "🏠 Inicio":
    st.title("⚽ Próximo Partido")
    
    df_e = load_sheet_data(URL_E)
    df_m = load_sheet_data(URL_M)
    df_c = load_sheet_data(URL_C)
    
    if not df_e.empty and 'datetime' in df_e.columns:
        tz = pytz.timezone('Europe/Madrid') 
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        
        # 筛选未来比赛[cite: 1]
        future_events = df_e[df_e['datetime'].str[:16] >= now].sort_values("datetime")
        
        if not future_events.empty:
            event = future_events.iloc[0]
            idx = future_events.index[0]
            
            # 获取球场信息[cite: 1]
            v_info = df_c[df_c['name'] == event['venue']] if not df_c.empty else pd.DataFrame()
            precio = "No especificado"
            map_link = "#"
            if not v_info.empty:
                v = v_info.iloc[0]
                precio = formatear_precio(v.get('is_free',0), v.get('price',0), v.get('duration_num',1), v.get('duration_unit','hora'))
                map_link = v.get('map_url', '#')
            
            st.info(f"**⏰ Fecha:** {event['datetime']}\n\n**🏟️ Campo:** [{event['venue']}]({map_link})\n\n**💰 Precio:** {precio}")
            st.divider()
            
            # 解析已报名名单[cite: 1]
            raw_players = str(event.get('players', ""))
            current_players_list = [p.strip() for p in raw_players.split(",") if p.strip() and raw_players != "nan"]
            
            # --- 核心改进：过滤下拉菜单[cite: 1] ---
            all_members = sorted(df_m['name'].tolist()) if not df_m.empty else []
            # 只有还没报名的人会出现在下拉菜单里[cite: 1]
            available_members = [m for m in all_members if m not in current_players_list]
            
            st.subheader("🙋‍♂️ Zona de Inscripción")
            sel = st.selectbox("Selecciona tu nombre:", ["-- Seleccionar --"] + available_members)
            
            if st.button("Confirmar Inscripción", type="primary"):
                if sel != "-- Seleccionar --":
                    current_players_list.append(sel) # 只能添加，因为已报名的人不在这里了[cite: 1]
                    df_e['players'] = df_e['players'].astype(object) 
                    df_e.at[idx, 'players'] = ",".join(current_players_list)
                    save_sheet_data(URL_E, df_e)
                    st.success(f"¡{sel} añadido!")
                    st.rerun() 
            
            # --- 增加：取消报名按钮 (可选，因为名字从下拉菜单消失了) ---
            st.divider()
            st.subheader(f"🏃‍♂️ Inscritos: {len(current_players_list)}")
            
            for p in current_players_list:
                c1, c2 = st.columns([4, 1])
                c1.write(f"✅ {p}")
                # 在名单旁边放一个“取消”按钮，方便退出[cite: 1]
                if c2.button("❌", key=f"del_{p}"):
                    current_players_list.remove(p)
                    df_e['players'] = df_e['players'].astype(object) 
                    df_e.at[idx, 'players'] = ",".join(current_players_list)
                    save_sheet_data(URL_E, df_e)
                    st.rerun()
        else:
            st.info("No hay partidos programados.")
    else:
        st.write("Configura tus datos para empezar.")

# ================= ⏳ 历史记录 (带地图链接) =================
elif menu == "⏳ Historial":
    st.title("⏳ Historial de Partidos")
    df_e = load_sheet_data(URL_E)
    df_c = load_sheet_data(URL_C) # 这里的 df_c 用来匹配历史记录里的地图链接
    
    if not df_e.empty and 'datetime' in df_e.columns:
        tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        past_events = df_e[df_e['datetime'].str[:16] < now].sort_values("datetime", ascending=False)
        
        if not past_events.empty:
            for i, row in past_events.iterrows():
                # 寻找该球场的地图链接
                v_match = df_c[df_c['name'] == row['venue']]
                v_url = v_match.iloc[0]['map_url'] if not v_match.empty else "#"
                
                # 标题显示为可点击链接[cite: 1]
                event_label = f"📅 {row['datetime']} | 🏟️ {row['venue']}"
                with st.expander(event_label):
                    st.markdown(f"📍 [Ver en Google Maps]({v_url})") # 内部也加一个明确的链接[cite: 1]
                    raw_p = str(row.get('players', ""))
                    players_list = [p.strip() for p in raw_p.split(",") if p.strip() and raw_p != "nan"]
                    st.write(f"Participantes ({len(players_list)}): " + ", ".join(players_list))
        else:
            st.info("No hay historial.")
    else:
        st.info("No hay datos.")
