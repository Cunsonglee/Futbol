import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import urllib.parse
import pytz 

# ================= 1. CONFIGURACIÓN =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="centered")

# --- IMPORTANTE: Tu URL de Google Sheets ---
MAIN_URL = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"
conn = st.connection("gsheets", GSheetsConnection)

def load_data(worksheet):
    try:
        # ttl=0 para asegurar que los votos y registros sean instantáneos
        return conn.read(spreadsheet=MAIN_URL, worksheet=worksheet, ttl=0).dropna(how="all")
    except:
        return pd.DataFrame()

def save_data(worksheet, df):
    try:
        conn.create(spreadsheet=MAIN_URL, worksheet=worksheet, data=df)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# --- Obtener los próximos 4 sábados automáticamente ---
def get_next_saturdays(n=4):
    saturdays = []
    d = datetime.now()
    while len(saturdays) < n:
        d += timedelta(days=1)
        if d.weekday() == 5: # 5 = Sábado
            saturdays.append(d.strftime('%Y-%m-%d'))
    return saturdays

# ================= 2. INTERFAZ =================
st.title("⚽ Gestión de Fútbol")

tab_inicio, tab_votar, tab_publicar, tab_campos, tab_miembros, tab_historial = st.tabs([
    "🏠 Inicio", "🗳️ Votar", "📅 Publicar", "🥅 Campos", "🤼‍♂️ Miembros", "⏳ Historial"
])

# --- TAB 1: INICIO (Partidos Confirmados) ---
with tab_inicio:
    st.subheader("Partidos Programados")
    df_e = load_data("Eventos")
    df_c = load_data("Campos")
    df_m = load_data("Miembros")
    
    if not df_e.empty:
        tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        activos = df_e[df_e['datetime'] >= now].sort_values("datetime")
        
        if not activos.empty:
            for idx, event in activos.iterrows():
                with st.expander(f"📌 {event['datetime']} @ {event['venue']}", expanded=True):
                    v_match = df_c[df_c['name'] == event['venue']] if not df_c.empty else pd.DataFrame()
                    url_map = v_match.iloc[0]['map_url'] if not v_match.empty else "#"
                    
                    st.write(f"📍 **Lugar:** [{event['venue']}]({url_map})")
                    
                    players = [p.strip() for p in str(event['players']).split(",") if p.strip() and str(event['players']) != "nan"]
                    st.write(f"🏃 **Inscritos ({len(players)}):** {', '.join(players)}")
                    
                    # Inscripción
                    non_signed = [m for m in df_m['name'].tolist() if m not in players] if not df_m.empty else []
                    c_sel, c_btn = st.columns([3, 1])
                    p_name = c_sel.selectbox("Tu nombre:", ["-- Seleccionar --"] + non_signed, key=f"ins_{idx}")
                    if c_btn.button("Inscribirme", key=f"btn_{idx}"):
                        if p_name != "-- Seleccionar --":
                            players.append(p_name)
                            df_e.at[idx, 'players'] = ",".join(players)
                            save_data("Eventos", df_e)
                            st.rerun()
        else:
            st.info("No hay partidos programados. ¡Vota para organizar uno!")

# --- TAB 2: VOTAR (Elegir Sábado y Turno) ---
with tab_votar:
    st.subheader("Votación para el Sábado")
    df_v = load_data("Votos")
    df_m = load_data("Miembros")
    
    # 获取接下来的周六
    sabs = get_next_saturdays()
    
    # 使用表单包裹投票控件，这样可以一次性提交，减少页面刷新次数
    with st.form("form_votacion"):
        v_fecha = st.selectbox("Selecciona el día (Sábado):", sabs)
        v_turno = st.radio("Selecciona el turno:", ["Mañana", "Tarde"])
        
        # 这里的 key 必须唯一
        lista_miembros = ["-- Seleccionar --"] + (df_m['name'].tolist() if not df_m.empty else [])
        v_user = st.selectbox("¿Quién eres?", lista_miembros)
        
        submit_voto = st.form_submit_button("Enviar Voto")
        
        if submit_voto:
            if v_user != "-- Seleccionar --":
                # 检查是否已经投过票了
                exists = df_v[(df_v['fecha'] == v_fecha) & (df_v['turno'] == v_turno) & (df_v['usuario'] == v_user)]
                
                if exists.empty:
                    new_v = pd.DataFrame([{"fecha": v_fecha, "turno": v_turno, "usuario": v_user}])
                    df_v = pd.concat([df_v, new_v], ignore_index=True)
                    save_data("Votos", df_v)
                    st.success(f"¡Gracias {v_user}! Tu voto ha sido registrado para el {v_fecha} por la {v_turno}.")
                    # 注意：如果这里用了 st.rerun()，上面的成功提示会闪现消失。
                    # 建议不在这里写 rerun，或者让用户手动刷新查看结果。
                else:
                    st.warning(f"Atención: {v_user}, ya has votado por este turno anteriormente.")
            else:
                st.error("Por favor, selecciona tu nombre antes de votar.")

    st.divider()
    st.write("📊 **Estado actual de las votaciones:**")
    
    # 重新加载数据以显示最新结果
    df_v_display = load_data("Votos")
    if not df_v_display.empty:
        # 统计每个日期时段的票数
        res = df_v_display.groupby(['fecha', 'turno']).size().reset_index(name='count')
        for _, r in res.iterrows():
            # 这里的颜色根据人数变化
            color = "green" if r['count'] >= 10 else "orange"
            st.write(f"📅 **{r['fecha']} ({r['turno']})**")
            st.markdown(f"Progreso: :{color}[{r['count']} / 10 votos]")
            st.progress(min(r['count'] / 10, 1.0))

