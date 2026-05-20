import streamlit as st
from supabase import create_client
import datetime
from logic import calcular_proximo_repaso
import random
import requests
import json

# --- 1. CONFIGURACIÓN DE CONEXIÓN ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)


# --- 2. FUNCIONES DE APOYO ---
import difflib  # Asegúrate de que esta línea quede dentro o arriba de la función

def validar_respuesta(intento, correcta):
    # 1. Limpieza básica de espacios y minúsculas
    intento_limpio = intento.strip().lower().rstrip('.')
    correcta_limpia = correcta.strip().lower().rstrip('.')
    
    # 2. Si es una coincidencia exacta, se aprueba de una
    if intento_limpio == correcta_limpia:
        return True
        
    # 3. Si no es exacta, calculamos el porcentaje de similitud (Ratio)
    similitud = difflib.SequenceMatcher(None, intento_limpio, correcta_limpia).ratio()
    
    # 4. Si la coincidencia es del 90% (0.90) o más, la damos por válida
    return similitud >= 0.95

def generar_ejercicio_ia(tema, tipo_ejercicio="translate"):
    api_key = st.secrets["GOOGLE_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    
    system_instruction = (
        "Eres un profesor de inglés en Colombia. "
        "Usa español de Colombia (ej: 'carro' en vez de 'coche', 'computador' en vez de 'ordenador'). "
        "Genera ejercicios educativos."
    )

    if tipo_ejercicio == "multiple_choice":
        formato_json = """
        {
            "question": "Pregunta en inglés o español",
            "options": ["A", "B", "C", "D"],
            "answer": "La opción correcta",
            "explanation": "Por qué es esa"
        }
        """
    else:
        formato_json = """
        {
            "question": "Frase en español",
            "answer": "Traducción en inglés",
            "explanation": "Regla gramatical"
        }
        """

    prompt = f"{system_instruction} Crea un ejercicio de tipo '{tipo_ejercicio}' sobre '{tema}'. Responde ÚNICAMENTE con este formato JSON: {formato_json}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            res_json = response.json()
            texto = res_json['candidates'][0]['content']['parts'][0]['text']
            data = json.loads(texto.replace('```json', '').replace('```', '').strip())
            
            return {
                "id": "ia_gen",
                "type": tipo_ejercicio,
                "topic": tema,
                "content": data
            }
    except Exception as e:
        print(f"Error: {e}")
    return None

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
    if exercise_id == "ia_gen":
        return 
        
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
        
def explicar_error_ia(pregunta, respuesta_correcta, respuesta_usuario, tema):
    api_key = st.secrets["GOOGLE_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    
    prompt = (
        f"Eres un profesor de inglés colombiano. El estudiante está practicando '{tema}'. "
        f"La pregunta era: '{pregunta}'. "
        f"La respuesta correcta es: '{respuesta_correcta}'. "
        f"El estudiante respondió: '{respuesta_usuario}'. "
        "Explica de forma breve, amable y en español de Colombia por qué la respuesta del estudiante es incorrecta "
        "y cuál es la regla gramatical que debe aplicar. Máximo 3 oraciones."
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
    except:
        return "Lo siento, no pude conectar con el profe IA en este momento."
    return "No pude generar la explicación."

def reset_password_admin(email):
    try:
        supabase.auth.reset_password_for_email(email)
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False
    
def actualizar_contrasena_usuario(nueva_contrasena):
    try:
        supabase.auth.update_user({"password": nueva_contrasena})
        return True
    except Exception as e:
        st.error(f"Error al cambiar la contraseña: {e}")
        return False

def eliminar_estudiante_db(user_id):
    try:
        supabase.table("profiles").delete().eq("id", user_id).execute()
        return True
    except Exception as e:
        st.error(f"Error al eliminar en la base de datos: {e}")
        return False

# --- 3. INTERFAZ PRINCIPAL ---
def main():
    st.set_page_config(
        page_title="SebIdiomas", 
        page_icon="favicon.png", 
        layout="centered"
    )
    
    # CSS Sanado y protegido para evitar pantallas blancas por colapso de renderizado
    st.markdown("""
         <style>
        /* Fondo general de la app */
        .stApp { background-color: #f8f9fa !important; }
        
        /* Forzar visibilidad de Títulos y Subtítulos en móviles */
        h1, h2, h3, span[data-baseweb="typewriter"] {
            color: #1d3557 !important;
            opacity: 1 !important;
            display: block !important;
        }

        /* Ajuste de márgenes en móviles para que no se esconda el contenido */
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        
        /* Texto principal */
        .stMarkdown p, .stText, label, .stWidgetLabel p { 
            color: #1d3557 !important; 
            font-weight: 500 !important; 
        }
        
        /* --- BARRA LATERAL --- */
        [data-testid="stSidebar"] { background-color: #1d3557 !important; }
        [data-testid="stSidebar"] * { color: white !important; }
        
        /* Botones grandes para dedos (touch friendly) */
        div.stButton > button {
            background-color: #e63946 !important;
            color: white !important;
            border-radius: 10px !important;
            height: 3em !important;
            width: 100% !important;
            margin-top: 10px !important;
        }
        /* Forzar visibilidad del texto de la meta semanal en el sidebar */
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: #ffffff !important;
            font-size: 1.1rem !important;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
        }

        /* Hacer la barra de progreso más alta para que sea fácil de ver en touch */
        [data-testid="stSidebar"] .stProgress > div > div > div > div {
            background-color: #e63946 !important;
            height: 10px;
        }
        /* --- ESTILO PARA OPCIONES DE SELECCIÓN MÚLTIPLE (RADIO) --- */
        
        /* Color del texto de las opciones no seleccionadas */
        div[data-testid="stMarkdownContainer"] p {
            color: #1d3557 !important;
        }

        /* Forzar color en los labels de los radio buttons */
        div[class*="st-"] label p {
            color: #1d3557 !important;
            font-size: 1.1rem !important;
            font-weight: 600 !important;
        }

        /* Espaciado entre opciones para que no queden pegadas en móvil */
        div[data-testid="stWidgetLabel"] {
            margin-bottom: 10px !important;
        }

        /* Ajuste para el círculo del radio (opcional, por si no se ve) */
        div[data-baseweb="radio"] div {
            text-shadow: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
 
    if "user" not in st.session_state:
        st.session_state.user = None
    if "recovery_mode" not in st.session_state:
        st.session_state.recovery_mode = False

    try:
        sesion_actual = supabase.auth.get_session()
        if sesion_actual and sesion_actual.user:
            parametros = st.query_params
            if parametros.get("type") == "recovery" or "type=recovery" in st.context.headers.get("Referer", ""):
                st.session_state.recovery_mode = True
    except:
        pass

    parametros = st.query_params
    if parametros.get("type") == "recovery" or "access_token" in parametros:
        st.session_state.recovery_mode = True

    if st.session_state.user is None:
        if st.session_state.recovery_mode:
            st.title("🔑 Restablecer tu Contraseña")
            st.subheader("Ingresa tu nueva clave de acceso")
            
            nueva_clave = st.text_input("Nueva Contraseña:", type="password", key="new_password_field")
            confirmar_clave = st.text_input("Confirmar Nueva Contraseña:", type="password", key="confirm_password_field")
            
            if st.button("Guardar Cambios y Entrar", use_container_width=True):
                if len(nueva_clave) < 6:
                    st.error("⚠️ La contraseña debe tener al menos 6 caracteres.")
                elif nueva_clave != confirmar_clave:
                    st.error("⚠️ Las contraseñas no coinciden.")
                else:
                    with st.spinner("Actualizando credenciales en Supabase..."):
                        if actualizar_contrasena_usuario(nueva_clave):
                            st.success("¡Contraseña actualizada con éxito! Ya puedes ingresar.")
                            st.session_state.recovery_mode = False
                            st.session_state.user = None
                            try:
                                supabase.auth.sign_out()
                            except:
                                pass
                            st.query_params.clear()
                            st.rerun()
            
            if st.button("❌ Cancelar", use_container_width=True):
                st.session_state.recovery_mode = False
                try:
                    supabase.auth.sign_out()
                except:
                    pass
                st.query_params.clear()
                st.rerun()

        else:
            col_logo, col_titulo = st.columns([1, 3], vertical_alignment="center")
            with col_logo:
                try:
                    st.image("logo.png", width=120)
                except:
                    pass
            with col_titulo:
                st.markdown('<p class="main-title">Bienvenido a SebIdiomas</p>', unsafe_allow_html=True)
            
            st.write("")
            tab_login, tab_signup = st.tabs(["Iniciar Sesión", "Registrarse"])
        
            with tab_login:
                email = st.text_input("Correo electrónico")
                password = st.text_input("Contraseña", type="password")
                col_login, col_olvido = st.columns([1, 1], vertical_alignment="center")
        
                with col_login:
                    if st.button("Entrar", use_container_width=True):
                        res = login_user(email, password)
                        if res:
                            st.session_state.user = res.user
                            st.rerun()
        
                with col_olvido:
                    msj_ayuda = "Hola Profe Sebastian, olvidé mi contraseña de SebIdiomas. Mi correo es: "
                    link_wa = f"https://wa.me/573114444334?text={msj_ayuda.replace(' ', '%20')}"
                    st.markdown(f"""
                        <a href="{link_wa}" target="_blank" style="text-decoration: none; display: block; width: 100%;">
                            <button style="display: flex; align-items: center; justify-content: center; width: 100%; padding: 10px 12px; font-family: inherit; font-size: 14px; font-weight: 500; color: #31333f; background-color: #ffffff; border: 1px solid rgba(49, 51, 63, 0.2); border-radius: 8px; cursor: pointer;">
                                ¿Olvidaste tu contraseña?
                            </button>
                        </a>
                    """, unsafe_allow_html=True)                    
                    
            with tab_signup:
                new_email = st.text_input("Nuevo Correo")
                new_pass = st.text_input("Nueva Contraseña", type="password")
                new_user = st.text_input("Nombre de Usuario")
                group_id = st.text_input("Código de Grupo")
                if st.button("Crear Cuenta", use_container_width=True):
                    res = signup_user(new_email, new_pass, new_user, group_id)
                    if res: st.success("¡Cuenta creada! Ya puedes iniciar sesión.")
    
    else:
        if st.session_state.user is None or not hasattr(st.session_state.user, 'id'):
            st.session_state.user = None
            st.query_params.clear()
            st.rerun()

        try:
            st.sidebar.image("logo.png", use_container_width=True)
        except:
            pass      
        st.sidebar.title("SebIdiomas")
        opciones = ["Práctica Diaria", "Ranking de la Clase"]
        
        if st.session_state.user and hasattr(st.session_state.user, 'email'):
            if st.session_state.user.email == "profesebastianloaiza@gmail.com":
                opciones.append("Panel de Administración")
                
        menu = st.sidebar.radio("Ir a:", opciones)

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

        elif menu == "Práctica Diaria":
            st.title("📚 Practice Room")
            RUTA_GRADOS = {
                "10-A 2026": ["Personal Information Basics", "Verb to be", "Present Simple"],
                "11-A 2026": ["Personal Information Basics", "Verb to be", "Present Simple"],
                "11-B 2026": ["Personal Information Basics", "Verb to be", "Present Simple"],
                "Grupo_Prueba": ["Personal Information Basics", "Verb to be", "Present Simple"],
            }

            try:
                if "ejercicio_actual" not in st.session_state: st.session_state.ejercicio_actual = None
                if "respondido" not in st.session_state: st.session_state.respondido = False
                if "es_correcto" not in st.session_state: st.session_state.es_correcto = False
                if "input_counter" not in st.session_state: st.session_state.input_counter = 0

                if st.session_state.ejercicio_actual is None:
                    user_info = supabase.table("profiles").select("group_id, groups(group_name)").eq("id", st.session_state.user.id).single().execute()
                    nombre_grupo = user_info.data['groups']['group_name'] if user_info.data['groups'] else "Sin Grupo"
                    temas_permitidos = RUTA_GRADOS.get(nombre_grupo, ["Vocabulary A1"])
                    
                    res_ex = supabase.table("exercises").select("*").in_("topic", temas_permitidos).execute()
                    res_prog = supabase.table("user_progress").select("exercise_id, next_review").eq("user_id", st.session_state.user.id).execute()
                    progreso_map = {p['exercise_id']: p['next_review'] for p in res_prog.data}
                    
                    ahora = datetime.datetime.now(datetime.timezone.utc)
                    
                    pendientes = []
                    for ex in res_ex.data:
                        if ex['id'] not in progreso_map:
                            pendientes.append(ex)
                        else:
                            fecha_repaso = datetime.datetime.fromisoformat(progreso_map[ex['id']].replace('Z', '+00:00'))
                            if ahora >= fecha_repaso:
                                pendientes.append(ex)

                    if pendientes:
                        st.session_state.ejercicio_actual = random.choice(pendientes)
                    else:
                        tema_para_ia = random.choice(temas_permitidos)
                        with st.spinner(f"Generando práctica de {tema_para_ia}..."):
                            nuevo_ejercicio = generar_ejercicio_ia(tema_para_ia)
                            if nuevo_ejercicio:
                                st.session_state.ejercicio_actual = nuevo_ejercicio
                            else:
                                st.error("No hay ejercicios disponibles ni conexión con la IA.")
                    
                    st.session_state.respondido = False
                    st.session_state.es_correcto = False
                    st.rerun()

                if st.session_state.ejercicio_actual:
                    item = st.session_state.ejercicio_actual
                    ex_id, tipo, contenido = item['id'], item['type'], item['content']
                    st.markdown(f"### Tema: {item.get('topic', 'General')}")
                    
                    if tipo == 'translate':
                        st.info(f"**Pregunta:** {contenido['question']}")
                        resp_user = st.text_input("Tu respuesta:", key=f"in_{ex_id}", disabled=st.session_state.respondido).lower().strip()
                    elif tipo == "multiple_choice":
                        st.write(f"**Pregunta:** {contenido['question']}")
                        resp_user = st.radio("Opciones:", contenido['options'], key=f"rad_{ex_id}", disabled=st.session_state.respondido)
                    elif tipo == 'scrambled':
                        palabras = contenido['words']
                        random.shuffle(palabras)
                        st.info("**Ordena la oración:**")
                        st.subheader(f"🧩 {' / '.join(palabras)}")
                        resp_user = st.text_input("Tu respuesta:", key=f"scr_{ex_id}_{st.session_state.input_counter}").strip()

                    if not st.session_state.respondido:
                        if st.button("Verificar", use_container_width=True):
                            respuestas_correctas = str(contenido['answer']).split('|')
                            coincide = any(validar_respuesta(resp_user, r) for r in respuestas_correctas)
                            
                            st.session_state.es_correcto = coincide
                            st.session_state.respondido = True
                            if st.session_state.es_correcto: 
                                guardar_progreso(st.session_state.user.id, ex_id, 5)
                            st.rerun()
                    else:
                        if st.session_state.es_correcto:
                            st.success("¡Excelente!")
                            if 'explanation' in contenido: st.caption(f"💡 {contenido['explanation']}")
                        else:              
                            st.error(f"❌ La respuesta correcta era: {str(contenido['answer']).split('|')[0]}")
    
                            if st.button("🤔 ¿Por qué me equivoqué? Explícame", key=f"expl_{ex_id}"):
                                if item and 'content' in item:
                                    with st.spinner("El profe está revisando tu respuesta..."):
                                        pregunta_texto = item['content'].get('question', 'la frase anterior')
                                        respuesta_profe = str(item['content'].get('answer', '')).split('|')[0]
                                        tema_ejercicio = item.get('topic', 'Inglés')

                                        explicacion = explicar_error_ia(pregunta_texto, respuesta_profe, resp_user, tema_ejercicio)
                                        st.info(explicacion)
                                else:
                                    st.error("No se pudo recuperar la información del ejercicio para la IA.")
                                      
                                if ex_id != "ia_gen":
                                    if st.button("Mi respuesta es correcta", key=f"btn_reclamo_{ex_id}"):
                                        try:
                                            reporte = {
                                                "user_id": st.session_state.user.id, 
                                                "exercise_id": ex_id,
                                                "user_answer": str(resp_user),
                                                "expected_answer": str(contenido['answer']),
                                                "status": "pending"
                                            }
                                            supabase.table("exercise_reports").insert(reporte).execute()
                                            st.success("✅ Reporte enviado. El Profe Sebastián lo revisará.")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Error al enviar: {e}")

                        if st.button("Siguiente Ejercicio ➡️", use_container_width=True):
                            if not st.session_state.es_correcto: 
                                guardar_progreso(st.session_state.user.id, ex_id, 0)
                            st.session_state.ejercicio_actual = None
                            st.session_state.input_counter += 1
                            st.rerun()

            except Exception as e:
                st.error(f"Error en práctica: {e}")
            
            try:
                user_data = supabase.table("profiles").select("groups(weekly_goal)").eq("id", st.session_state.user.id).single().execute()
                meta_dinamica = user_data.data['groups']['weekly_goal'] if user_data.data['groups'] else 100

                una_semana_atras = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
                progreso_semana = supabase.table("user_progress").select("id").eq("user_id", st.session_state.user.id).gt("last_reviewed", una_semana_atras).execute()
    
                completados = len(progreso_semana.data)
                porcentaje = min(completados / meta_dinamica, 1.0)
    
                st.sidebar.write(f"📊 Meta Semanal: {completados}/{meta_dinamica}")
                st.sidebar.progress(porcentaje)
                if porcentaje >= 1.0:
                    st.sidebar.success("¡Meta alcanzada! 🎯")
            except:
                pass                    
  
        elif menu == "Panel de Administración":
            st.title("📊 Control Docente")
            
            tab_reportes, tab_estudiantes, tab_config = st.tabs([
                "🚩 Reportes de Errores", 
                "👥 Gestión de Estudiantes por Grupo", 
                "⚙️ Configuración del Sistema"
            ])
            
            # --- PESTAÑA 1: REPORTES DE ERRORES ---
            with tab_reportes:
                st.subheader("Reportes de Errores Pendientes")
                try:
                    res_reports = supabase.table("exercise_reports").select(
                        "id, user_answer, expected_answer, profiles(username), exercises(content, topic)"
                    ).eq("status", "pending").execute()
                    
                    if not res_reports.data:
                        st.info("No hay reportes nuevos por revisar. ¡Todo al día! ✨")
                    else:
                        for report in res_reports.data:
                            nombre_alumno = report['profiles']['username'] if report['profiles'] else "Usuario"
                            with st.expander(f"Reporte de {nombre_alumno}"):
                                st.write(f"**Alumno dijo:** {report['user_answer']}")
                                c1, c2 = st.columns(2)
                                if c1.button("Aprobar", key=f"ap_{report['id']}", use_container_width=True):
                                    supabase.table("exercise_reports").update({"status": "approved"}).eq("id", report['id']).execute()
                                    st.rerun()
                                if c2.button("Rechazar", key=f"re_{report['id']}", use_container_width=True):
                                    supabase.table("exercise_reports").update({"status": "rejected"}).eq("id", report['id']).execute()
                                    st.rerun()
                except Exception as e:
                    st.error(f"Error cargando reportes: {e}")

            # --- PESTAÑA 2: GESTIÓN DE ESTUDIANTES ---
            with tab_estudiantes:
                st.subheader("👥 Gestión de Estudiantes por Grupos")
                try:
                    res_estudiantes = supabase.table("profiles").select(
                        "id, username, group_id, groups(group_name)"
                    ).execute()
                    lista_estudiantes = res_estudiantes.data if res_estudiantes else []
                except Exception as e:
                    st.error(f"No se pudieron cargar los estudiantes: {e}")
                    lista_estudiantes = []

                if lista_estudiantes:
                    mapeo_grupos = {}
                    for est in lista_estudiantes:
                        g_id = est.get("group_id")
                        if g_id:
                            info_grupo = est.get("groups")
                            if isinstance(info_grupo, dict):
                                g_name = info_grupo.get("group_name", g_id)
                            else:
                                g_name = g_id
                            mapeo_grupos[g_id] = g_name

                    if mapeo_grupos:
                        opciones_combo = list(mapeo_grupos.keys())
                        grupo_seleccionado_id = st.selectbox(
                            "Selecciona el grupo para administrar:", 
                            opciones_combo, 
                            format_func=lambda x: f"🏫 {mapeo_grupos[x]} ({x})",
                            key="sb_admin_grupos"
                        )
                        
                        estudiantes_filtrados = [est for est in lista_estudiantes if est.get("group_id") == grupo_seleccionado_id]
                        
                        if estudiantes_filtrados:
                            st.write(f"Estudiantes activos en el grupo **{mapeo_grupos[grupo_seleccionado_id]}**:")
                            
                            for est in estudiantes_filtrados:
                                col_info, col_accion = st.columns([3, 1], vertical_alignment="center")
                                with col_info:
                                    nombre_usuario = est.get("username", "Sin nombre")
                                    st.markdown(f"👤 **{nombre_usuario}**")
                                with col_accion:
                                    if st.button("❌ Eliminar", key=f"del_{est['id']}", use_container_width=True):
                                        st.session_state.confirmar_eliminar = est
                                        st.rerun()
                            
                            if "confirmar_eliminar" in st.session_state and st.session_state.confirmar_eliminar:
                                est_a_borrar = st.session_state.confirmar_eliminar
                                nombre_borrar = est_a_borrar.get("username", "este estudiante")
                                
                                st.warning(f"⚠️ ¿Estás seguro de que deseas eliminar a **{nombre_borrar}**? Perderá el acceso.")
                                col_si, col_no = st.columns(2)
                                with col_si:
                                    if st.button("Sí, eliminar", type="primary", use_container_width=True, key="btn_conf_si"):
                                        with st.spinner("Eliminando..."):
                                            if eliminar_estudiante_db(est_a_borrar["id"]):
                                                st.success(f"¡{nombre_borrar} eliminado!")
                                                st.session_state.confirmar_eliminar = None
                                                st.rerun()
                                with col_no:
                                    if st.button("Cancelar", use_container_width=True, key="btn_conf_no"):
                                        st.session_state.confirmar_eliminar = None
                                        st.rerun()
                        else:
                            st.info("No hay estudiantes registrados en este grupo.")
                    else:
                        st.info("No hay códigos de grupo vinculados a ningún estudiante.")
                else:
                    st.info("No hay perfiles registrados en el sistema.")

            # --- PESTAÑA 3: CONFIGURACIÓN / METAS ---
            with tab_config:
                st.subheader("⚙️ Configuración del Sistema")
                with st.container(border=True):
                    st.markdown("### 🔑 Gestión de Usuarios (Mantenimiento)")
                    st.write("Herramientas globales para el control de accesos de la plataforma.")
                    st.write("")
                    
                    user_a_resetear = st.text_input("Correo del alumno que olvidó la clave:")
                    if st.button("Enviar correo de recuperación"):
                        if reset_password_admin(user_a_resetear):
                            st.success("Correo de recuperación enviado con éxito.")
                    
                with st.container(border=True):
                    st.markdown("### 📈 Seguimiento de Metas")
                    st.write("Panel para la administración y control de las metas globales por lote asignadas a los muchachos.")
                    
                    # 1. Selección de fechas y usuario
                    col1, col2 = st.columns(2)
                    fecha_inicio = col1.date_input("Desde", datetime.date.today() - datetime.timedelta(days=30))
                    fecha_fin = col2.date_input("Hasta", datetime.date.today())
           
                    res_est_meta = supabase.table("profiles").select("id, username").execute()
                    if res_est_meta.data:
                        estudiantes = {e['username']: e['id'] for e in res_est_meta.data}
                        sel_estudiante = st.selectbox("Seleccionar Estudiante para auditar:", list(estudiantes.keys()))
                        user_id_auditar = estudiantes[sel_estudiante]

                       # 2. Consultar progreso en ese rango
                        res_auditoria = supabase.table("user_progress") \
                            .select("last_reviewed") \
                            .eq("user_id", user_id_auditar) \
                            .gte("last_reviewed", fecha_inicio.isoformat()) \
                            .lte("last_reviewed", fecha_fin.isoformat()) \
                            .execute()

                        if res_auditoria.data:
                           import pandas as pd
                   
                           df = pd.DataFrame(res_auditoria.data)
                           df['last_reviewed'] = pd.to_datetime(df['last_reviewed'])
                   
                            # Agrupar por semana (empezando lunes 'W-MON')
                            # Contamos cuántos ejercicios hizo por semana
                           df_semanal = df.groupby(pd.Grouper(key='last_reviewed', freq='W-MON')).size().reset_index(name='conteo')
                   
                            # 3. Mostrar Resultados
                           metas_cumplidas = df_semanal[df_semanal['conteo'] >= 100].shape[0]
                           metas_cumplidas = df_semanal[df_semanal['conteo'] >= 100].shape[0]
                   
                           c1, c2 = st.columns(2)
                           c1.metric("Metas Cumplidas", f"{metas_cumplidas} semanas")
                           c1.metric("Metas Cumplidas", f"{metas_cumplidas} semanas")
                           c2.metric("Total Ejercicios", f"{len(res_auditoria.data)}")
                   
                           # Visualización opcional para el docente
                           with st.expander("Ver detalle por semanas"):
                               df_semanal['Cumplió'] = df_semanal['conteo'].apply(lambda x: "✅" if x >= 100 else "❌")
                               st.table(df_semanal.rename(columns={'last_reviewed': 'Semana del (Lunes)', 'conteo': 'Ejercicios'}))
                        else:
                           st.info("No hay actividad registrada en este rango de fechas.")
                st.divider()
                st.subheader("🎯 Configurar Metas por Grupo")
                try:
                   # Traer los grupos actuales
                   res_grupos = supabase.table("groups").select("id, group_name, weekly_goal").execute()
                   if res_grupos.data:
                       for grp in res_grupos.data:
                           with st.expander(f"Meta de {grp['group_name']}"):
                               nueva_meta = st.number_input(
                                   f"Ejercicios semanales para {grp['group_name']}:", 
                                   value=int(grp['weekly_goal']),
                                   key=f"goal_{grp['id']}"
                               )
                               if st.button("Actualizar Meta", key=f"btn_goal_{grp['id']}"):
                                   supabase.table("groups").update({"weekly_goal": nueva_meta}).eq("id", grp['id']).execute()
                                   st.success("¡Meta actualizada!")
                                   st.rerun()
                except Exception as e:
                   st.error(f"Error al cargar metas: {e}")                    
                   st.error(f"Error al cargar metas: {e}")         
                    
  #-------CERRAR SESIÓN------------------        
        st.sidebar.divider()
        if st.sidebar.button("Cerrar Sesión", use_container_width=True):
            st.session_state.user = None
if __name__ == "__main__":
    main()
