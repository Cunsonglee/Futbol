import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse
import pytz

# ================= 1. CONFIGURACIÓN BÁSICA =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="centered")

MAIN_URL = "https://docs.google.com/spreadsheets/d/11mn_aczvx1l1Xxo8bmUjUHpJFRbX4dWyJDF1o5G_TK4/edit"

# ================= ⚙️ CONFIGURACIÓN DE ADMINISTRADORES =================
# ➡️ Añade aquí los nombres EXACTOS de los administradores (igual que en la hoja "Miembros")
ADMINS = ["Carlos", "Maria"]  # ← CAMBIA ESTOS NOMBRES

conn = st.connection("gsheets", type=GSheetsConnection)

# ================= 2. AUTENTICACIÓN POR URL =================
def get_current_user():
    """Lee el parámetro ?user=Nombre de la URL"""
    params = st.query_params
    user = params.get("user", "").strip()
    return user if user else None

def is_admin(user):
    return user in ADMINS

current_user = get_current_user()

# --- Pantalla de acceso si no hay parámetro user ---
if not current_user:
    st.title("⚽ Club de Fútbol")
    st.divider()
    st.warning("⚠️ Necesitas un enlace personalizado para acceder.")
    st.info(
        "**¿Cómo funciona?**\n\n"
        "Cada miembro tiene su propio enlace:\n\n"
        "`https://tu-app.streamlit.app/?user=TuNombre`\n\n"
        "Pide al administrador que te envíe tu enlace personal."
    )

    # Panel de admin para generar enlaces (acceso con contraseña maestra)
    with st.expander("🔧 Panel de administrador — generar enlaces"):
        master_pw = st.text_input("Contraseña maestra", type="password")
        if master_pw == "futbol2024":  # ← CAMBIA ESTA CONTRASEÑA
            st.success("✅ Acceso de administrador")
            df_m_temp = conn.read(spreadsheet=MAIN_URL, worksheet="Miembros", ttl=60).dropna(how="all")
            if not df_m_temp.empty:
                base_url = st.text_input("URL base de tu app", placeholder="https://tu-app.streamlit.app")
                if base_url:
                    st.write("**Enlaces personales:**")
                    for _, row in df_m_temp.iterrows():
                        name = row['name']
                        link = f"{base_url}/?user={urllib.parse.quote(name)}"
                        admin_tag = " 👑 Admin" if name in ADMINS else ""
                        st.code(f"{name}{admin_tag}: {link}")
    st.stop()

# ================= 3. FUNCIONES DE DATOS =================
def load_sheet_data(worksheet_name):
    try:
        return conn.read(spreadsheet=MAIN_URL, worksheet=worksheet_name, ttl=300).dropna(how="all")
    except Exception as e:
        st.error(f"Error al cargar la pestaña {worksheet_name}: {e}")
        return pd.DataFrame()

def save_sheet_data(worksheet_name, df):
    try:
        conn.create(spreadsheet=MAIN_URL, worksheet=worksheet_name, data=df)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Error al guardar en {worksheet_name}: {e}")

# ================= 4. FUNCIONES AUXILIARES =================
def fetch_venue_name(url):
    try:
        if "/place/" in url:
            part = url.split("/place/")[1].split("/")[0]
            name = urllib.parse.unquote(part).replace("+", " ")
            if name and "@" not in name:
                return name
    except:
        pass
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        name = soup.title.string.replace(" - Google Maps", "").strip()
        return name if name and "Sign in" not in name else None
    except:
        return None

def formatear_precio(is_free, price, num, unit):
    if is_free or is_free == 1:
        return "Gratis"
    try:
        unit_str = "días" if (num > 1 and unit == "día") else (unit + "s" if num > 1 else unit)
        return f"{float(price):.2f} € / {int(num)} {unit_str}"
    except:
        return "No especificado"

# ================= 5. CABECERA CON USUARIO =================
user_display = f"👑 {current_user} (Admin)" if is_admin(current_user) else f"👤 {current_user}"
st.title("⚽ Gestión del Club")
st.caption(f"Conectado como: **{user_display}**")