# --- TAB 3: PUBLICAR (Solo si hay >= 10 votos) ---
with tab_publicar:
    st.subheader("Confirmar y Publicar Partido")
    df_v = load_data("Votos")
    df_c = load_data("Campos")
    
    if not df_v.empty:
        summary = df_v.groupby(['fecha', 'turno']).size().reset_index(name='count')
        ready = summary[summary['count'] >= 10]
        
        if ready.empty:
            st.warning("Aún ningún turno ha llegado a 10 personas.")
        else:
            with st.form("form_pub"):
                options = [f"{r['fecha']} ({r['turno']})" for _, r in ready.iterrows()]
                selected_voto = st.selectbox("Turnos listos:", options)
                
                final_time = st.time_input("Hora de encuentro:")
                final_venue = st.selectbox("Seleccionar Campo:", df_c['name'].tolist() if not df_c.empty else [])
                
                if st.form_submit_button("🚀 Publicar Partido"):
                    f_date = selected_voto.split(" (")[0]
                    dt_str = f"{f_date} {final_time.strftime('%H:%M')}"
                    
                    df_e = load_data("Eventos")
                    new_match = pd.DataFrame([{"datetime": dt_str, "venue": final_venue, "players": ""}])
                    df_e = pd.concat([df_e, new_match], ignore_index=True)
                    save_data("Eventos", df_e)
                    st.success("¡Partido publicado!")
                    st.rerun()

# --- TAB 4: CAMPOS ---
with tab_campos:
    st.subheader("Gestión de Campos")
    df_c = load_data("Campos")
    with st.form("add_c"):
        c_url = st.text_input("Link Google Maps:")
        if st.form_submit_button("Añadir Campo"):
            try:
                h = {'User-Agent': 'Mozilla/5.0'}
                res = requests.get(c_url, headers=h, timeout=5)
                name = BeautifulSoup(res.text, 'html.parser').title.string.replace(" - Google Maps", "").strip()
                new_c = pd.DataFrame([{"name": name, "map_url": c_url}])
                df_c = pd.concat([df_c, new_c], ignore_index=True)
                save_data("Campos", df_c)
                st.rerun()
            except: st.error("Error al obtener nombre.")
    
    for i, r in df_c.iterrows():
        c1, c2 = st.columns([4,1])
        c1.markdown(f"🏟️ [{r['name']}]({r['map_url']})")
        if c2.button("🗑️", key=f"dc_{i}"):
            df_c = df_c.drop(i)
            save_data("Campos", df_c)
            st.rerun()

# --- TAB 5: MIEMBROS ---
with tab_miembros:
    st.subheader("Miembros")
    df_m = load_data("Miembros")
    with st.form("add_m"):
        m_name = st.text_input("Nombre:")
        if st.form_submit_button("Añadir"):
            df_m = pd.concat([df_m, pd.DataFrame([{"name": m_name}])], ignore_index=True)
            save_data("Miembros", df_m)
            st.rerun()
    for i, r in df_m.iterrows():
        c1, c2 = st.columns([4,1])
        c1.write(f"👤 {r['name']}")
        if c2.button("🗑️", key=f"dm_{i}"):
            df_m = df_m.drop(i)
            save_data("Miembros", df_m)
            st.rerun()

# --- TAB 6: HISTORIAL (Partidos pasados) ---
with tab_historial:
    st.subheader("Historial de Partidos")
    df_e = load_data("Eventos")
    
    if not df_e.empty:
        tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        # Partidos con fecha menor a la actual
        pasados = df_e[df_e['datetime'] < now].sort_values("datetime", ascending=False)
        
        if not pasados.empty:
            for i, row in pasados.iterrows():
                with st.expander(f"📅 {row['datetime']} - {row['venue']}"):
                    p_list = [p.strip() for p in str(row['players']).split(",") if p.strip() and str(row['players']) != "nan"]
                    st.write(f"**Participantes ({len(p_list)}):**")
                    st.write(", ".join(p_list))
        else:
            st.info("No hay partidos en el historial todavía.")
