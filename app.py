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

# --- 重要：请确保此 URL 对应的表格中有名为 "Eventos", "Campos", "Miembros" 的工作表 ---
MAIN_URL = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"

conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet_data(worksheet_name):
    # ttl=300 缓存5分钟，大幅提升加载速度
    return conn.read(spreadsheet=MAIN_URL, worksheet=worksheet_name, ttl=300).dropna(how="all")

def save_sheet_data(worksheet_name, df):
    # 修复：使用 create 代替 update
    conn.create(spreadsheet=MAIN_URL, worksheet=worksheet_name, data=df)
    st.cache_data.clear() # 更新后清除缓存

# ================= 2. 辅助函数 =================
def fetch_venue_name(url):
    try:
        if "/place/" in url:
            part = url.split("/place/")[1].split("/")[0]
            name = urllib.parse.unquote(part).replace("+", " ")
            if name and "@" not in name: return name
    except: pass
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
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

# ================= 3. UI 布局 (Tabs 模式) =================
st.title("⚽ Club de Fútbol")

tab_inicio, tab_publicar, tab_campos, tab_miembros, tab_historial = st.tabs([
    "🏠 Inicio", "📅 Publicar", "🥅 Campos", "🤼‍♂️ Miembros", "⏳ Historial"
])

# --- TAB: 🏠 Inicio ---
with tab_inicio:
    st.subheader("Próximo Partido")
    df_e = load_sheet_data("Eventos")
    df_m = load_sheet_data("Miembros")
    df_c = load_sheet_data("Campos")
    
    if not df_e.empty and 'datetime' in df_e.columns:
        tz = pytz.timezone('Europe/Madrid') 
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        future_events = df_e[df_e['datetime'].str[:16] >= now].sort_values("datetime")
        
        if not future_events.empty:
            event = future_events.iloc[0]
            idx = future_events.index[0]
            
            v_info = df_c[df_c['name'] == event['venue']] if not df_c.empty else pd.DataFrame()
            precio, map_link = "No especificado", "#"
            if not v_info.empty:
                v = v_info.iloc[0]
                precio = formatear_precio(v.get('is_free',0), v.get('price',0), v.get('duration_num',1), v.get('duration_unit','hora'))
                map_link = v.get('map_url', '#')
            
            st.info(f"**⏰ Fecha:** {event['datetime']}\n\n**🏟️ Campo:** [{event['venue']}]({map_link})\n\n**💰 Precio:** {precio}")
            
            # 报名逻辑
            raw_players = str(event.get('players', ""))
            current_players_list = [p.strip() for p in raw_players.split(",") if p.strip() and raw_players != "nan"]
            all_members = sorted(df_m['name'].tolist()) if not df_m.empty else []
            available_members = [m for m in all_members if m not in current_players_list]
            
            st.divider()
            st.subheader("🙋‍♂️ Zona de Inscripción")
            sel = st.selectbox("Selecciona tu nombre:", ["-- Seleccionar --"] + available_members)
            
            if st.button("Confirmar Inscripción", type="primary"):
                if sel != "-- Seleccionar --":
                    current_players_list.append(sel)
                    df_e.at[idx, 'players'] = ",".join(current_players_list)
                    save_sheet_data("Eventos", df_e)
                    st.success(f"¡{sel} añadido!")
                    st.rerun() 
            
            st.divider()
            st.subheader(f"🏃‍♂️ Inscritos: {len(current_players_list)}")
            for p in current_players_list:
                c1, c2 = st.columns([4, 1])
                c1.write(f"✅ {p}")
                if c2.button("❌", key=f"del_{p}"):
                    current_players_list.remove(p)
                    df_e.at[idx, 'players'] = ",".join(current_players_list)
                    save_sheet_data("Eventos", df_e)
                    st.rerun()
        else:
            st.info("No hay partidos programados.")

# --- TAB: 📅 Publicar ---
with tab_publicar:
    st.subheader("Programar Partido")
    df_c = load_sheet_data("Campos")
    df_e = load_sheet_data("Eventos")
    
    if df_c.empty:
        st.warning("⚠️ Primero agrega campos en la pestaña 'Campos'.")
    else:
        with st.form("pub_form"):
            col1, col2 = st.columns(2)
            event_date = col1.date_input("Fecha")
            event_time = col2.time_input("Hora")
            selected_venue = st.selectbox("Campo", df_c['name'].tolist())
            if st.form_submit_button("Publicar Partido"):
                dt_str = f"{event_date.strftime('%Y-%m-%d')} {event_time.strftime('%H:%M')}"
                new_e = pd.DataFrame([{"datetime": dt_str, "venue": selected_venue, "players": ""}])
                df_e = pd.concat([df_e, new_e], ignore_index=True)
                save_sheet_data("Eventos", df_e)
                st.success("¡Publicado!")
                st.rerun()

# --- TAB: 🥅 Campos ---
with tab_campos:
    st.subheader("Gestión de Campos")
    df_c = load_sheet_data("Campos")
    
    with st.form("add_campo"):
        url = st.text_input("Enlace de Google Maps")
        is_free = st.checkbox("Gratis")
        col1, col2, col3 = st.columns(3)
        p = col1.number_input("Precio", min_value=0.0)
        n = col2.number_input("Cantidad", min_value=1)
        u = col3.selectbox("Unidad", ["hora", "día", "minuto"])
        if st.form_submit_button("Extraer y Guardar"):
            if url:
                with st.spinner("Buscando..."):
                    name = fetch_venue_name(url)
                    if name:
                        new_c = pd.DataFrame([{"name": name, "map_url": url, "is_free": int(is_free), "price": p, "duration_num": n, "duration_unit": u}])
                        df_c = pd.concat([df_c, new_c], ignore_index=True)
                        save_sheet_data("Campos", df_c)
                        st.success(f"Añadido: {name}")
                        st.rerun()
                    else: st.error("No se pudo obtener el nombre.")

    st.divider()
    for i, row in df_c.iterrows():
        c1, c2 = st.columns([4,1])
        c1.markdown(f"🏟️ **[{row['name']}]({row['map_url']})**")
        if c2.button("Eliminar", key=f"c_{i}"):
            df_c = df_c.drop(i)
            save_sheet_data("Campos", df_c)
            st.rerun()

# --- TAB: 🤼‍♂️ Miembros ---
with tab_miembros:
    st.subheader("Miembros")
    df_m = load_sheet_data("Miembros")
    with st.form("add_m"):
        name = st.text_input("Nombre")
        if st.form_submit_button("Añadir"):
            if name:
                df_m = pd.concat([df_m, pd.DataFrame([{"name": name}])], ignore_index=True)
                save_sheet_data("Miembros", df_m)
                st.rerun()
    for i, row in df_m.iterrows():
        c1, c2 = st.columns([4,1])
        c1.write(row['name'])
        if c2.button("🗑️", key=f"m_{i}"):
            df_m = df_m.drop(i)
            save_sheet_data("Miembros", df_m)
            st.rerun()

# --- TAB: ⏳ Historial ---
with tab_historial:
    st.subheader("Historial")
    df_e = load_sheet_data("Eventos")
    # 此处省略部分显示逻辑，同之前代码...
