import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse

# 设置网页标题和图标
st.set_page_config(page_title="周末足球俱乐部", page_icon="⚽", layout="centered")

# ================= 辅助函数：获取 Google 地图名称 =================
def fetch_venue_name(url):
    """优先从URL提取名称，如果失败再尝试抓取网页"""
    # 1. 尝试直接从 URL 提取 (针对 /maps/place/场地名称/ 这种格式)
    try:
        if "/place/" in url:
            part = url.split("/place/")[1].split("/")[0]
            # 把 URL 编码的文字和加号转成正常的空格和文字
            name = urllib.parse.unquote(part).replace("+", " ")
            if name and "@" not in name:
                return name
    except Exception:
        pass

    # 2. 备用方案：尝试抓取网页标题
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string if soup.title else ""
        name = title.replace(" - Google Maps", "").replace("Google Maps", "").strip()
        if name and "Sign in" not in name:
            return name
        return None
    except Exception as e:
        return None

# ================= 数据库设置 =================
DB_NAME = 'football_v2.db' # 更改了数据库名称，避免旧数据冲突

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS members (name TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS venues 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, map_url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS events 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, event_datetime TEXT, venue_name TEXT, map_url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS registrations 
                 (event_id INTEGER, member_name TEXT, UNIQUE(event_id, member_name))''')
    conn.commit()
    conn.close()

init_db()

# ================= 侧边栏导航 =================
st.sidebar.title("⚽ 菜单栏")
menu = st.sidebar.radio("请选择操作", ["🏠 主页 - 下一场比赛", "📅 发布新比赛", "🏟️ 管理球场", "👥 管理成员"])

# ================= 页面：主页 =================
if menu == "🏠 主页 - 下一场比赛":
    st.title("⚽ 周末足球俱乐部")
    
    conn = sqlite3.connect(DB_NAME)
    event_df = pd.read_sql_query("SELECT * FROM events ORDER BY id DESC LIMIT 1", conn)
    
    if not event_df.empty:
        event_id = event_df['id'][0]
        event_datetime = event_df['event_datetime'][0]
        venue_name = event_df['venue_name'][0]
        map_url = event_df['map_url'][0]
        
        st.subheader("📅 下一次活动信息")
        st.info(f"**⏰ 时间:** {event_datetime}\n\n**🏟️ 场地:** {venue_name}")
        if map_url:
            st.markdown(f"📍 **[点击这里在 Google 地图中打开]({map_url})**")
            
        st.divider()
        
        st.subheader("🙋‍♂️ 报名区")
        members_df = pd.read_sql_query("SELECT name FROM members", conn)
        
        if not members_df.empty:
            member_list = members_df['name'].tolist()
            selected_member = st.selectbox("请选择你的名字进行报名：", ["-- 请选择 --"] + member_list)
            
            if st.button("报名 / 取消报名", type="primary"):
                if selected_member == "-- 请选择 --":
                    st.warning("请先选择你的名字！")
                else:
                    c = conn.cursor()
                    c.execute("SELECT * FROM registrations WHERE event_id=? AND member_name=?", (int(event_id), selected_member))
                    if c.fetchone():
                        c.execute("DELETE FROM registrations WHERE event_id=? AND member_name=?", (int(event_id), selected_member))
                        st.warning(f"{selected_member} 已取消报名。")
                    else:
                        c.execute("INSERT INTO registrations (event_id, member_name) VALUES (?, ?)", (int(event_id), selected_member))
                        st.success(f"{selected_member} 报名成功！")
                    conn.commit()
                    st.rerun()
        else:
            st.warning("目前没有成员，请先到“管理成员”添加同事！")
            
        st.divider()
        regs_df = pd.read_sql_query(f"SELECT member_name FROM registrations WHERE event_id={event_id}", conn)
        st.subheader(f"🏃‍♂️ 总共报名人数: {len(regs_df)} 人")
        
        if not regs_df.empty:
            for index, row in regs_df.iterrows():
                st.write(f"✅ {row['member_name']}")
        else:
            st.write("还没有人报名，快来抢沙发！")
            
    else:
        st.info("目前没有安排任何比赛。请到“发布新比赛”页面安排活动。")
    conn.close()

# ================= 页面：发布新比赛 =================
elif menu == "📅 发布新比赛":
    st.title("📅 安排下一场比赛")
    
    conn = sqlite3.connect(DB_NAME)
    venues_df = pd.read_sql_query("SELECT * FROM venues", conn)
    
    if venues_df.empty:
        st.warning("⚠️ 目前还没有保存任何场地。请先去“🏟️ 管理球场”添加场地！")
    else:
        venue_list = venues_df['name'].tolist()
        
        with st.form("add_event_form"):
            col1, col2 = st.columns(2)
            with col1:
                event_date = st.date_input("比赛日期")
            with col2:
                event_time = st.time_input("比赛时间")
                
            selected_venue = st.selectbox("选择场地", venue_list)
            submit_event = st.form_submit_button("发布比赛")
            
            if submit_event:
                datetime_str = f"{event_date.strftime('%Y-%m-%d')} {event_time.strftime('%H:%M')}"
                map_url = venues_df.loc[venues_df['name'] == selected_venue, 'map_url'].values[0]
                
                c = conn.cursor()
                c.execute("INSERT INTO events (event_datetime, venue_name, map_url) VALUES (?, ?, ?)", 
                          (datetime_str, selected_venue, map_url))
                conn.commit()
                st.success("✅ 比赛发布成功！去主页看看吧。")
    conn.close()

# ================= 页面：管理球场 =================
elif menu == "🏟️ 管理球场":
    st.title("🏟️ 球队常驻球场")
    
    # --- 添加场地 ---
    st.subheader("✨ 添加新场地")
    auto_url = st.text_input("输入 Google 地图链接", placeholder="https://www.google.com/maps/place/...")
    if st.button("自动抓取并保存", type="primary"):
        if auto_url:
            with st.spinner("正在获取场地信息..."):
                venue_name = fetch_venue_name(auto_url)
                if venue_name:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO venues (name, map_url) VALUES (?, ?)", (venue_name, auto_url))
                        conn.commit()
                        st.success(f"✅ 成功添加场地：**{venue_name}**")
                    except sqlite3.IntegrityError:
                        st.error("⚠️ 该场地名称已存在！")
                    finally:
                        conn.close()
                else:
                    st.error("❌ 无法自动获取，请展开下方使用手动添加。")
        else:
            st.warning("请先输入链接！")

    with st.expander("🛠️ 手动添加场地"):
        with st.form("manual_venue_form"):
            manual_name = st.text_input("手动输入场地名称")
            manual_url = st.text_input("手动输入地图链接")
            if st.form_submit_button("保存"):
                if manual_name and manual_url:
                    conn = sqlite3.connect(DB_NAME)
                    try:
                        conn.execute("INSERT INTO venues (name, map_url) VALUES (?, ?)", (manual_name, manual_url))
                        conn.commit()
                        st.success("添加成功！")
                    except sqlite3.IntegrityError:
                        st.error("名称已存在")
                    conn.close()

    st.divider()

    # --- 删除场地 ---
    conn = sqlite3.connect(DB_NAME)
    venues_list = pd.read_sql_query("SELECT name, map_url FROM venues", conn)
    
    if not venues_list.empty:
        st.subheader("🗑️ 删除场地")
        venue_to_delete = st.selectbox("选择要删除的场地", ["--请选择--"] + venues_list['name'].tolist())
        if st.button("删除选中的场地", type="primary"):
            if venue_to_delete != "--请选择--":
                conn.execute("DELETE FROM venues WHERE name=?", (venue_to_delete,))
                conn.commit()
                st.success(f"已删除场地: {venue_to_delete}")
                st.rerun() # 刷新页面更新列表
            else:
                st.warning("请先选择一个场地")
                
        st.subheader("📍 已保存的场地列表")
        for index, row in venues_list.iterrows():
            st.markdown(f"- **{row['name']}** ([查看地图]({row['map_url']}))")
    else:
        st.info("暂无保存的场地。")
    conn.close()

# ================= 页面：管理成员 =================
elif menu == "👥 管理成员":
    st.title("👥 管理球队成员")
    
    # --- 添加成员 ---
    with st.form("add_member_form"):
        new_member = st.text_input("输入要添加的同事姓名")
        if st.form_submit_button("添加成员"):
            if new_member:
                conn = sqlite3.connect(DB_NAME)
                try:
                    conn.execute("INSERT INTO members (name) VALUES (?)", (new_member,))
                    conn.commit()
                    st.success(f"✅ 成功添加成员: {new_member}")
                except sqlite3.IntegrityError:
                    st.error("⚠️ 该成员已存在！")
                conn.close()
            else:
                st.error("姓名不能为空！")
                
    st.divider()
    
    # --- 删除成员 ---
    conn = sqlite3.connect(DB_NAME)
    current_members = pd.read_sql_query("SELECT name FROM members", conn)
    
    if not current_members.empty:
        st.subheader("🗑️ 删除成员")
        member_to_delete = st.selectbox("选择要删除的成员", ["--请选择--"] + current_members['name'].tolist())
        if st.button("删除选中的成员", type="primary"):
            if member_to_delete != "--请选择--":
                conn.execute("DELETE FROM members WHERE name=?", (member_to_delete,))
                # 同时删除该成员所有的报名记录
                conn.execute("DELETE FROM registrations WHERE member_name=?", (member_to_delete,))
                conn.commit()
                st.success(f"已删除成员: {member_to_delete}")
                st.rerun() # 刷新页面
            else:
                st.warning("请先选择一个成员")
                
        st.subheader("🏃 当前名单")
        for name in current_members['name']:
            st.write(f"- {name}")
    else:
        st.info("目前没有成员。")
    conn.close()
