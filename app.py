import streamlit as st
from supabase import create_client
import datetime
from logic import calcular_proximo_repaso

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
            "last_reviewed": datetime.datetime.now().isoformat()
        }).execute()
    except Exception as e:
        st.error(f"Error al guardar progreso: {e}")

# --- 3. INTERFAZ PRINCIPAL ---

def main():
    st.set_page_config(page_title="SebIdiomas", page_icon="📖", layout="centered")

    # --- ESTILO VISUAL PERSONALIZADO ---
    st.markdown("""
        <style>
        /* Fondo principal */
        .stApp { 
            background-color: #f8f9fa !important; 
        }

        /* --- CORRECCIÓN DE VISIBILIDAD DE TEXTOS --- */
        /* Forzar color oscuro en etiquetas de campos (Email, Contraseña, etc.) */
        .stWidgetLabel p, label {
            color: #1d3557 !important;
            font-weight: bold !important;
        }

        /* Estilo para las Pestañas (Login / Registro) */
        button[data-baseweb="tab"] p {
            color: #1d3557 !important; /* Texto visible */
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            background-color: #e63946 !important; /* Pestaña activa en Rojo */
            color: white !important;
            border-radius: 5px;
        }
        button[data-baseweb="tab"][aria-selected="true"] p {
            color: white !important;
        }

        /* --- BOTONES Y BARRA LATERAL --- */
        div.stButton > button {
            background-color: #e63946 !important;
            color: white !important;
            border-radius: 8px !important;
            border: none !important;
            font-weight: bold !important;
        }
        div.stButton > button:hover { 
            background-color: #1d3557 !important; 
        }
        
        [data-testid="stSidebar"] { 
            background-color: #1d3557 !important; 
        }
        [data-testid="stSidebar"] * { 
            color: white !important; 
        }

        /* Ajuste para inputs en móviles */
        /* --- MEJORA DE RECUADROS DE TEXTO (INPUTS) --- */
        .stTextInput input {
            background-color: #ffffff !important; /* Fondo blanco puro */
            color: #1d3557 !important;           /* Texto azul institucional oscuro */
            border: 2px solid #1d3557 !important; /* Borde definido para que se vea el recuadro */
            border-radius: 5px !important;
        }

        /* Color del texto cuando el campo está enfocado (haciendo clic) */
        .stTextInput input:focus {
            border-color: #e63946 !important;     /* Borde rojo al escribir */
            box-shadow: 0 0 0 0.2rem rgba(230, 57, 70, 0.25) !important;
        }

        /* Asegurar visibilidad del texto en modo oscuro de algunos celulares */
        input::placeholder {
            color: #6c757d !important; /* Gris claro para el texto de ayuda */
        }
        </style>
    """, unsafe_allow_html=True)

    if "user" not in st.session_state:
        st.session_state.user = None

    # --- FLUJO DE AUTENTICACIÓN ---
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
        
        # Definimos las opciones del menú
        opciones = ["Práctica Diaria", "Ranking de la Clase"]
        
        # SOLO TÚ PUEDES VER EL PANEL DE ADMIN (Reemplaza con tu correo)
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
                    st.info("¡Sé el primero en practicar para aparecer aquí!")
            except Exception as e:
                st.error(f"Error al cargar ranking: {e}")

