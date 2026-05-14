import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import urllib.parse
import pytz
import io
import base64

from googleapiclient.discovery import build
from google.oauth2 import service_account

# ================= 1. CONFIGURACIÓN BÁSICA =================
st.set_page_config(page_title="Club de Fútbol", page_icon="⚽", layout="wide")

# ── GitHub 配置 ──────────────────────────────────────────
GITHUB_TOKEN  = st.secrets["github"]["token"]
GITHUB_REPO   = st.secrets["github"]["repo"]    # "usuario/repo"
GITHUB_BRANCH = st.secrets["github"].get("branch", "main")

CSV_FILES = {
    "Campos":     "Campos.csv",
    "Eventos":    "Eventos.csv",
    "Miembros":   "Miembros.csv",
    "Votaciones": "Votaciones.csv",
}

CSV_DEFAULTS = {
    "Campos":     ["name", "map_url", "is_free", "price", "duration_num", "duration_unit"],
    "Eventos":    ["datetime", "venue", "players"],
    "Miembros":   ["name"],
    "Votaciones": ["Fecha", "Jugadores"],
}

GH_API = "https://api.github.com"
GH_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

def _gh_get_file(filename):
    """获取 GitHub 上文件的内容和 SHA（用于后续更新）"""
    url = f"{GH_API}/repos/{GITHUB_REPO}/contents/{filename}?ref={GITHUB_BRANCH}"
    r = requests.get(url, headers=GH_HEADERS, timeout=15)
    if r.status_code == 404:
        return None, None   # 文件不存在
    r.raise_for_status()
    data = r.json()
    raw  = base64.b64decode(data["content"]).decode("utf-8-sig")
    return raw, data["sha"]