# ================= 6. TABS (visibles según rol) =================
if is_admin(current_user):
    tab_inicio, tab_publicar, tab_campos, tab_miembros, tab_historial = st.tabs([
        "🏠 Inicio", "📅 Publicar", "🥅 Campos", "🤼‍♂️ Miembros", "⏳ Historial"
    ])
else:
    # Miembro normal: no ve Publicar ni gestión de Campos/Miembros
    tab_inicio, tab_historial = st.tabs(["🏠 Inicio", "⏳ Historial"])
    tab_publicar = None
    tab_campos = None
    tab_miembros = None

# --- TAB: 🏠 Inicio ---
with tab_inicio:
    st.subheader("Próximo Partido")
    df_e = load_sheet_data("Eventos")
    df_m = load_sheet_data("Miembros")
    df_c = load_sheet_data("Campos")

    if not df_e.empty and 'datetime' in df_e.columns:
        tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        df_e['datetime'] = df_e['datetime'].astype(str)
        future_events = df_e[df_e['datetime'] >= now].sort_values("datetime")

        if not future_events.empty:
            event = future_events.iloc[0]
            idx = future_events.index[0]

            v_info = df_c[df_c['name'] == event['venue']] if not df_c.empty else pd.DataFrame()
            precio, map_link = "No especificado", "#"
            if not v_info.empty:
                v = v_info.iloc[0]
                precio = formatear_precio(v.get('is_free', 0), v.get('price', 0), v.get('duration_num', 1), v.get('duration_unit', 'hora'))
                map_link = v.get('map_url', '#')

            st.info(f"**⏰ Fecha:** {event['datetime']}\n\n**🏟️ Campo:** [{event['venue']}]({map_link})\n\n**💰 Precio:** {precio}")

            players_str = str(event.get('players', ""))
            current_players = [p.strip() for p in players_str.split(",") if p.strip() and players_str != "nan"]

            st.write("---")
            already_signed = current_user in current_players

            # --- Inscripción del usuario actual ---
            st.subheader("🙋‍♂️ Tu inscripción")
            if already_signed:
                st.success(f"✅ Ya estás inscrito en este partido.")
                if st.button("❌ Cancelar mi inscripción", type="secondary"):
                    current_players.remove(current_user)
                    df_e.at[idx, 'players'] = ",".join(current_players)
                    save_sheet_data("Eventos", df_e)
                    st.rerun()
            else:
                if st.button("✅ Confirmar mi inscripción", type="primary"):
                    current_players.append(current_user)
                    df_e.at[idx, 'players'] = ",".join(current_players)
                    save_sheet_data("Eventos", df_e)
                    st.success(f"¡{current_user} inscrito con éxito!")
                    st.rerun()

            # --- Lista de inscritos (solo lectura para miembros, editable para admins) ---
            st.divider()
            st.write(f"🏃‍♂️ **Inscritos actualmente: {len(current_players)}**")
            for p in current_players:
                c1, c2 = st.columns([5, 1])
                c1.write(f"✅ {p}")
                # Admins pueden eliminar a cualquiera, miembros solo a sí mismos
                if is_admin(current_user) or p == current_user:
                    if c2.button("❌", key=f"del_{p}"):
                        current_players.remove(p)
                        df_e.at[idx, 'players'] = ",".join(current_players)
                        save_sheet_data("Eventos", df_e)
                        st.rerun()
        else:
            st.info("No hay partidos programados próximamente.")
    else:
        st.info("No hay eventos disponibles.")

