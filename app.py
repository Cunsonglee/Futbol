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

# --- ⚠️ 重要：在这里放入你的 Google Sheet 完整链接 ---
# 确保这个表格里有三个 Tab (工作表)，名称分别是: Eventos, Campos, Miembros
MAIN_URL = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"

conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet_data(worksheet_name):
    # 使用 spreadsheet 参数明确指定链接，防止报错
    try:
        return conn.read(spreadsheet=MAIN_URL, worksheet=worksheet_name, ttl=300).dropna(how="all")
    except Exception as e:
        st.error(f"读取数据失败 (Tab: {worksheet_name}): {e}")
        return pd.DataFrame()

def save_sheet_data(worksheet_name, df):
    # 使用 create 方法覆盖更新数据
    try:
        conn.create(spreadsheet=MAIN_URL, worksheet=worksheet_name, data=df)
        st.cache_data.clear() # 更新后清除缓存，确保数据实时
    except Exception as e:
        st.error(f"保存数据失败 (Tab: {worksheet_name}): {e}")

# ================= 2. 辅助函数 =================
def fetch_venue_name(url):
    """只在点击按钮时触发的爬虫"""
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

# ================= 3. UI 布局 (Tabs 标签页) =================
st.title("⚽ 管理系统")

tab_inicio, tab_publicar, tab_campos, tab_miembros, tab_historial = st.tabs([
    "🏠 Inicio", "📅 Publicar", "🥅 Campos", "🤼‍♂️ Miembros", "⏳ Historial"
])

# --- TAB: 首页 ---
with tab_inicio:
    st.subheader("Próximo Partido")
    df_e = load_sheet_data("Eventos")
    df_m = load_sheet_data("Miembros")
    df_c = load_sheet_data("Campos")
    
    if not df_e.empty and 'datetime' in df_e.columns:
        tz = pytz.timezone('Europe/Madrid') 
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        # 转换并排序未来比赛
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
            
            st.info(f"**⏰ Fecha:** {event['datetime']}\n\n**🏟️ Campo:** [{event['venue']}]({map_link})\n\n**💰 Precio:** {precio}")
            
            # 报名名单处理
            players_str = str(event.get('players', ""))
            current_players = [p.strip() for p in players_str.split(",") if p.strip() and players_str != "nan"]
            
            # 过滤未报名成员
            all_m = sorted(df_m['name'].tolist()) if not df_m.empty else []
            available = [m for m in all_m if m not in current_players]
            
            st.write("---")
            sel = st.selectbox("选择你的名字报名:", ["-- Seleccionar --"] + available)
            if st.button("Confirmar Inscripción", type="primary"):
                if sel != "-- Seleccionar --":
                    current_players.append(sel)
                    df_e.at[idx, 'players'] = ",".join(current_players)
                    save_sheet_data("Eventos", df_e)
                    st.success(f"{sel} 报名成功!")
                    st.rerun()
            
            st.divider()
            st.write(f"🏃‍♂️ **已报名人数: {len(current_players)}**")
            for p in current_players:
                c1, c2 = st.columns([5, 1])
                c1.write(f"✅ {p}")
                if c2.button("❌", key=f"del_{p}"):
                    current_players.remove(p)
                    df_e.at[idx, 'players'] = ",".join(current_players)
                    save_sheet_data("Eventos", df_e)
                    st.rerun()
        else:
            st.info("目前没有待举办的比赛。")

# --- TAB: 发布比赛 ---
with tab_publicar:
    st.subheader("发布新比赛")
    df_c = load_sheet_data("Campos")
    if df_c.empty:
        st.warning("请先在 Campos 标签页添加球场。")
    else:
        with st.form("pub_form"):
            d = st.date_input("日期")
            t = st.time_input("时间")
            venue = st.selectbox("选择球场", df_c['name'].tolist())
            if st.form_submit_button("发布"):
                dt_str = f"{d.strftime('%Y-%m-%d')} {t.strftime('%H:%M')}"
                df_e = load_sheet_data("Eventos")
                new_row = pd.DataFrame([{"datetime": dt_str, "venue": venue, "players": ""}])
                df_e = pd.concat([df_e, new_row], ignore_index=True)
                save_sheet_data("Eventos", df_e)
                st.success("发布成功！")
                st.rerun()

# --- TAB: 球场管理 ---
with tab_campos:
    st.subheader("球场数据管理")
    df_c = load_sheet_data("Campos")
    with st.form("campo_form"):
        u = st.text_input("Google Maps 链接")
        free = st.checkbox("免费球场")
        col1, col2, col3 = st.columns(3)
        price = col1.number_input("价格", min_value=0.0)
        num = col2.number_input("数值", min_value=1, value=1)
        unit = col3.selectbox("单位", ["hora", "día", "minuto"])
        if st.form_submit_button("抓取并保存"):
            if u:
                with st.spinner("抓取球场名称中..."):
                    name = fetch_venue_name(u)
                    if name:
                        new_c = pd.DataFrame([{"name": name, "map_url": u, "is_free": int(free), "price": price, "duration_num": num, "duration_unit": unit}])
                        df_c = pd.concat([df_c, new_c], ignore_index=True)
                        save_sheet_data("Campos", df_c)
                        st.success(f"已添加: {name}")
                        st.rerun()
                    else: st.error("无法识别链接名称。")

    st.write("---")
    if not df_c.empty:
        for i, row in df_c.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"🏟️ **[{row['name']}]({row['map_url']})**")
            if c2.button("删除", key=f"c_{i}"):
                df_c = df_c.drop(i).reset_index(drop=True)
                save_sheet_data("Campos", df_c)
                st.rerun()

# --- TAB: 成员管理 ---
with tab_miembros:
    st.subheader("成员名单")
    df_m = load_sheet_data("Miembros")
    with st.form("m_form"):
        name = st.text_input("新成员姓名")
        if st.form_submit_button("添加"):
            if name:
                df_m = pd.concat([df_m, pd.DataFrame([{"name": name}])], ignore_index=True)
                save_sheet_data("Miembros", df_m)
                st.rerun()
    st.write(f"总人数: {len(df_m)}")
    for i, row in df_m.iterrows():
        c1, c2 = st.columns([4, 1])
        c1.write(f"👤 {row['name']}")
        if c2.button("🗑️", key=f"m_{i}"):
            df_m = df_m.drop(i).reset_index(drop=True)
            save_sheet_data("Miembros", df_m)
            st.rerun()

# --- TAB: 历史记录 ---
with tab_historial:
    st.subheader("比赛历史记录")
    df_e = load_sheet_data("Eventos")
    if not df_e.empty:
        tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        past = df_e[df_e['datetime'] < now].sort_values("datetime", ascending=False)
        for _, row in past.iterrows():
            with st.expander(f"📅 {row['datetime']} - {row['venue']}"):
                p_list = str(row['players']).split(",")
                st.write(f"参赛者 ({len([x for x in p_list if x.strip()])}): {row['players']}")
