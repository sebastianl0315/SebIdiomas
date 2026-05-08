import streamlit as st
from supabase import create_client
import datetime
from logic import calcular_proximo_repaso
import random

# --- 1. CONFIGURACIÓN DE CONEXIÓN ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

# --- 2. FUNCIONES DE APOYO ---

def login_user(email, password):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return res
    except Exception as e:
        st.error(f"Error al iniciar sesión: {e}")
        return None

def signup_user(email, password, username, group_code):
    try:
        auth_res = supabase.auth.sign_up({"email": email, "password": password})
        user_id = auth_res.user.id
        supabase.table("profiles").insert({
            "id": user_id,
            "username": username,
            "group_id": group_code
        }).execute()
        return auth_res
    except Exception as e:
        st.error(f"Error en el registro: {e}")
        return None

def guardar_progreso(user_id, exercise_id, calidad_respuesta):
    try:
        progreso_actual = supabase.table("user_progress").select("*").eq("user_id", user_id).eq("exercise_id", exercise_id).execute()
        ease_factor, repetitions, interval = 2.5, 0, 0
        if progreso_actual.data:
            data = progreso_actual.data[0]
            ease_factor = data['ease_factor']
            repetitions = data['repetitions']
            interval = data['interval']

        nuevo_int, nuevas_rep, nuevo_ef, proxima_fecha = calcular_proximo_repaso(calidad_respuesta, ease_factor, repetitions, interval)

        supabase.table("user_progress").upsert({
            "user_id": str(user_id),
            "exercise_id": exercise_id,
            "ease_factor": nuevo_ef,
            "repetitions": nuevas_rep,
            "interval": nuevo_int,
            "next_review": proxima_fecha.isoformat(),
            "last_reviewed": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        st.error(f"Error al guardar progreso: {e}")

# --- 3. INTERFAZ PRINCIPAL ---

def main():
    st.set_page_config(page_title="SebIdiomas", page_icon="📖", layout="centered")

    st.markdown("""
        <style>
        .stApp { background-color: #f8f9fa !important; }
        .stWidgetLabel p, label { color: #1d3557 !important; font-weight: bold !important; }
        button[data-baseweb="tab"] p { color: #1d3557 !important; }
        button[data-baseweb="tab"][aria-selected="true"] {
            background-color: #e63946 !important;
            color: white !important;
            border-radius: 5px;
        }
        button[data-baseweb="tab"][aria-selected="true"] p { color: white !important; }
        div.stButton > button {
            background-color: #e63946 !important;
            color: white !important;
            border-radius: 8px !important;
            border: none !important;
            font-weight: bold !important;
        }
        div.stButton > button:hover { background-color: #1d3557 !important; }
        [data-testid="stSidebar"] { background-color: #1d3557 !important; }
        [data-testid="stSidebar"] * { color: white !important; }
        .stTextInput input {
            background-color: #ffffff !important;
            color: #1d3557 !important;
            border: 2px solid #1d3557 !important;
            border-radius: 5px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    if "user" not in st.session_state:
        st.session_state.user = None

    if st.session_state.user is None:
        st.title("Bienvenido a SebIdiomas")
        tab_login, tab_signup = st.tabs(["Iniciar Sesión", "Registrarse"])
        with tab_login:
            email = st.text_input("Correo electrónico")
            password = st.text_input("Contraseña", type="password")
            if st.button("Entrar", use_container_width=True):
                res = login_user(email, password)
                if res:
                    st.session_state.user = res.user
                    st.rerun()
        with tab_signup:
            new_email = st.text_input("Nuevo Correo")
            new_pass = st.text_input("Nueva Contraseña", type="password")
            new_user = st.text_input("Nombre de Usuario")
            group_id = st.text_input("Código de Grupo")
            if st.button("Crear Cuenta", use_container_width=True):
                res = signup_user(new_email, new_pass, new_user, group_id)
                if res: st.success("¡Cuenta creada! Ya puedes iniciar sesión.")
    else:
        # --- MENÚ LATERAL ---
        st.sidebar.title("🚀 SebIdiomas")
        opciones = ["Práctica Diaria", "Ranking de la Clase"]
        if st.session_state.user.email == "profesebastianloaiza@gmail.com":
            opciones.append("Panel de Administración")
        menu = st.sidebar.radio("Ir a:", opciones)
        if st.sidebar.button("Cerrar Sesión"):
            st.session_state.user = None
            st.rerun()

        # --- SECCIÓN: RANKING ---
        if menu == "Ranking de la Clase":
            st.title("🏆 Hall of Fame")
            try:
                user_profile = supabase.table("profiles").select("group_id").eq("id", st.session_state.user.id).single().execute()
                current_group = user_profile.data['group_id']
                res_leaderboard = supabase.table("leaderboard").select("*").eq("group_id", current_group).execute()
                if res_leaderboard.data:
                    for i, row in enumerate(res_leaderboard.data):
                        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "👤"
                        st.subheader(f"{medal} {row['username']} - {row['total_score']} pts")
                else:
                    st.info("¡Sé el primero en practicar!")
            except Exception as e:
                st.error(f"Error al cargar ranking: {e}")

        # --- SECCIÓN: PRÁCTICA ---
        elif menu == "Práctica Diaria":
            st.title("📚 Practice Room")
            
            # 1. Definición de rutas (puedes mover esto fuera de la función si prefieres)
            RUTA_GRADOS = {
                "10-A 2026": ["Vocabulary A1", "Verb to be", "Present simple"],
                "11-A 2026": ["Vocabulary A1", "Verb to be", "Present simple", "Presente continuous", "Future"],
                "11-B 2026": ["Vocabulary A1", "Verb to be", "Present simple", "Presente continuous"]
            }

            try:
                # 2. Inicializar estados de sesión para la práctica si no existen
                if "ejercicio_actual" not in st.session_state:
                    st.session_state.ejercicio_actual = None
                if "respondido" not in st.session_state:
                    st.session_state.respondido = False
                if "es_correcto" not in st.session_state:
                    st.session_state.es_correcto = False

                # 3. Cálculo de Meta Semanal (Visualización en Sidebar)
                hace_una_semana = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
                res_semanal = supabase.table("user_progress").select("ease_factor").eq("user_id", str(st.session_state.user.id)).gte("last_reviewed", hace_una_semana).execute()
                
                puntos_totales = sum([10 if r['ease_factor'] >= 2.5 else 5 if r['ease_factor'] >= 2.0 else 2 for r in res_semanal.data]) if res_semanal.data else 0
                
                META = 100
                st.sidebar.divider()
                st.sidebar.subheader("🎯 Meta Semanal")
                st.sidebar.progress(min(puntos_totales / META, 1.0))
                st.sidebar.write(f"Puntos: {puntos_totales} / {META}")

                # 4. Lógica de Selección de Ejercicio (Solo si no hay uno activo)
                if st.session_state.ejercicio_actual is None:
                    user_info = supabase.table("profiles").select("groups(group_name)").eq("id", st.session_state.user.id).single().execute()
                    nombre_grupo = user_info.data['groups']['group_name'] if user_info.data['groups'] else "Sin Grupo"
                    temas_permitidos = RUTA_GRADOS.get(nombre_grupo, ["Vocabulary A1"])
                    
                    # Cargar ejercicios y progreso
                    res_ex = supabase.table("exercises").select("*").in_("topic", temas_permitidos).execute()
                    res_prog = supabase.table("user_progress").select("exercise_id, next_review").eq("user_id", st.session_state.user.id).execute()
                    
                    progreso_map = {p['exercise_id']: p['next_review'] for p in res_prog.data}
                    ahora = datetime.datetime.now(datetime.timezone.utc)
                    
                    pendientes = [ex for ex in res_ex.data if ex['id'] not in progreso_map or ahora >= datetime.datetime.fromisoformat(progreso_map[ex['id']].replace('Z', '+00:00'))]

                    if pendientes:
                        # Priorizar nuevos (70%) o repasos
                        nuevos = [ex for ex in pendientes if ex['id'] not in progreso_map]
                        repasos = [ex for ex in pendientes if ex['id'] in progreso_map]
                        
                        if nuevos and repasos:
                            st.session_state.ejercicio_actual = random.choice(nuevos) if random.random() < 0.7 else random.choice(repasos)
                        else:
                            st.session_state.ejercicio_actual = random.choice(pendientes)
                        
                        st.session_state.respondido = False
                        st.session_state.es_correcto = False
                        st.rerun()

                # 5. Renderizado del Ejercicio Persistente
                if st.session_state.ejercicio_actual:
                    item = st.session_state.ejercicio_actual
                    ex_id, tipo, contenido = item['id'], item['type'], item['content']
                    es_repaso = ex_id in (progreso_map if 'progreso_map' in locals() else {})

                    st.markdown(f":{'orange' if es_repaso else 'green'}[**{'🔄 REPASO' if es_repaso else '✨ NUEVO'}**] | Tema: **{item.get('topic', 'General')}**")

                    # Interfaz según tipo
                    if tipo == 'translate':
                        st.info(f"**Pregunta:** {contenido['question']}")
                        resp_user = st.text_input("Tu respuesta:", key=f"input_{ex_id}", disabled=st.session_state.respondido).lower().strip()
                    else:
                        st.write(f"**Pregunta:** {contenido['question']}")
                        resp_user = st.radio("Opciones:", contenido['options'], key=f"radio_{ex_id}", disabled=st.session_state.respondido)

                    # Botones de Acción
                    if not st.session_state.respondido:
                        if st.button("Verificar", use_container_width=True):
                            validas = [r.lower().strip() for r in str(contenido['answer']).split('|')]
                            st.session_state.es_correcto = (resp_user in validas) if tipo == 'translate' else (resp_user == contenido['answer'])
                            st.session_state.respondido = True
                            
                            # Guardar inmediatamente si es correcto
                            if st.session_state.es_correcto:
                                guardar_progreso(st.session_state.user.id, ex_id, 5)
                            st.rerun()
                    else:
                        # Mostrar Feedback
                        if st.session_state.es_correcto:
                            st.success("¡Excelente trabajo! ✨")
                        else:
                            st.error(f"❌ La respuesta correcta era: **{str(contenido['answer']).split('|')[0]}**")
                            if tipo == 'translate' and st.button("Mi respuesta es correcta"):
                                guardar_progreso(st.session_state.user.id, ex_id, 2)
                                st.session_state.es_correcto = True
                                st.rerun()

                        if st.button("Siguiente Ejercicio ➡️", use_container_width=True):
                            # Si falló y no corrigió, guardar como error
                            if not st.session_state.es_correcto:
                                guardar_progreso(st.session_state.user.id, ex_id, 0)
                            
                            # Limpiar estado para el próximo ejercicio
                            st.session_state.ejercicio_actual = None
                            st.rerun()
                else:
                    st.info("✅ ¡Felicidades! Has terminado tus ejercicios pendientes.")

            except Exception as e:
                st.error(f"Error en la práctica: {e}")

        # --- SECCIÓN: PANEL DE ADMINISTRACIÓN ---
        elif menu == "Panel de Administración":
            st.title("📊 Control Docente")
            try:
                res_estudiantes = supabase.table("profiles").select("id, username, groups(group_name)").execute()
                df_estudiantes = res_estudiantes.data
                res_stats = supabase.table("user_progress").select("user_id, ease_factor").execute()
                df_stats = res_stats.data

                if df_estudiantes:
                    nombres_grupos = sorted(list(set([e['groups']['group_name'] for e in df_estudiantes if e['groups']])))
                    seleccion = st.selectbox("Grupo:", nombres_grupos)
                    estudiantes_grupo = [e for e in df_estudiantes if e['groups'] and e['groups']['group_name'] == seleccion]
                    
                    for est in estudiantes_grupo:
                        progreso_est = [s for s in df_stats if s['user_id'] == est['id']]
                        aciertos = len([s for s in progreso_est if s['ease_factor'] >= 2.5])
                        with st.expander(f"👤 {est['username']} - {aciertos} aciertos"):
                            st.metric("Intentos totales", len(progreso_est))
            except Exception as e:
                st.error(f"Error al cargar el panel: {e}")

if __name__ == "__main__":
    main()
