import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse

# ================= 1. 基础配置 =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="centered")

# 修改连接定义方式
conn = st.connection("gsheets", type=GSheetsConnection)

# 定义三个表格的 URL (替换为你自己的 edit 链接)
URL_M = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"
URL_C = "https://docs.google.com/spreadsheets/d/1tjTojyme8N-CaEdcewJHBwTPyDqbtF6JvWsz-Ej3HPU/edit"
URL_E = "https://docs.google.com/spreadsheets/d/1UWb__avGXO5wxIJLrqRh14zhDwMbqFTX38O-zBsDaPs/edit"

# 修改读取数据的函数
def get_data(url):
    return conn.read(spreadsheet=url, ttl=0).dropna(how="all")

# 修改保存数据的函数
def save_data(url, df):
    conn.update(spreadsheet=url, data=df)

# ================= 2. 辅助函数 (保留原逻辑) =================
def fetch_venue_name(url):
    """提取球场名称"""
    try:
        if "/place/" in url:
            part = url.split("/place/")[1].split("/")[0]
            name = urllib.parse.unquote(part).replace("+", " ")
            if name and "@" not in name: return name
    except Exception: pass
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        name = soup.title.string.replace(" - Google Maps", "").strip()
        return name if name and "Sign in" not in name else None
    except: return None

def formatear_precio(is_free, price, num, unit):
    """格式化价格显示"""
    if is_free or is_free == 1: return "Gratis"
    unit_str = "días" if (num > 1 and unit == "día") else (unit + "s" if num > 1 else unit)
    return f"{float(price):.2f} € / {int(num)} {unit_str}"

def get_data(conn):
    """实时读取数据[cite: 2]"""
    return conn.read(ttl=0).dropna(how="all")

# ================= 3. 导航菜单 =================
menu = st.sidebar.radio("Seleccione", ["🏠 Inicio", "📅 Publicar", "🥅 Campos", "🤼‍♂️ Miembros", "⏳ Historial"])

# ================= 🤼‍♂️ 成员管理 =================
if menu == "🤼‍♂️ Miembros":
    st.title("🤼‍♂️ Miembros")
    df_m = get_data(conn_m)
    
    with st.form("add_member"):
        new_name = st.text_input("Nombre del compañero")
        if st.form_submit_button("Añadir"):
            if new_name and new_name not in df_m['name'].values:
                df_m = pd.concat([df_m, pd.DataFrame([{"name": new_name}])], ignore_index=True)
                conn_m.update(data=df_m)
                st.success(f"Added: {new_name}")
                st.rerun()
    
    st.subheader(f"Lista Actual (Total: {len(df_m)})")
    for i, row in df_m.sort_values("name").iterrows():
        c1, c2 = st.columns([4,1])
        c1.write(f"- {row['name']}")
        if c2.button("🗑️", key=f"m_{i}"):
            df_m = df_m.drop(i)
            conn_m.update(data=df_m)
            st.rerun()

# ================= 🥅 球场管理 =================
elif menu == "🥅 Campos":
    st.title("🥅 Campos")
    df_c = get_data(conn_c)
    
    # 自动添加逻辑[cite: 2]
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
            conn_c.update(data=df_c)
            st.success(f"Guardado: {v_name}")
            st.rerun()

    st.divider()
    for i, row in df_c.iterrows():
        precio_txt = formatear_precio(row['is_free'], row['price'], row['duration_num'], row['duration_unit'])
        st.write(f"🏟️ **{row['name']}** | {precio_txt}")
        if st.button("Eliminar", key=f"c_{i}"):
            df_c = df_c.drop(i)
            conn_c.update(data=df_c)
            st.rerun()

# ================= 📅 发布比赛 =================
elif menu == "📅 Publicar":
    st.title("📅 Programar Partido")
    df_c = get_data(conn_c)
    df_e = get_data(conn_e)
    
    if df_c.empty:
        st.warning("Añade un campo primero.")
    else:
        with st.form("pub"):
            date = st.date_input("Fecha")
            time = st.time_input("Hora")
            venue = st.selectbox("Campo", df_c['name'].tolist())
            if st.form_submit_button("Publicar"):
                new_e = {"datetime": f"{date} {time}", "venue": venue, "players": ""}
                df_e = pd.concat([df_e, pd.DataFrame([new_e])], ignore_index=True)
                conn_e.update(data=df_e)
                st.success("¡Partido publicado!")

# ================= 🏠 首页报名 =================
elif menu == "🏠 Inicio":
    st.title("⚽ Próximo Partido")
    df_e = get_data(conn_e)
    df_m = get_data(conn_m)
    df_c = get_data(conn_c)
    
    # 筛选未来的比赛[cite: 2]
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    future_events = df_e[df_e['datetime'] >= now].sort_values("datetime")
    
    if not future_events.empty:
        event = future_events.iloc[0]
        idx = future_events.index[0]
        
        # 获取球场价格信息
        v_info = df_c[df_c['name'] == event['venue']]
        precio = "No especificado"
        if not v_info.empty:
            v = v_info.iloc[0]
            precio = formatear_precio(v['is_free'], v['price'], v['duration_num'], v['duration_unit'])
        
        st.info(f"**⏰:** {event['datetime']}\n\n**🏟️:** {event['venue']}\n\n**💰:** {precio}")
        
        # 报名逻辑[cite: 2]
        players = str(event['players']).split(",") if event['players'] and str(event['players']) != "nan" else []
        players = [p.strip() for p in players if p.strip()]
        
        sel = st.selectbox("Tu nombre", ["-- Seleccionar --"] + sorted(df_m['name'].tolist()))
        if st.button("Inscribirse / Cancelar", type="primary"):
            if sel != "-- Seleccionar --":
                if sel in players: players.remove(sel)
                else: players.append(sel)
                df_e.at[idx, 'players'] = ",".join(players)
                conn_e.update(data=df_e)
                st.rerun()
        
        st.subheader(f"🏃‍♂️ Inscritos: {len(players)}")
        for p in players: st.write(f"✅ {p}")
    else:
        st.write("No hay partidos programados.")

# ================= ⏳ 历史记录 =================
elif menu == "⏳ Historial":
    st.title("⏳ Historial")
    df_e = get_data(conn_e)
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    past = df_e[df_e['datetime'] < now].sort_values("datetime", ascending=False)
    
    for i, row in past.iterrows():
        with st.expander(f"📅 {row['datetime']} - {row['venue']}"):
            p_list = str(row['players']).split(",") if row['players'] and str(row['players']) != "nan" else []
            st.write(f"Participantes ({len(p_list)}): {', '.join(p_list)}")