# --- SECCIÓN: PRÁCTICA ---
        elif menu == "Práctica Diaria":
            st.title("📚 Practice Room")
            try:
                # 1. Cargar datos
                res_ex = supabase.table("exercises").select("*").execute()
                todos_ejercicios = res_ex.data 
                
                res_prog = supabase.table("user_progress").select("exercise_id, next_review").eq("user_id", st.session_state.user.id).execute()
                
                progreso_map = {p['exercise_id']: p['next_review'] for p in res_prog.data}
                ahora = datetime.datetime.now(datetime.timezone.utc)
                pendientes = []

                for ex in todos_ejercicios:
                    eid = ex['id']
                    if eid not in progreso_map:
                        pendientes.append(ex)
                    else:
                        fecha_str = progreso_map[eid].replace('Z', '+00:00')
                        fecha_repaso = datetime.datetime.fromisoformat(fecha_str)
                        if ahora >= fecha_repaso:
                            pendientes.append(ex)

                # 2. Interfaz de Práctica Lineal
                if not pendientes:
                    st.balloons()
                    st.success("🎉 ¡Misión cumplida por hoy!")
                else:
                    # Siempre el primero de la lista
                    item = pendientes[0]
                    ex_id, tipo, contenido = item['id'], item['type'], item['content']

                    # Barra de progreso
                    total_maestro = len(todos_ejercicios)
                    resueltos = total_maestro - len(pendientes)
                    prog = resueltos / total_maestro if total_maestro > 0 else 0.0
                    st.progress(prog, text=f"Progreso: {resueltos}/{total_maestro} ejercicios")

                    st.markdown(f"### Tarea: {tipo.replace('_', ' ').capitalize()}")

                    # --- LÓGICA PARA TRADUCCIÓN ---
                    if tipo == 'translate':
                        st.info(f"**Pregunta:** {contenido['question']}")
                        respuesta_usuario = st.text_input("Tu respuesta:", key=f"in_{ex_id}").lower().strip()
                        
                        if f"error_{ex_id}" not in st.session_state:
                            st.session_state[f"error_{ex_id}"] = False

                        col1, col2 = st.columns(2)
                        
                        if not st.session_state[f"error_{ex_id}"]:
                            if col1.button("Verificar", use_container_width=True):
                                respuestas_validas = [r.lower().strip() for r in str(contenido['answer']).split('|')]
                                
                                if respuesta_usuario in respuestas_validas:
                                    st.success("¡Correcto! +10 puntos")
                                    if f"error_{ex_id}" in st.session_state:
                                        del st.session_state[f"error_{ex_id}"]
                                    guardar_progreso(st.session_state.user.id, ex_id, 5)
                                    st.rerun()
                                else:
                                    st.session_state[f"error_{ex_id}"] = True
                                    st.rerun()
                        else:
                            # Feedback de error y respuesta correcta
                            primera_opcion = str(contenido['answer']).split('|')[0].strip()
                            st.error(f"❌ Incorrecto. La respuesta correcta es: **{primera_opcion}**")
                            
                            if col1.button("Siguiente", use_container_width=True):
                                del st.session_state[f"error_{ex_id}"]
                                guardar_progreso(st.session_state.user.id, ex_id, 0)
                                st.rerun()

                            if col2.button("Mi respuesta es correcta", use_container_width=True):
                                del st.session_state[f"error_{ex_id}"]
                                guardar_progreso(st.session_state.user.id, ex_id, 2) 
                                st.rerun()

                    # --- LÓGICA PARA SELECCIÓN MÚLTIPLE ---
                    elif tipo == 'multiple_choice':
                        st.write(f"**Pregunta:** {contenido['question']}")
                        opcion = st.radio("Opciones:", contenido['options'], key=f"rad_{ex_id}")
                        
                        if f"error_{ex_id}" not in st.session_state:
                            st.session_state[f"error_{ex_id}"] = False

                        if not st.session_state[f"error_{ex_id}"]:
                            if st.button("Revisar", use_container_width=True):
                                if opcion == contenido['answer']:
                                    st.success("¡Excelente! +10 puntos")
                                    if f"error_{ex_id}" in st.session_state:
                                        del st.session_state[f"error_{ex_id}"]
                                    guardar_progreso(st.session_state.user.id, ex_id, 5)
                                    st.rerun()
                                else:
                                    st.session_state[f"error_{ex_id}"] = True
                                    st.rerun()
                        else:
                            # Feedback de error y respuesta correcta
                            st.error(f"❌ Incorrecto. La opción correcta era: **{contenido['answer']}**")
                            
                            if st.button("Siguiente", use_container_width=True):
                                del st.session_state[f"error_{ex_id}"]
                                guardar_progreso(st.session_state.user.id, ex_id, 0)
                                st.rerun()
            except Exception as e:
                st.error(f"Error en la práctica: {e}")

# --- SECCIÓN: PANEL DE ADMINISTRACIÓN ---
        elif menu == "Panel de Administración":
            st.title("📊 Control de Progreso Docente")
            st.write("Seguimiento en tiempo real de tus estudiantes.")

            try:
                # 1. Obtener perfiles incluyendo el nombre del grupo (JOIN)
                # Usamos 'groups(group_name)' para traer la etiqueta en lugar del código
                res_estudiantes = supabase.table("profiles").select("id, username, group_id, groups(group_name)").execute()
                df_estudiantes = res_estudiantes.data

                # 2. Obtener todo el progreso
                res_stats = supabase.table("user_progress").select("user_id, ease_factor, last_reviewed").execute()
                df_stats = res_stats.data

                if df_estudiantes:
                    # Extraemos los nombres de los grupos para el selector
                    # Accedemos a ['groups']['group_name'] debido a la estructura del JOIN en Supabase
                    nombres_grupos = sorted(list(set([e['groups']['group_name'] for e in df_estudiantes if e['groups']])))
                    seleccion_nombre = st.selectbox("Seleccionar Grupo por Nombre:", nombres_grupos)

                    # Filtrar estudiantes que pertenecen a ese nombre de grupo
                    estudiantes_grupo = [e for e in df_estudiantes if e['groups'] and e['groups']['group_name'] == seleccion_nombre]
                    
                    st.divider()
                    st.subheader(f"Estudiantes en {seleccion_nombre}")
                    
                    for est in estudiantes_grupo:
                        progreso_est = [s for s in df_stats if s['user_id'] == est['id']]
                        ejercicios_completados = len(progreso_est)
                        aciertos_reales = len([s for s in progreso_est if s['ease_factor'] >= 2.5])
                        
                        with st.expander(f"👤 {est['username']} - {aciertos_reales} aciertos"):
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Ejercicios Intentados", ejercicios_completados)
                            col2.metric("Dominio Real (Ranking)", aciertos_reales)
                            
                            if progreso_est:
                                # Ordenar por fecha para obtener la última actividad
                                ultima_actividad = max([s['last_reviewed'] for s in progreso_est])
                                col3.caption(f"Última actividad: {ultima_actividad[:10]}")
                            else:
                                col3.write("Sin actividad.")
                else:
                    st.info("No hay estudiantes registrados todavía.")

            except Exception as e:
                st.error(f"Error al cargar el panel: {e}")
                st.info("Asegúrate de que la relación entre 'profiles' y 'groups' esté bien definida en Supabase.") 

if __name__ == "__main__":
    main()

