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

# ================= 1. 初始化与配额管理 =================
st.set_page_config(page_title="足球俱乐部管理", page_icon="⚽", layout="wide")

MAIN_URL = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

# 使用 Streamlit 的缓存装饰器，大幅减少对 Google Sheets 的请求频率
@st.cache_data(ttl=600) # 10分钟才读一次
def get_static_data(worksheet):
    try:
        return conn.read(spreadsheet=MAIN_URL, worksheet=worksheet).dropna(how="all")
    except:
        return pd.DataFrame()

def get_dynamic_data(worksheet):
    # 投票和事件数据使用极短缓存，但也要避免 0
    try:
        return conn.read(spreadsheet=MAIN_URL, worksheet=worksheet, ttl=2).dropna(how="all")
    except:
        return pd.DataFrame()

def save_data(worksheet, df):
    try:
        conn.update(worksheet=worksheet, data=df)
        st.cache_data.clear() # 保存后清除本地所有缓存，确保刷新后看到最新的
    except Exception as e:
        st.error(f"保存失败: {e}")

# ================= 2. 工具函数 =================
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

def get_calendar_slots():
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
            calendarId=calendar_id, timeMin=start_of_week.isoformat(),
            timeMax=time_max.isoformat(), singleEvents=True, orderBy='startTime').execute()
            
        events = events_result.get('items', [])
        slots = {}
        for event in events:
            start = event.get('start', {})
            end = event.get('end', {})
            if 'dateTime' in start:
                s_dt = datetime.fromisoformat(start['dateTime']).astimezone(tz)
                e_dt = datetime.fromisoformat(end['dateTime']).astimezone(tz)
                d_str = s_dt.strftime('%Y-%m-%d')
                s_t, e_t = s_dt.strftime('%H:%M'), e_dt.strftime('%H:%M')
                f = "Mañana" if s_t=="07:00" else ("Tarde" if s_t in ["13:00","17:00"] else f"{s_t}-{e_t}")
                if d_str not in slots: slots[d_str] = []
                slots[d_str].append(f)
        return slots, start_of_week
    except: return {}, datetime.now()

# ================= 3. 界面布局 =================
tab_inicio, tab_votar, tab_cal, tab_campos, tab_miembros = st.tabs(["🏠 首页", "🗳️ 投票报名", "📅 完整日历", "🥅 场地管理", "🤼‍♂️ 成员名单"])

# --- TAB: 🗳️ 投票报名 ---
with tab_votar:
    st.subheader("选择场次并登记人员")
    
    # 核心：从内存加载，减少 API 消耗
    df_v = get_dynamic_data("Votaciones")
    df_m = get_static_data("Miembros")
    
    # 1. 绘制网格
    slots, start_day = get_calendar_slots()
    selected = []
    
    d_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    h_cols = st.columns(7)
    for i, d in enumerate(d_names): h_cols[i].markdown(f"**{d}**")
    
    curr = start_day
    for w in range(6):
        cols = st.columns(7)
        for i in range(7):
            d_str = curr.strftime('%Y-%m-%d')
            with cols[i]:
                st.caption(curr.strftime('%d/%m'))
                if d_str in slots:
                    for f in slots[d_str]:
                        full_val = f"{d_str} ({f})"
                        if st.checkbox(f, key=f"v_{full_val}"): selected.append(full_val)
                else: st.write("NON")
            curr += timedelta(days=1)
        st.write("---")

    names = sorted(df_m['name'].tolist()) if not df_m.empty else []
    who = st.multiselect("谁要参加？", names)
    
    if st.button("Confirmar Jugadores", type="primary"):
        if not selected or not who:
            st.warning("请至少勾选一个日期和一名成员")
        else:
            with st.spinner("正在写入数据..."):
                # 处理数据逻辑
                for s in selected:
                    if not df_v.empty and s in df_v['Fecha'].values:
                        idx = df_v[df_v['Fecha'] == s].index[0]
                        old = str(df_v.at[idx, 'Jugadores']).split(",")
                        updated = list(set([x.strip() for x in old if x.strip()] + who))
                        df_v.at[idx, 'Jugadores'] = ",".join(updated)
                    else:
                        df_v = pd.concat([df_v, pd.DataFrame([{"Fecha": s, "Jugadores": ",".join(who)}])], ignore_index=True)
                save_data("Votaciones", df_v)
                st.success("登记成功！")
                st.rerun()

    st.divider()
    st.subheader("📊 Estado de votaciones (当前投票情况)")
    if not df_v.empty:
        for i, r in df_v.iterrows():
            f, j = str(r['Fecha']), str(r['Jugadores'])
            j_list = [x.strip() for x in j.split(",") if x.strip() and j != "nan"]
            if j_list:
                with st.expander(f"📅 {f} — ({len(j_list)}人报名)"):
                    st.write(f"名单: {', '.join(j_list)}")
                    if len(j_list) >= 5:
                        df_c = get_static_data("Campos")
                        campo = st.selectbox("选择场地", df_c['name'].tolist() if not df_c.empty else ["无"], key=f"cp_{f}")
                        tm = st.time_input("确认具体时间", key=f"tm_{f}")
                        if st.button("Publicar Partida", key=f"pub_{f}"):
                            # 写入 Eventos 逻辑
                            df_e = get_dynamic_data("Eventos")
                            final_dt = f"{f.split(' ')[0]} {tm.strftime('%H:%M')}"
                            new_e = pd.DataFrame([{"datetime": final_dt, "venue": campo, "players": j}])
                            save_data("Eventos", pd.concat([df_e, new_e], ignore_index=True))
                            # 删除当前投票
                            save_data("Votaciones", df_v.drop(i))
                            st.rerun()
    else:
        st.info("暂无投票数据")

# --- TAB: 🥅 场地管理 (功能补全) ---
with tab_campos:
    st.subheader("场地库")
    df_c = get_static_data("Campos")
    with st.form("add_campo"):
        u = st.text_input("Google Maps 链接")
        c1, c2 = st.columns(2)
        p = c1.number_input("价格", min_value=0.0)
        fr = st.checkbox("免费")
        if st.form_submit_button("添加场地"):
            name = fetch_venue_name(u)
            if name:
                new_df = pd.concat([df_c, pd.DataFrame([{"name": name, "map_url": u, "price": p, "is_free": int(fr)}])], ignore_index=True)
                save_data("Campos", new_df)
                st.rerun()
    
    if not df_c.empty:
        for i, r in df_c.iterrows():
            st.write(f"🏟️ **{r['name']}** - [地图]({r['map_url']})")
            if st.button("删除", key=f"dc_{i}"):
                save_data("Campos", df_c.drop(i))
                st.rerun()

# --- TAB: 🤼‍♂️ 成员名单 ---
with tab_miembros:
    df_m = get_static_data("Miembros")
    new_m = st.text_input("新增成员姓名")
    if st.button("添加"):
        if new_m:
            save_data("Miembros", pd.concat([df_m, pd.DataFrame([{"name": new_m}])], ignore_index=True))
            st.rerun()
    st.write(df_m)

# --- TAB: 📅 完整日历 ---
with tab_cal:
    components.iframe("https://calendar.google.com/calendar/embed?src=07854ef03649a28b9507946bb4f7af183d0cf1f49535580916c12c2a4fd1933c%40group.calendar.google.com&ctz=Europe%2FMadrid", height=600)
