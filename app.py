import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# 设置网页标题和图标
st.set_page_config(page_title="周末足球俱乐部", page_icon="⚽", layout="centered")

# ================= 辅助函数：获取 Google 地图名称 =================
def fetch_venue_name(url):
    """尝试从 Google 地图链接中抓取场地名称"""
    try:
        # 伪装成浏览器请求
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string if soup.title else ""
        # Google地图的网页标题通常是 "地点名称 - Google Maps"，我们把后缀去掉
        name = title.replace(" - Google Maps", "").replace("Google Maps", "").strip()
        if name and "Sign in" not in name:
            return name
        return None
    except Exception as e:
        return None

# ================= 数据库设置 =================
def init_db():
    conn = sqlite3.connect('football.db')
    c = conn.cursor()
    # 成员表
    c.execute('''CREATE TABLE IF NOT EXISTS members (name TEXT UNIQUE)''')
    # 场地表 (新增)
    c.execute('''CREATE TABLE IF NOT EXISTS venues 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  name TEXT UNIQUE, 
                  map_url TEXT)''')
    # 活动表 (修改了时间字段)
    c.execute('''CREATE TABLE IF NOT EXISTS events 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  event_datetime TEXT, 
                  venue_name TEXT, 
                  map_url TEXT)''')
    # 报名表
    c.execute('''CREATE TABLE IF NOT EXISTS registrations 
                 (event_id INTEGER, 
                  member_name TEXT, 
                  UNIQUE(event_id, member_name))''')
    conn.commit()
    conn.close()

init_db()

# ================= 侧边栏导航 =================
st.sidebar.title("⚽ 菜单栏")
menu = st.sidebar.radio("请选择操作", ["🏠 主页 - 下一场比赛", "📅 发布新比赛", "👥 管理成员", "🏟️ 管理球场"])

# ================= 页面：主页 =================
if menu == "🏠 主页 - 下一场比赛":
    st.title("⚽ 周末足球俱乐部")
    
    conn = sqlite3.connect('football.db')
    event_df = pd.read_sql_query("SELECT * FROM events ORDER BY id DESC LIMIT 1", conn)
    
    if not event_df.empty:
        event_id = event_df['id'][0]
        event_datetime = event_df['event_datetime'][0]
        venue_name = event_df['venue_name'][0]
        map_url = event_df['map_url'][0]
        
        st.subheader("📅 下一次活动信息")
        st.info(f"**⏰ 时间:** {event_datetime}\n\n**🏟️ 场地:** {venue_name}")
        if map_url:
            st.markdown(f"📍 **[点击这里在 Google 地图中打开场地位置]({map_url})**")
            
        st.divider()
        
        # 报名区块
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
                        st.success(f"{selected_member} 报名成功！期待你的加入！")
                    conn.commit()
                    st.rerun()
        else:
            st.warning("目前没有成员，请先到“管理成员”页面添加同事！")
            
        # 统计人数区块
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
    
    conn = sqlite3.connect('football.db')
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
                # 拼接日期和时间
                datetime_str = f"{event_date.strftime('%Y-%m-%d')} {event_time.strftime('%H:%M')}"
                # 获取选中场地的地图链接
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
    
    # 自动获取并添加模块
    st.subheader("✨ 自动识别并添加")
    st.write("输入 Google 地图链接（例如分享链接），系统将尝试自动获取场地名称。")
    auto_url = st.text_input("Google 地图链接", key="auto_url")
    
    if st.button("智能抓取并保存", type="primary"):
        if auto_url:
            with st.spinner("正在从 Google 地图获取场地信息..."):
                venue_name = fetch_venue_name(auto_url)
                if venue_name:
                    conn = sqlite3.connect('football.db')
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO venues (name, map_url) VALUES (?, ?)", (venue_name, auto_url))
                        conn.commit()
                        st.success(f"✅ 成功添加场地：**{venue_name}**")
                    except sqlite3.IntegrityError:
                        st.error("⚠️ 该场地名称已存在数据库中！")
                    conn.close()
                else:
                    st.error("❌ 无法自动获取场地名称（可能是网络或 Google 的防爬限制）。请使用下方手动添加功能。")
        else:
            st.warning("请先输入链接！")

    st.divider()
    
    # 手动添加模块 (作为备用方案)
    with st.expander("🛠️ 如果自动获取失败，点击这里手动添加"):
        with st.form("manual_venue_form"):
            manual_name = st.text_input("手动输入场地名称")
            manual_url = st.text_input("手动输入地图链接")
            if st.form_submit_button("手动保存场地"):
                if manual_name and manual_url:
                    conn = sqlite3.connect('football.db')
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO venues (name, map_url) VALUES (?, ?)", (manual_name, manual_url))
                        conn.commit()
                        st.success(f"✅ 成功手动添加场地：{manual_name}")
                    except sqlite3.IntegrityError:
                        st.error("⚠️ 该场地名称已存在！")
                    conn.close()
                else:
                    st.error("名称和链接都不能为空！")

    # 显示已有场地
    st.divider()
    st.subheader("已保存的场地列表")
    conn = sqlite3.connect('football.db')
    venues_list = pd.read_sql_query("SELECT name, map_url FROM venues", conn)
    if not venues_list.empty:
        for index, row in venues_list.iterrows():
            st.markdown(f"📍 **{row['name']}** - [查看地图]({row['map_url']})")
    else:
        st.info("暂无保存的场地。")
    conn.close()

# ================= 页面：管理成员 =================
elif menu == "👥 管理成员":
    st.title("👥 添加球队成员")
    
    with st.form("add_member_form"):
        new_member = st.text_input("输入同事的姓名或昵称")
        submit_member = st.form_submit_button("添加成员")
        
        if submit_member:
            if new_member:
                conn = sqlite3.connect('football.db')
                c = conn.cursor()
                try:
                    c.execute("INSERT INTO members (name) VALUES (?)", (new_member,))
                    conn.commit()
                    st.success(f"✅ 成功添加成员: {new_member}")
                except sqlite3.IntegrityError:
                    st.error("⚠️ 该成员已存在！")
                conn.close()
            else:
                st.error("姓名不能为空！")
                
    st.divider()
    st.subheader("当前名单")
    conn = sqlite3.connect('football.db')
    current_members = pd.read_sql_query("SELECT name FROM members", conn)
    if not current_members.empty:
        for name in current_members['name']:
            st.write(f"🏃 {name}")
    conn.close()
