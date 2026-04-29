import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse

# Configuración de la página (设置网页标题和图标)
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="centered")

# ================= Funciones Auxiliares (辅助函数) =================
def fetch_venue_name(url):
    """Extraer nombre de la URL o intentar obtener el título de la página"""
    try:
        if "/place/" in url:
            part = url.split("/place/")[1].split("/")[0]
            name = urllib.parse.unquote(part).replace("+", " ")
            if name and "@" not in name:
                return name
    except Exception:
        pass

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

def formatear_precio(is_free, price, num, unit):
    """Formatear el texto del precio (处理免费和价格单位的复数显示)"""
    if is_free:
        return "Gratis"
    else:
        unit_str = unit
        if num > 1:
            unit_str = "días" if unit == "día" else unit + "s"
        return f"{price:.2f} € / {num} {unit_str}"

# ================= Configuración de la Base de Datos (数据库设置 V3) =================
DB_NAME = 'football_v4.db' 

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS members (name TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS venues 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  name TEXT UNIQUE, 
                  map_url TEXT,
                  is_free INTEGER,
                  price REAL,
                  duration_num INTEGER,
                  duration_unit TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS events 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, event_datetime TEXT, venue_name TEXT, map_url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS registrations 
                 (event_id INTEGER, member_name TEXT, UNIQUE(event_id, member_name))''')
    conn.commit()
    conn.close()

init_db()

# ================= Menú Lateral (侧边栏导航) =================
st.sidebar.title("⚽ Menú")
menu = st.sidebar.radio("Seleccione una opción", 
                        ["🏠 Inicio", 
                         "📅 Publicar Partido", 
                         "🏟️ Gestionar Campos", 
                         "👥 Gestionar Miembros", 
                         "⏳ Historial"])

# ================= Página: Inicio (主页 - 下一场比赛) =================
if menu == "🏠 Inicio":
    st.title("⚽ Club de Fútbol de Fin de Semana")
    
    conn = sqlite3.connect(DB_NAME)
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    query = "SELECT * FROM events WHERE event_datetime >= ? ORDER BY event_datetime ASC LIMIT 1"
    event_df = pd.read_sql_query(query, conn, params=(current_time,))
    
    if not event_df.empty:
        event_id = event_df['id'][0]
        event_datetime = event_df['event_datetime'][0]
        venue_name = event_df['venue_name'][0]
        map_url = event_df['map_url'][0]
        
        venue_info = pd.read_sql_query("SELECT is_free, price, duration_num, duration_unit FROM venues WHERE name=?", conn, params=(venue_name,))
        texto_precio = "No especificado"
        if not venue_info.empty:
            v_free = bool(venue_info['is_free'][0])
            v_price = venue_info['price'][0]
            v_num = venue_info['duration_num'][0]
            v_unit = venue_info['duration_unit'][0]
            texto_precio = formatear_precio(v_free, v_price, v_num, v_unit)
        
        st.subheader("📅 Información del Próximo Partido")
        st.info(f"**⏰ Fecha y Hora:** {event_datetime}\n\n**🏟️ Campo:** {venue_name}\n\n**💰 Precio:** {texto_precio}")
        
        if map_url:
            st.markdown(f"📍 **[Haz clic aquí para abrir en Google Maps]({map_url})**")
            
        st.divider()
        
        st.subheader("🙋‍♂️ Zona de Inscripción")
        # 🔥 修改点：按字母 A-Z 升序读取成员名单
        members_df = pd.read_sql_query("SELECT name FROM members ORDER BY name ASC", conn)
        
        if not members_df.empty:
            member_list = members_df['name'].tolist()
            selected_member = st.selectbox("Selecciona tu nombre para inscribirte:", ["-- Seleccionar --"] + member_list)
            
            if st.button("Inscribirse / Cancelar Inscripción", type="primary"):
                if selected_member == "-- Seleccionar --":
                    st.warning("¡Por favor, selecciona tu nombre primero!")
                else:
                    c = conn.cursor()
                    c.execute("SELECT * FROM registrations WHERE event_id=? AND member_name=?", (int(event_id), selected_member))
                    if c.fetchone():
                        c.execute("DELETE FROM registrations WHERE event_id=? AND member_name=?", (int(event_id), selected_member))
                        st.warning(f"Se ha cancelado la inscripción de {selected_member}.")
                    else:
                        c.execute("INSERT INTO registrations (event_id, member_name) VALUES (?, ?)", (int(event_id), selected_member))
                        st.success(f"¡{selected_member} se ha inscrito con éxito!")
                    conn.commit()
                    st.rerun()
        else:
            st.warning("No hay miembros actualmente. ¡Añade compañeros en 'Gestionar Miembros'!")
            
        st.divider()
        regs_df = pd.read_sql_query(f"SELECT member_name FROM registrations WHERE event_id={event_id}", conn)
        st.subheader(f"🏃‍♂️ Total de inscritos: {len(regs_df)} personas")
        
        if not regs_df.empty:
            for index, row in regs_df.iterrows():
                st.write(f"✅ {row['member_name']}")
        else:
            st.write("Aún no hay inscritos. ¡Sé el primero!")
            
    else:
        st.info("Actualmente no hay partidos programados. Ve a 'Publicar Partido' para organizar uno.")
    conn.close()

# ================= Página: Publicar Partido (发布新比赛) =================
elif menu == "📅 Publicar Partido":
    st.title("📅 Programar Siguiente Partido")
    
    conn = sqlite3.connect(DB_NAME)
    venues_df = pd.read_sql_query("SELECT * FROM venues", conn)
    
    if venues_df.empty:
        st.warning("⚠️ Todavía no hay campos guardados. ¡Ve a '🏟️ Gestionar Campos' para añadir uno!")
    else:
        venue_list = venues_df['name'].tolist()
        
        with st.form("add_event_form"):
            col1, col2 = st.columns(2)
            with col1:
                event_date = st.date_input("Fecha del partido")
            with col2:
                event_time = st.time_input("Hora del partido")
                
            selected_venue = st.selectbox("Seleccionar campo", venue_list)
            submit_event = st.form_submit_button("Publicar Partido")
            
            if submit_event:
                datetime_str = f"{event_date.strftime('%Y-%m-%d')} {event_time.strftime('%H:%M')}"
                map_url = venues_df.loc[venues_df['name'] == selected_venue, 'map_url'].values[0]
                
                c = conn.cursor()
                c.execute("INSERT INTO events (event_datetime, venue_name, map_url) VALUES (?, ?, ?)", 
                          (datetime_str, selected_venue, map_url))
                conn.commit()
                st.success("✅ ¡Partido publicado con éxito! Revisa la pestaña de Inicio.")
    conn.close()

# ================= Página: Gestionar Campos (管理球场) =================
elif menu == "🏟️ Gestionar Campos":
    st.title("🏟️ Campos de Fútbol")
    
    st.subheader("✨ Añadir nuevo campo")
    auto_url = st.text_input("Introduce el enlace de Google Maps", placeholder="https://www.google.com/maps/place/...")
    
    st.markdown("💰 **Configuración de Precio**")
    auto_is_free = st.checkbox("Gratis (Gratuito)", key="auto_free")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        auto_price = st.number_input("Precio (€)", min_value=0.0, step=1.0, format="%.2f", disabled=auto_is_free, key="auto_price")
    with col2:
        auto_num = st.selectbox("Cantidad", list(range(1, 13)), disabled=auto_is_free, key="auto_num")
    with col3:
        auto_unit = st.selectbox("Unidad", ["minuto", "hora", "día"], disabled=auto_is_free, key="auto_unit")

    if st.button("Extraer y guardar automáticamente", type="primary"):
        if auto_url:
            with st.spinner("Obteniendo información del campo..."):
                venue_name = fetch_venue_name(auto_url)
                if venue_name:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO venues (name, map_url, is_free, price, duration_num, duration_unit) VALUES (?, ?, ?, ?, ?, ?)", 
                                  (venue_name, auto_url, int(auto_is_free), auto_price, auto_num, auto_unit))
                        conn.commit()
                        st.success(f"✅ Campo añadido con éxito: **{venue_name}**")
                    except sqlite3.IntegrityError:
                        st.error("⚠️ ¡Este nombre de campo ya existe!")
                    finally:
                        conn.close()
                else:
                    st.error("❌ No se pudo obtener automáticamente, usa la opción manual abajo.")
        else:
            st.warning("¡Por favor, introduce el enlace primero!")

    with st.expander("🛠️ Añadir campo manualmente"):
        manual_name = st.text_input("Nombre del campo (Manual)")
        manual_url = st.text_input("Enlace del mapa (Manual)")
        
        st.markdown("💰 **Configuración de Precio**")
        man_is_free = st.checkbox("Gratis (Gratuito)", key="man_free")
        
        col4, col5, col6 = st.columns(3)
        with col4:
            man_price = st.number_input("Precio (€)", min_value=0.0, step=1.0, format="%.2f", disabled=man_is_free, key="man_price")
        with col5:
            man_num = st.selectbox("Cantidad", list(range(1, 13)), disabled=man_is_free, key="man_num")
        with col6:
            man_unit = st.selectbox("Unidad", ["minuto", "hora", "día"], disabled=man_is_free, key="man_unit")
            
        if st.button("Guardar campo manualmente"):
            if manual_name and manual_url:
                conn = sqlite3.connect(DB_NAME)
                try:
                    conn.execute("INSERT INTO venues (name, map_url, is_free, price, duration_num, duration_unit) VALUES (?, ?, ?, ?, ?, ?)", 
                                 (manual_name, manual_url, int(man_is_free), man_price, man_num, man_unit))
                    conn.commit()
                    st.success("¡Añadido con éxito!")
                except sqlite3.IntegrityError:
                    st.error("El nombre ya existe")
                conn.close()
            else:
                st.error("El nombre y el enlace son obligatorios.")

    st.divider()

    conn = sqlite3.connect(DB_NAME)
    venues_list = pd.read_sql_query("SELECT * FROM venues", conn)
    
    if not venues_list.empty:
        st.subheader("🗑️ Eliminar campo")
        venue_to_delete = st.selectbox("Selecciona el campo a eliminar", ["--Seleccionar--"] + venues_list['name'].tolist())
        if st.button("Eliminar campo seleccionado", type="primary"):
            if venue_to_delete != "--Seleccionar--":
                conn.execute("DELETE FROM venues WHERE name=?", (venue_to_delete,))
                conn.commit()
                st.success(f"Campo eliminado: {venue_to_delete}")
                st.rerun()
            else:
                st.warning("Por favor, selecciona un campo primero")
                
        st.subheader("📍 Lista de campos guardados")
        for index, row in venues_list.iterrows():
            precio_str = formatear_precio(bool(row['is_free']), row['price'], row['duration_num'], row['duration_unit'])
            st.markdown(f"- **{row['name']}** | 💰 {precio_str} | ([Ver mapa]({row['map_url']}))")
    else:
        st.info("No hay campos guardados.")
    conn.close()

# ================= Página: Gestionar Miembros (管理成员) =================
elif menu == "👥 Gestionar Miembros":
    st.title("👥 Gestionar Miembros del Equipo")
    
    with st.form("add_member_form"):
        new_member = st.text_input("Introduce el nombre del compañero")
        if st.form_submit_button("Añadir miembro"):
            if new_member:
                conn = sqlite3.connect(DB_NAME)
                try:
                    conn.execute("INSERT INTO members (name) VALUES (?)", (new_member,))
                    conn.commit()
                    st.success(f"✅ Miembro añadido con éxito: {new_member}")
                except sqlite3.IntegrityError:
                    st.error("⚠️ ¡Este miembro ya existe!")
                conn.close()
            else:
                st.error("¡El nombre no puede estar vacío!")
                
    st.divider()
    
    conn = sqlite3.connect(DB_NAME)
    current_members = pd.read_sql_query("SELECT name FROM members ORDER BY name ASC", conn)
    
    if not current_members.empty:
        st.subheader("🗑️ Eliminar miembro")
        member_to_delete = st.selectbox("Selecciona el miembro a eliminar", ["--Seleccionar--"] + current_members['name'].tolist())
        if st.button("Eliminar miembro seleccionado", type="primary"):
            if member_to_delete != "--Seleccionar--":
                conn.execute("DELETE FROM members WHERE name=?", (member_to_delete,))
                conn.execute("DELETE FROM registrations WHERE member_name=?", (member_to_delete,))
                conn.commit()
                st.success(f"Miembro eliminado: {member_to_delete}")
                st.rerun()
            else:
                st.warning("Por favor, selecciona un miembro primero")
                
        # 🔥 修改点：在这里动态计算并显示总人数
        st.subheader(f"🏃 Lista actual (Total: {len(current_members)})")
        for name in current_members['name']:
            st.write(f"- {name}")
    else:
        st.info("No hay miembros actualmente.")
    conn.close()

# ================= Página: Historial (历史记录) =================
elif menu == "⏳ Historial":
    st.title("⏳ Historial de Partidos")
    
    conn = sqlite3.connect(DB_NAME)
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    query = "SELECT * FROM events WHERE event_datetime < ? ORDER BY event_datetime DESC"
    past_events_df = pd.read_sql_query(query, conn, params=(current_time,))
    
    if not past_events_df.empty:
        st.write("Aquí puedes ver los partidos pasados y quiénes participaron:")
        
        for index, row in past_events_df.iterrows():
            event_id = row['id']
            with st.expander(f"📅 {row['event_datetime']} | 🏟️ {row['venue_name']}"):
                regs_df = pd.read_sql_query(f"SELECT member_name FROM registrations WHERE event_id={event_id}", conn)
                
                st.markdown(f"**Total de participantes:** {len(regs_df)}")
                
                if not regs_df.empty:
                    jugadores = regs_df['member_name'].tolist()
                    st.write("Jugadores: " + ", ".join(jugadores))
                else:
                    st.write("Nadie se inscribió en este partido.")
    else:
        st.info("Aún no hay partidos en el historial.")
        
    conn.close()
