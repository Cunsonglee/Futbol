import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# 设置网页标题和图标
st.set_page_config(page_title="周末足球俱乐部", page_icon="⚽", layout="centered")

# ================= 数据库设置 =================
def init_db():
    conn = sqlite3.connect('football.db')
    c = conn.cursor()
    # 成员表
    c.execute('''CREATE TABLE IF NOT EXISTS members (name TEXT UNIQUE)''')
    # 活动表
    c.execute('''CREATE TABLE IF NOT EXISTS events 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  event_date TEXT, 
                  venue TEXT, 
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
menu = st.sidebar.radio("请选择操作", ["🏠 主页 - 下一场比赛", "📅 管理活动", "👥 管理成员"])

# ================= 页面：主页 =================
if menu == "🏠 主页 - 下一场比赛":
    st.title("⚽ 周末足球俱乐部")
    
    conn = sqlite3.connect('football.db')
    # 获取最新的一场比赛
    event_df = pd.read_sql_query("SELECT * FROM events ORDER BY event_date DESC LIMIT 1", conn)
    
    if not event_df.empty:
        event_id = event_df['id'][0]
        event_date = event_df['event_date'][0]
        venue = event_df['venue'][0]
        map_url = event_df['map_url'][0]
        
        st.subheader("📅 下一次活动信息")
        st.info(f"**时间:** {event_date}\n\n**场地:** {venue}")
        if map_url:
            st.markdown(f"📍 **[点击这里在 Google 地图中查看场地位置]({map_url})**")
            
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
                    # 检查是否已经报名
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
        st.info("目前没有安排任何比赛。请到“管理活动”页面添加下一场比赛。")
    conn.close()

# ================= 页面：管理活动 =================
elif menu == "📅 管理活动":
    st.title("📅 添加新比赛")
    
    with st.form("add_event_form"):
        event_date = st.text_input("比赛时间 (例如: 2026-05-02 周六 下午3点)")
        venue = st.text_input("场地名称 (例如: 城市中心足球场 3号场)")
        map_url = st.text_input("Google 地图链接 (粘贴 URL)")
        
        submit_event = st.form_submit_button("发布比赛")
        
        if submit_event:
            if event_date and venue:
                conn = sqlite3.connect('football.db')
                c = conn.cursor()
                c.execute("INSERT INTO events (event_date, venue, map_url) VALUES (?, ?, ?)", 
                          (event_date, venue, map_url))
                conn.commit()
                conn.close()
                st.success("✅ 比赛发布成功！去主页看看吧。")
            else:
                st.error("时间和场地名称不能为空！")

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
            st.write(f"⚽ {name}")
    conn.close()
