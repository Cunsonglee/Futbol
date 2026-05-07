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

# --- 请在这里填写你合并后的主表格 URL ---
MAIN_URL = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"

conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet_data(worksheet_name):
    # ttl=300 表示 5 分钟内使用缓存，不重复请求 Google，显著提速
    return conn.read(spreadsheet=MAIN_URL, worksheet=worksheet_name, ttl=300).dropna(how="all")

def save_sheet_data(worksheet_name, df):
    conn.update(spreadsheet=MAIN_URL, worksheet=worksheet_name, data=df)
    st.cache_data.clear() # 保存后清空缓存，确保下次读取是最新的

# ================= 2. 辅助函数 =================
def fetch_venue_name(url):
    """仅在用户点击时触发：获取球场名称"""
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

# ================= 3. UI 布局 (Tabs 模式) =================
st.title("⚽ Club de Fútbol")

# 创建五个标签页
tab_inicio, tab_publicar, tab_campos, tab_miembros, tab_historial = st.tabs([
    "🏠 Inicio", "📅 Publicar", "🥅 Campos", "🤼‍♂️ Miembros", "⏳ Historial"
])

# ================= TAB: 🏠 Inicio =================
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
            
            # 获取球场信息
            v_info = df_c[df_c['name'] == event['venue']] if not df_c.empty else pd.DataFrame()
            precio = "No especificado"
            map_link = "#"
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
            
            st.write("---")
            st.subheader("🙋‍♂️ Zona de Inscripción")
            sel = st.selectbox("Selecciona tu nombre:", ["-- Seleccionar --"] + available_members, key="sel_member")
            
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
    else:
        st.write("Cargando datos...")

# ================= TAB: 📅 Publicar =================
with tab_publicar:
    st.subheader("Programar Partido")
    df_c = load_sheet_data("Campos")
    df_e = load_sheet_data("Eventos")
    
    if df_c.empty:
        st.warning("⚠️ Todavía no hay campos guardados. Agrégalos en la pestaña 'Campos'.")
    else:
        venue_list = df_c['name'].tolist()
        with st.form("pub_form"):
            col1, col2 = st.columns(2)
            event_date = col1.date_input("Fecha")
            event_time = col2.time_input("Hora")
            selected_venue = st.selectbox("Campo", venue_list)
            if st.form_submit_button("Publicar Partido"):
                datetime_str = f"{event_date.strftime('%Y-%m-%d')} {event_time.strftime('%H:%M')}"
                new_e = {"datetime": datetime_str, "venue": selected_venue, "players": ""}
                df_e = pd.concat([df_e, pd.DataFrame([new_e])], ignore_index=True)
                save_sheet_data("Eventos", df_e)
                st.success("¡Partido publicado!")
                st.rerun()

# ================= TAB: 🥅 Campos =================
with tab_campos:
    st.subheader("Gestión de Campos")
    df_c = load_sheet_data("Campos")
    
    # 只有在这里提交表单，才会触发 fetch_venue_name 爬虫
    with st.form("add_campo_form"):
        auto_url = st.text_input("Enlace de Google Maps (URL)")
        is_free = st.checkbox("Es Gratis")
        col1, col2, col3 = st.columns(3)
        p = col1.number_input("Precio (€)", min_value=0.0)
        n = col2.number_input("Cantidad", min_value=1, value=1)
        u = col3.selectbox("Unidad", ["hora", "día", "minuto"])
        
        submit_campo = st.form_submit_button("Extraer Nombre y Guardar")
        
        if submit_campo:
            if auto_url:
                with st.spinner("Buscando nombre del campo en Google Maps..."):
                    v_name = fetch_venue_name(auto_url)
                    if v_name:
                        new_row = {"name": v_name, "map_url": auto_url, "is_free": int(is_free), 
                                   "price": p, "duration_num": n, "duration_unit": u}
                        df_c = pd.concat([df_c, pd.DataFrame([new_row])], ignore_index=True)
                        save_sheet_data("Campos", df_c)
                        st.success(f"Guardado: {v_name}")
                        st.rerun()
                    else:
                        st.error("No se pudo obtener el nombre. Verifica el enlace.")
            else:
                st.warning("Por favor, introduce un enlace.")

    st.divider()
    st.write("### Campos Existentes")
    if not df_c.empty:
        for i, row in df_c.iterrows():
            p_txt = formatear_precio(row.get('is_free',0), row.get('price',0), row.get('duration_num',1), row.get('duration_unit','hora'))
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"🏟️ **[{row['name']}]({row['map_url']})**\n{p_txt}")
            if c2.button("Eliminar", key=f"del_c_{i}"):
                df_c = df_c.drop(i)
                save_sheet_data("Campos", df_c)
                st.rerun()

# ================= TAB: 🤼‍♂️ Miembros =================
with tab_miembros:
    st.subheader("Gestión de Miembros")
    df_m = load_sheet_data("Miembros")
    
    with st.form("add_member"):
        new_name = st.text_input("Nombre del compañero")
        if st.form_submit_button("Añadir"):
            if new_name and ('name' not in df_m.columns or new_name not in df_m['name'].values):
                df_m = pd.concat([df_m, pd.DataFrame([{"name": new_name}])], ignore_index=True)
                save_sheet_data("Miembros", df_m)
                st.rerun()
    
    st.write(f"**Total: {len(df_m)}**")
    if not df_m.empty:
        for i, row in df_m.sort_values("name").iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(f"- {row['name']}")
            if c2.button("🗑️", key=f"del_m_{i}"):
                df_m = df_m.drop(i)
                save_sheet_data("Miembros", df_m)
                st.rerun()

# ================= TAB: ⏳ Historial =================
with tab_historial:
    st.subheader("Historial de Partidos")
    df_e = load_sheet_data("Eventos")
    df_c = load_sheet_data("Campos")
    
    if not df_e.empty:
        tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        past_events = df_e[df_e['datetime'].str[:16] < now].sort_values("datetime", ascending=False)
        
        for i, row in past_events.iterrows():
            v_match = df_c[df_c['name'] == row['venue']] if not df_c.empty else pd.DataFrame()
            v_url = v_match.iloc[0]['map_url'] if not v_match.empty else "#"
            
            with st.expander(f"📅 {row['datetime']} | 🏟️ {row['venue']}"):
                st.markdown(f"📍 [Ver ubicación]({v_url})")
                players = [p.strip() for p in str(row['players']).split(",") if p.strip() and str(row['players']) != "nan"]
                st.write(f"Participantes ({len(players)}): {', '.join(players)}")
    else:
        st.info("No hay datos históricos.")