# --- TAB: 📅 Publicar (solo admins) ---
if tab_publicar is not None:
    with tab_publicar:
        st.subheader("Programar Nuevo Partido")
        df_c = load_sheet_data("Campos")
        if df_c.empty:
            st.warning("Por favor, añade primero un campo en la pestaña 'Campos'.")
        else:
            with st.form("pub_form"):
                d = st.date_input("Fecha")
                t = st.time_input("Hora")
                venue = st.selectbox("Seleccionar Campo", df_c['name'].tolist())
                if st.form_submit_button("Publicar Partido"):
                    dt_str = f"{d.strftime('%Y-%m-%d')} {t.strftime('%H:%M')}"
                    df_e = load_sheet_data("Eventos")
                    new_row = pd.DataFrame([{"datetime": dt_str, "venue": venue, "players": ""}])
                    df_e = pd.concat([df_e, new_row], ignore_index=True)
                    save_sheet_data("Eventos", df_e)
                    st.success("¡Partido publicado con éxito!")
                    st.rerun()

# --- TAB: 🥅 Campos (solo admins) ---
if tab_campos is not None:
    with tab_campos:
        st.subheader("Gestión de Campos de Fútbol")
        df_c = load_sheet_data("Campos")
        with st.form("campo_form"):
            u = st.text_input("Enlace de Google Maps")
            free = st.checkbox("Campo gratuito")
            col1, col2, col3 = st.columns(3)
            price = col1.number_input("Precio", min_value=0.0)
            num = col2.number_input("Cantidad", min_value=1, value=1)
            unit = col3.selectbox("Unidad", ["hora", "día", "minuto"])
            if st.form_submit_button("Extraer Nombre y Guardar"):
                if u:
                    with st.spinner("Buscando nombre del campo..."):
                        name = fetch_venue_name(u)
                        if name:
                            new_c = pd.DataFrame([{"name": name, "map_url": u, "is_free": int(free), "price": price, "duration_num": num, "duration_unit": unit}])
                            df_c = pd.concat([df_c, new_c], ignore_index=True)
                            save_sheet_data("Campos", df_c)
                            st.success(f"Campo añadido: {name}")
                            st.rerun()
                        else:
                            st.error("No se pudo identificar el nombre del lugar.")

        st.write("---")
        st.write("### Lista de Campos")
        if not df_c.empty:
            for i, row in df_c.iterrows():
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"🏟️ **[{row['name']}]({row['map_url']})**")
                if c2.button("Eliminar", key=f"c_{i}"):
                    df_c = df_c.drop(i).reset_index(drop=True)
                    save_sheet_data("Campos", df_c)
                    st.rerun()

# --- TAB: 🤼‍♂️ Miembros (solo admins) ---
if tab_miembros is not None:
    with tab_miembros:
        st.subheader("Lista de Miembros")
        df_m = load_sheet_data("Miembros")
        with st.form("m_form"):
            name = st.text_input("Nombre del nuevo miembro")
            if st.form_submit_button("Añadir Miembro"):
                if name:
                    df_m = pd.concat([df_m, pd.DataFrame([{"name": name}])], ignore_index=True)
                    save_sheet_data("Miembros", df_m)
                    st.success(f"¡{name} añadido!")
                    st.rerun()

        st.write(f"Total de miembros: {len(df_m)}")
        for i, row in df_m.iterrows():
            c1, c2 = st.columns([4, 1])
            admin_tag = " 👑" if row['name'] in ADMINS else ""
            c1.write(f"👤 {row['name']}{admin_tag}")
            if c2.button("Eliminar", key=f"m_{i}"):
                df_m = df_m.drop(i).reset_index(drop=True)
                save_sheet_data("Miembros", df_m)
                st.rerun()

# --- TAB: ⏳ Historial ---
with tab_historial:
    st.subheader("Historial de Partidos Pasados")
    df_e = load_sheet_data("Eventos")
    if not df_e.empty:
        tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        past = df_e[df_e['datetime'] < now].sort_values("datetime", ascending=False)
        if not past.empty:
            for _, row in past.iterrows():
                with st.expander(f"📅 {row['datetime']} - {row['venue']}"):
                    p_list = str(row['players']).split(",")
                    n_players = len([x for x in p_list if x.strip() and x != "nan"])
                    participated = "✅ Participaste" if current_user in p_list else "❌ No participaste"
                    st.write(f"**{participated}** · Participantes ({n_players}): {row['players']}")
        else:
            st.info("No hay partidos en el historial.")