def _gh_put_file(filename, csv_content, sha, commit_msg):
    """在 GitHub 上创建或更新文件"""
    url  = f"{GH_API}/repos/{GITHUB_REPO}/contents/{filename}"
    body = {
        "message": commit_msg,
        "content": base64.b64encode(csv_content.encode("utf-8")).decode("utf-8"),
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        body["sha"] = sha   # 更新已有文件必须带 SHA
    r = requests.put(url, headers=GH_HEADERS, json=body, timeout=15)
    r.raise_for_status()

def _parse_csv(raw_text, worksheet_name):
    """把 CSV 文本解析成 DataFrame"""
    sep = ";" if ";" in raw_text.splitlines()[0] else ","
    df  = pd.read_csv(io.StringIO(raw_text), dtype=str, sep=sep)
    df.columns = [c.strip() for c in df.columns]
    df = df.dropna(how="all").reset_index(drop=True)
    for col in CSV_DEFAULTS.get(worksheet_name, []):
        if col not in df.columns:
            df[col] = ""
    return df

# ── Leer desde GitHub ────────────────────────────────────
def load_sheet_data(worksheet_name, ttl=None):
    filename = CSV_FILES.get(worksheet_name)
    if not filename:
        st.error(f"Hoja desconocida: {worksheet_name}")
        return pd.DataFrame()
    try:
        raw, _ = _gh_get_file(filename)
        if raw is None:
            # Archivo no existe aún → devolver DataFrame vacío
            return pd.DataFrame(columns=CSV_DEFAULTS.get(worksheet_name, []))
        return _parse_csv(raw, worksheet_name)
    except Exception as e:
        st.error(f"Error al leer {filename} desde GitHub: {e}")
        return pd.DataFrame(columns=CSV_DEFAULTS.get(worksheet_name, []))

# ── Guardar en GitHub (commit automático) ────────────────
def save_sheet_data(worksheet_name, df):
    filename = CSV_FILES.get(worksheet_name)
    if not filename:
        st.error(f"Hoja desconocida: {worksheet_name}")
        return
    try:
        _, sha = _gh_get_file(filename)   # necesitamos el SHA para actualizar
        csv_text = df.to_csv(index=False)
        _gh_put_file(
            filename  = filename,
            csv_content = csv_text,
            sha       = sha,
            commit_msg = f"app: actualizar {filename}"
        )
    except Exception as e:
        st.error(f"Error al guardar {filename} en GitHub: {e}")


# ================= 2. FUNCIONES AUXILIARES =================
def fetch_venue_name(url):
    """Extrae el nombre del campo desde un enlace de Google Maps."""
    try:
        if "/place/" in url:
            part = url.split("/place/")[1].split("/")[0]
            name = urllib.parse.unquote(part).replace("+", " ")
            if name and "@" not in name:
                return name
    except:
        pass
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        name = soup.title.string.replace(" - Google Maps", "").strip()
        return name if name and "Sign in" not in name else None
    except:
        return None


def formatear_precio(is_free, price, num, unit):
    """Formatea el precio del campo para mostrarlo."""
    try:
        is_free_bool = str(is_free) in ("1", "True", "true", "GRATIS", "Gratis")
    except:
        is_free_bool = False

    if is_free_bool:
        return "Gratis"
    try:
        num = int(float(num))
        unit_str = "días" if (num > 1 and unit == "día") else (unit + "s" if num > 1 else unit)
        return f"{float(price):.2f} € / {num} {unit_str}"
    except:
        return "No especificado"


def get_calendar_slots_grouped():
    """Lee los slots disponibles desde Google Calendar."""
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
            calendarId=calendar_id,
            timeMin=start_of_week.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        slots_by_date = {}

        for event in events:
            start_info = event.get('start', {})
            end_info   = event.get('end',   {})
            if 'dateTime' in start_info and 'dateTime' in end_info:
                start_dt = datetime.fromisoformat(start_info['dateTime']).astimezone(tz)
                end_dt   = datetime.fromisoformat(end_info['dateTime']).astimezone(tz)
                date_str = start_dt.strftime('%Y-%m-%d')
                s_t, e_t = start_dt.strftime('%H:%M'), end_dt.strftime('%H:%M')
                if s_t == "07:00" and e_t == "13:00":
                    franja = "Mañana"
                elif (s_t == "17:00" and e_t == "23:30") or (s_t == "13:00" and e_t == "23:30"):
                    franja = "Tarde"
                else:
                    franja = f"{s_t}-{e_t}"
            else:
                date_str = start_info.get('date', '')
                franja   = "Todo el día"

            if date_str:
                if date_str not in slots_by_date:
                    slots_by_date[date_str] = []
                slots_by_date[date_str].append(franja)

        return slots_by_date, start_of_week

    except Exception as e:
        st.error(f"Error Calendario: {e}")
        return {}, datetime.now()


# ================= 3. DISEÑO DE INTERFAZ =================
st.title("⚽ Gestión del Club")

tab_inicio, tab_votar, tab_calendario, tab_campos, tab_miembros, tab_historial = st.tabs([
    "🏠 Inicio", "🗳️ Votar", "📅 Calendario", "🥅 Campos", "🤼‍♂️ Miembros", "⏳ Historial"
])

# ─────────────────────────────────────────────────────────
# TAB: 🏠 Inicio
# ─────────────────────────────────────────────────────────
with tab_inicio:
    st.subheader("Próximo Partido Confirmado")
    df_e = load_sheet_data("Eventos")
    if not df_e.empty and 'datetime' in df_e.columns:
        tz  = pytz.timezone('Europe/Madrid')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M')
        future_events = df_e[df_e['datetime'].astype(str) >= now].sort_values("datetime")
        if not future_events.empty:
            event   = future_events.iloc[0]
            players = [p.strip() for p in str(event.get('players', "")).split(",")
                       if p.strip() and str(event.get('players', "")) != "nan"]
            venue_name = event.get('venue', '')
            # Buscar la URL del campo en Campos.csv
            df_c_ini = load_sheet_data("Campos")
            venue_url = ""
            if not df_c_ini.empty and 'name' in df_c_ini.columns and 'map_url' in df_c_ini.columns:
                match = df_c_ini[df_c_ini['name'] == venue_name]
                if not match.empty:
                    venue_url = str(match.iloc[0]['map_url'])
            campo_html = f'<a href="{venue_url}" target="_blank">{venue_name}</a>' if venue_url else venue_name
            st.markdown(
                f"**⏰ Fecha:** {event['datetime']}<br>**🏟️ Campo:** {campo_html}",
                unsafe_allow_html=True
            )
            st.write(f"🏃‍♂️ **Inscritos ({len(players)}):** {', '.join(players)}")
        else:
            st.info("No hay partidos próximos programados.")
    else:
        st.info("No hay partidos próximos programados.")

# ─────────────────────────────────────────────────────────
# TAB: 🗳️ Votar
# ─────────────────────────────────────────────────────────
with tab_votar:
    st.subheader("🗳️ Votación y Registro")

    df_v = load_sheet_data("Votaciones")
    df_m = load_sheet_data("Miembros")
    all_m = sorted(df_m['name'].tolist()) if not df_m.empty and 'name' in df_m.columns else []

    # ── Construir diccionario rápido de votos actuales para mostrar contador ──
    votos_actuales = {}
    if not df_v.empty and 'Fecha' in df_v.columns:
        for _, vrow in df_v.iterrows():
            f_key = str(vrow.get('Fecha', ''))
            j_str = str(vrow.get('Jugadores', ''))
            jugs  = [p.strip() for p in j_str.split(",") if p.strip() and j_str != "nan"]
            if f_key:
                votos_actuales[f_key] = jugs

    # ══════════════════════════════════════════════════════
    # SECCIÓN 1: Calendario
    st.markdown("**📅 Selecciona fecha y franja horaria:**")
    slots_by_date, start_of_week = get_calendar_slots_grouped()
    selected_slots = []

    dias_es = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    # CSS compacto: columnas pegadas, sin padding extra de Streamlit
    st.markdown("""<style>
    .cal-week { font-size:0.68rem; font-weight:700; color:#888; text-transform:uppercase;
                letter-spacing:.06em; margin:14px 0 3px 0; }
    /* Quitar el gap vertical entre filas de columnas */
    [data-testid="stHorizontalBlock"] { gap: 0.3rem !important; margin-bottom: 0 !important; }
    [data-testid="stHorizontalBlock"] > div { padding: 0 !important; }
    /* Checkboxes más pequeños */
    .stCheckbox label { font-size: 0.78rem !important; }
    .stCheckbox { margin-bottom: 0 !important; padding: 0 !important; }
    </style>""", unsafe_allow_html=True)

    curr = start_of_week
    for w in range(6):
        lun = curr.strftime("%d/%m")
        dom = (curr + timedelta(days=6)).strftime("%d/%m")

        semana_slots = []
        tmp = curr
        for i in range(7):
            d_str = tmp.strftime("%Y-%m-%d")
            if d_str in slots_by_date:
                semana_slots.append((dias_es[i], tmp.strftime("%d/%m"), d_str, slots_by_date[d_str]))
            tmp += timedelta(days=1)

        if semana_slots:
            st.markdown(f'<div class="cal-week">—— Semana {lun}–{dom} ——</div>', unsafe_allow_html=True)
            for nombre, fecha, d_str, franjas in semana_slots:
                # 4 columnas: fecha(1.8) | franja1(1.5) | franja2(1.5) | relleno(1)
                c0, c1, c2, c3 = st.columns([1.8, 1.5, 1.5, 1])
                c0.markdown(
                    f'<div style="padding:6px 0 0 4px;font-size:0.82rem;font-weight:700;'
                    f'color:#1a73e8;white-space:nowrap;">{nombre}&nbsp;{fecha}</div>',
                    unsafe_allow_html=True)
                for j, franja in enumerate(franjas[:2]):
                    s_val  = f"{d_str} ({franja})"
                    n_vots = len(votos_actuales.get(s_val, []))
                    icon   = "🌅" if franja == "Mañana" else "🌆"
                    label  = f"{icon} {franja} ({n_vots}✓)"
                    col = c1 if j == 0 else c2
                    with col:
                        if st.checkbox(label, key=f"chk_{s_val}"):
                            selected_slots.append(s_val)

        curr += timedelta(days=7)
    st.divider()

    # ══════════════════════════════════════════════════════
    # SECCIÓN 2: Selección de miembros + confirmar
    # ══════════════════════════════════════════════════════
    col_sel, col_btn = st.columns([4, 1])
    with col_sel:
        sel_members = st.multiselect("👥 Miembros que asistirán:", all_m, label_visibility="collapsed",
                                     placeholder="Elige miembros...")
    with col_btn:
        confirmar = st.button("✅ Confirmar", type="primary", use_container_width=True)

    if confirmar:
        if not selected_slots:
            st.warning("⚠️ Selecciona al menos una fecha.")
        elif not sel_members:
            st.warning("⚠️ Selecciona al menos un miembro.")
        else:
            with st.spinner("Guardando..."):
                df_v_fresh = load_sheet_data("Votaciones")
                for s in selected_slots:
                    s = str(s).strip()
                    if not df_v_fresh.empty and 'Fecha' in df_v_fresh.columns and \
                       s in df_v_fresh['Fecha'].astype(str).values:
                        idx = df_v_fresh.index[df_v_fresh['Fecha'].astype(str) == s][0]
                        existentes = [p.strip() for p in str(df_v_fresh.at[idx, 'Jugadores']).split(",")
                                      if p.strip() and str(df_v_fresh.at[idx, 'Jugadores']) != "nan"]
                        for m in sel_members:
                            if m not in existentes:
                                existentes.append(m)
                        df_v_fresh.at[idx, 'Jugadores'] = ",".join(existentes)
                    else:
                        new_row = pd.DataFrame([{"Fecha": s, "Jugadores": ",".join(sel_members)}])
                        df_v_fresh = pd.concat([df_v_fresh, new_row], ignore_index=True)
                save_sheet_data("Votaciones", df_v_fresh)
                st.success("✅ ¡Votos guardados!")
                st.rerun()

    st.divider()

    # ══════════════════════════════════════════════════════
    # SECCIÓN 3: Estado de votaciones — tarjetas compactas
    # ══════════════════════════════════════════════════════
    st.markdown("**📊 Estado de votaciones:**")

    df_v = load_sheet_data("Votaciones")
    if not df_v.empty and 'Fecha' in df_v.columns:
        df_c = load_sheet_data("Campos")
        campo_opts = df_c['name'].tolist() if not df_c.empty and 'name' in df_c.columns else ["No hay campos"]

        for i in range(len(df_v)):
            row      = df_v.iloc[i]
            f        = str(row.get('Fecha', ''))
            j_str    = str(row.get('Jugadores', ''))
            jugadores = [p.strip() for p in j_str.split(",") if p.strip() and j_str != "nan"]
            if not jugadores:
                continue

            n      = len(jugadores)
            falta  = max(0, 10 - n)
            color  = "#e8f5e9" if n >= 10 else "#fff8e1"
            border = "#4CAF50" if n >= 10 else "#FFB300"
            barra  = min(n / 10, 1.0)

            # Tarjeta con barra de progreso visual
            st.markdown(f"""
            <div style="border-left:4px solid {border}; background:{color};
                        border-radius:6px; padding:8px 12px; margin-bottom:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight:700; font-size:0.85rem;">📅 {f}</span>
                    <span style="font-size:0.8rem; font-weight:600; color:{border};">
                        {n}/10 jugadores{"  🟢 Listo!" if n >= 10 else f"  ⏳ faltan {falta}"}
                    </span>
                </div>
                <div style="background:#ddd; border-radius:4px; height:5px; margin:5px 0;">
                    <div style="background:{border}; width:{int(barra*100)}%; height:5px; border-radius:4px;"></div>
                </div>
                <div style="font-size:0.75rem; color:#555;">👥 {', '.join(jugadores)}</div>
            </div>
            """, unsafe_allow_html=True)

            # Botón publicar — solo visible si hay 5+
            if n >= 10:
                with st.expander("🚀 Publicar partido", expanded=False):
                    hc = st.time_input("Hora del partido", key=f"h_{f}")
                    campo = st.selectbox("Campo", campo_opts, key=f"c_{f}")
                    if st.button("Confirmar y Publicar", key=f"p_{f}", type="primary"):
                        dt = f"{f.split(' ')[0]} {hc.strftime('%H:%M')}"
                        df_e_cur = load_sheet_data("Eventos")
                        new_e = pd.DataFrame([{"datetime": dt, "venue": campo, "players": ",".join(jugadores)}])
                        save_sheet_data("Eventos", pd.concat([df_e_cur, new_e], ignore_index=True))
                        df_v_upd = load_sheet_data("Votaciones")
                        df_v_upd = df_v_upd[df_v_upd['Fecha'].astype(str) != f]
                        save_sheet_data("Votaciones", df_v_upd)
                        st.rerun()
    else:
        st.info("No hay votos registrados actualmente.")

# ─────────────────────────────────────────────────────────
# TAB: 📅 Calendario
# ─────────────────────────────────────────────────────────
with tab_calendario:
    st.subheader("Google Calendar")
    components.iframe(
        "https://calendar.google.com/calendar/embed?"
        "src=07854ef03649a28b9507946bb4f7af183d0cf1f49535580916c12c2a4fd1933c%40group.calendar.google.com"
        "&ctz=Europe%2FMadrid",
        height=600
    )

# ─────────────────────────────────────────────────────────
# TAB: 🥅 Campos
# ─────────────────────────────────────────────────────────
with tab_campos:
    st.subheader("🥅 Gestión de Campos")
    df_c = load_sheet_data("Campos")

    with st.form("campo_form"):
        u    = st.text_input("Enlace de Google Maps")
        free = st.checkbox("Campo gratuito")
        col1, col2, col3 = st.columns(3)
        price = col1.number_input("Precio", min_value=0.0)
        num   = col2.number_input("Cantidad", min_value=1, value=1)
        unit  = col3.selectbox("Unidad", ["hora", "día", "minuto"])

        if st.form_submit_button("Extraer Nombre y Guardar"):
            if u:
                with st.spinner("Buscando nombre del campo..."):
                    name = fetch_venue_name(u)
                    if name:
                        new_c = pd.DataFrame([{
                            "name":          name,
                            "map_url":       u,
                            "is_free":       int(free),
                            "price":         price,
                            "duration_num":  num,
                            "duration_unit": unit
                        }])
                        save_sheet_data("Campos", pd.concat([df_c, new_c], ignore_index=True))
                        st.success(f"Campo añadido: {name}")
                        st.rerun()
                    else:
                        st.error("No se pudo identificar el lugar.")

    st.write("### Campos Registrados")
    df_c = load_sheet_data("Campos")   # recargar tras posible guardado

    if not df_c.empty:
        for i in range(len(df_c)):
            row = df_c.iloc[i]
            c1, c2 = st.columns([4, 1])
            nombre  = str(row.get('name', 'Sin nombre'))
            map_url = str(row.get('map_url', '#'))
            precio_f = formatear_precio(
                row.get('is_free', 0), row.get('price', 0),
                row.get('duration_num', 1), row.get('duration_unit', 'hora')
            )
            c1.markdown(f"🏟️ **[{nombre}]({map_url})** — {precio_f}")
            if c2.button("Eliminar", key=f"del_c_{i}"):
                df_c_new = df_c.drop(index=i).reset_index(drop=True)
                save_sheet_data("Campos", df_c_new)
                st.rerun()

# ─────────────────────────────────────────────────────────
# TAB: 🤼‍♂️ Miembros
# ─────────────────────────────────────────────────────────
with tab_miembros:
    df_m = load_sheet_data("Miembros")
    total_m = len(df_m) if not df_m.empty and 'name' in df_m.columns else 0
    st.subheader(f"🤼‍♂️ Miembros del Club  ({total_m})")

    with st.form("m_form"):
        new_name = st.text_input("Nombre del miembro")
        if st.form_submit_button("Añadir"):
            if new_name:
                save_sheet_data("Miembros", pd.concat(
                    [df_m, pd.DataFrame([{"name": new_name}])], ignore_index=True
                ))
                st.rerun()

    df_m = load_sheet_data("Miembros")   # recargar
    if not df_m.empty and 'name' in df_m.columns:
        for i in range(len(df_m)):
            r = df_m.iloc[i]
            c1, c2 = st.columns([4, 1])
            c1.write(f"👤 {r.get('name', '')}")
            if c2.button("Eliminar", key=f"m_del_{i}"):
                save_sheet_data("Miembros", df_m.drop(index=i).reset_index(drop=True))
                st.rerun()

# ─────────────────────────────────────────────────────────
# TAB: ⏳ Historial
# ─────────────────────────────────────────────────────────
with tab_historial:
    st.subheader("⏳ Historial de Partidos")
    df_e = load_sheet_data("Eventos")
    if not df_e.empty:
        if "datetime" in df_e.columns:
            df_e = df_e.sort_values("datetime", ascending=False)
        st.dataframe(df_e, use_container_width=True)
    else:
        st.info("No hay partidos registrados aún.")
