import streamlit as st
from supabase import create_client
import datetime
from logic import calcular_proximo_repaso
import random
import requests
import json
from streamlit_cookies_controller import CookieController

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
    
    # 4. Si la coincidencia es del 95% (0.95) o más, la damos por válida
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
        "Si la respuesta debió ser aceptada como correcta, dile que la reporte con el botón de la respuesta era correcta "
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
    except:
        return "Lo siento, no pude conectar con el profe IA en este momento."
    return "No pude generar la explicación."

def res_password_admin(email):
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

def obtener_inicio_semana_actual():
    hoy = datetime.date.today()
    # weekday() devuelve 0 para lunes, 6 para domingo
    dias_al_lunes = hoy.weekday() 
    lunes_actual = hoy - datetime.timedelta(days=dias_al_lunes)
    # Retorna la fecha en formato string 'YYYY-MM-DD' para la consulta de Supabase
    return lunes_actual.strftime("%Y-%m-%d")

# --- 3. INTERFAZ PRINCIPAL ---
def main():
    st.set_page_config(
        page_title="SebIdiomas", 
        page_icon="favicon.png", 
        layout="centered"
    )
    controller = CookieController()    
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
 
   # --- VERIFICACIÓN Y PERSISTENCIA DE SESIÓN (RESISTENTE A F5) ---
    
    # 1. Inicializar variables de estado indispensables
    if "user" not in st.session_state:
        st.session_state.user = None
    if "cookies_initialized" not in st.session_state:
        st.session_state.cookies_initialized = False

    # 2. Intentar leer la cookie de Supabase protegiendo la carga asíncrona
    sb_session_token = None
    try:
        sb_session_token = controller.get("sb_session")
    except TypeError:
        # Captura el fallo cuando self.__cookies aún no está listo internamente en la librería
        pass

    # 3. Mecanismo de espera en el primer renderizado tras F5
    # Si la librería falló o devolvió None pero es la primera pasada del script tras el F5,
    # pausamos brevemente (200ms) para que cargue el JS y forzamos un ciclo de reloj limpio.
    if sb_session_token is None and not st.session_state.cookies_initialized:
        import time
        time.sleep(0.2)  # Pausa imperceptible y segura para el navegador
        st.session_state.cookies_initialized = True
        st.rerun()

    # 4. Si después del intento/espera realmente hay un token guardado, restauramos
    if st.session_state.user is None and sb_session_token:
        try:
            # Restauramos la sesión en el cliente de Supabase
            res_sesion = supabase.auth.set_session(
                sb_session_token["access_token"], 
                sb_session_token["refresh_token"]
            )
            if res_sesion and res_sesion.user:
                st.session_state.user = res_sesion.user
                
                # Sincronizamos inmediatamente los tokens frescos en la cookie
                session_data = {
                    "access_token": res_sesion.session.access_token,
                    "refresh_token": res_sesion.session.refresh_token
                }
                controller.set("sb_session", session_data, expires=datetime.datetime.now() + datetime.timedelta(days=30))
                
                # Forzamos rerun para pintar inmediatamente el entorno de estudio
                st.rerun()
        except Exception as e:
            # Si el token falló o expiró definitivamente, limpiamos por seguridad
            try:
                controller.remove("sb_session")
            except:
                pass
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
                            st.session_state.cookies_initialized = True # <-- Agregar esto en el login exitoso
                            # Guardamos los tokens en una cookie que dure 30 días
                            session_data = {
                                "access_token": res.session.access_token,
                                "refresh_token": res.session.refresh_token
                            }
                            controller.set("sb_session", session_data, expires=datetime.datetime.now() + datetime.timedelta(days=30))
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
                # NUEVO: Campo para confirmar el correo electrónico
                confirm_email = st.text_input("Confirmar Correo")
                new_pass = st.text_input("Nueva Contraseña", type="password")
                confirm_pass = st.text_input("Confirmar Contraseña", type="password")
                new_user = st.text_input("Nombre de Usuario")
                group_id = st.text_input("Código de Grupo")
                
                if st.button("Crear Cuenta", use_container_width=True):
                    # 1. Validación de campos vacíos
                    if not new_email or not confirm_email or not new_pass or not confirm_pass or not new_user or not group_id:
                        st.error("⚠️ Todos los campos son obligatorios.")
                    
                    # 2. Validación de correos coincidentes
                    elif new_email.strip().lower() != confirm_email.strip().lower():
                        st.error("⚠️ Los correos electrónicos no coinciden. Por favor, verifícalos.")
                    
                    # 3. Validación de longitud de contraseña
                    elif len(new_pass) < 6:
                        st.error("⚠️ La contraseña debe tener al menos 6 caracteres.")
                    
                    # 4. Validación de contraseñas coincidentes
                    elif new_pass != confirm_pass:
                        st.error("⚠️ Las contraseñas no coinciden. Verifica bien lo que escribiste.")
                    
                    # 5. Si todo está perfecto, se procede al registro
                    else:
                        with st.spinner("Creando cuenta..."):
                            res = signup_user(new_email.strip(), new_pass, new_user.strip(), group_id.strip())
                            if res: 
                                st.success("¡Cuenta creada con éxito! Ya puedes pasar a la pestaña de 'Iniciar Sesión'.")
    
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
        opciones = ["Práctica Diaria", "Ranking de la Clase", "Mi Perfil"]
        
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
            
            # --- NUEVA LÓGICA DE META SEMANAL EN EL PANEL PRINCIPAL ---
            try:
                # Calculamos la fecha de inicio de esta semana (Lunes 00:00)
                fecha_inicio_semana = obtener_inicio_semana_actual()
                
                # Consultamos los ejercicios correctos de la semana actual
                res_progreso_semanal = supabase.table("user_progress") \
                    .select("ease_factor") \
                    .eq("user_id", st.session_state.user.id) \
                    .gte("last_reviewed", fecha_inicio_semana) \
                    .gt("repetitions", 0) \
                    .execute()
                
                # Calculamos los puntos (Pregunta Difícil < 2.5 = 2 pts, Fácil >= 2.5 = 1 pt)
                puntos_semanales = 0
                if res_progreso_semanal.data:
                    for registro in res_progreso_semanal.data:
                        if registro["ease_factor"] < 2.5:
                            puntos_semanales += 2
                        else:
                            puntos_semanales += 1
                            
            except Exception as e:
                puntos_semanales = 0
                st.error(f"Error al sincronizar meta semanal: {e}")              

            # 3. Renderizado de la Barra en el Panel Principal (Meta fija de 100)
            META_FIJA = 100
            st.markdown(f"### 🎯 Tu Meta Semanal: {puntos_semanales} / {META_FIJA} puntos")
            
            porcentaje_meta = min(puntos_semanales / META_FIJA, 1.0)
            st.progress(porcentaje_meta)
            
            if puntos_semanales >= META_FIJA:
                st.success("¡Excelente trabajo! 🎉 Has alcanzado tu meta de la semana.")
            else:
                st.caption(f"Te faltan {META_FIJA - puntos_semanales} puntos para cumplir tu meta. Se reinicia el domingo a la medianoche.")
            
            st.divider()
            
            # --- AQUÍ CONTINÚA TU LÓGICA NORMAL DE RUTA DE GRADOS ---
            RUTA_GRADOS = {
                "10-A 2026": ["Personal Information Basics", "Verb to be", "Present Simple"],
                "11-A 2026": ["Personal Information Basics", "Verb to be", "Present Simple"],
                "11-B 2026": ["Personal Information Basics", "Verb to be", "Present Simple"],
                "Grupo_Prueba": ["Personal Information Basics", "Verb to be", "Present Simple", "There is / There are", "Adjectives"],
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
                    
                    # --- NUEVA LÓGICA: ALEATORIZAR OPCIONES DE OPCIÓN MÚLTIPLE ---
                    if st.session_state.ejercicio_actual and st.session_state.ejercicio_actual.get('type') == 'multiple_choice':
                        opciones_originales = list(st.session_state.ejercicio_actual['content']['options'])
                        # Creamos una copia y la mezclamos para que no afecte el orden original de la base de datos
                        random.shuffle(opciones_originales)
                        st.session_state.opciones_mezcladas = opciones_originales
                    else:
                        st.session_state.opciones_mezcladas = []
                    
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
                        
                        # LEER LAS OPCIONES MEZCLADAS: Si por alguna razón está vacía, cae en el orden original por seguridad
                        opciones_a_mostrar = st.session_state.get('opciones_mezcladas', contenido['options'])
                        
                        resp_user = st.radio(
                            "Opciones:", 
                            opciones_a_mostrar, 
                            key=f"rad_{ex_id}", 
                            disabled=st.session_state.respondido
                        )
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
    
                            # --- CONTROL DE IA CON SESSION_STATE ---
                            if f"ver_explicacion_{ex_id}" not in st.session_state:
                                st.session_state[f"ver_explicacion_{ex_id}"] = False

                            col_ia, col_reporte = st.columns(2)

                            with col_ia:
                                if st.button("🤔 ¿Por qué me equivoqué?", key=f"expl_{ex_id}", use_container_width=True):
                                    st.session_state[f"ver_explicacion_{ex_id}"] = True

                            with col_reporte:
                                # El botón de reporte único y siempre visible si fallan
                                if ex_id != "ia_gen":
                                    if st.button("🚩 Mi respuesta es correcta", key=f"btn_reclamo_{ex_id}", use_container_width=True):
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

                            # Si el alumno pidió la explicación, se muestra abajo de los botones
                            if st.session_state[f"ver_explicacion_{ex_id}"]:
                                if item and 'content' in item:
                                    with st.spinner("El profe está revisando tu respuesta..."):
                                        pregunta_texto = item['content'].get('question', 'la frase anterior')
                                        respuesta_profe = str(item['content'].get('answer', '')).split('|')[0]
                                        tema_ejercicio = item.get('topic', 'Inglés')

                                        explicacion = explicar_error_ia(pregunta_texto, respuesta_profe, resp_user, tema_ejercicio)
                                        st.info(explicacion)
                                else:
                                    st.error("No se pudo recuperar la información del ejercicio para la IA.")

                        if st.button("Siguiente Ejercicio ➡️", use_container_width=True):
                            if not st.session_state.es_correcto: 
                                guardar_progreso(st.session_state.user.id, ex_id, 0)
                            st.session_state.ejercicio_actual = None
                            st.session_state.input_counter += 1
                            st.rerun()

            except Exception as e:
                st.error(f"Error en práctica: {e}")
            
        elif menu == "Mi Perfil":
            st.title("👤 Mi Perfil")
            st.write("Gestiona la información de tu cuenta. Mantén tus datos actualizados de forma segura.")
            
            # Traer los datos actuales en tiempo real directamente de Supabase
            try:
                datos_actuales = supabase.table("profiles").select("username").eq("id", st.session_state.user.id).single().execute()
                current_username = datos_actuales.data["username"] if datos_actuales.data else st.session_state.user.user_metadata.get("username", "")
            except:
                current_username = st.session_state.user.user_metadata.get("username", "")

            # --- SECCIÓN 1: ACTUALIZAR NOMBRE DE USUARIO ---
            st.subheader("📝 Cambiar Nombre de Usuario")
            nuevo_username = st.text_input("Nuevo nombre de usuario", value=current_username)
            if st.button("Actualizar Nombre", key="btn_update_user"):
                if nuevo_username.strip():
                    try:
                        # 1. Actualizar tabla pública 'profiles'
                        supabase.table("profiles").update({"username": nuevo_username.strip()}).eq("id", st.session_state.user.id).execute()
                        # 2. Actualizar metadatos de autenticación en Supabase
                        supabase.auth.update_user({"data": {"username": nuevo_username.strip()}})
                        st.success("¡Nombre de usuario actualizado con éxito! 🎉")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al actualizar el nombre: {e}")
                else:
                    st.error("El nombre de usuario no puede estar vacío.")

            st.divider()

            # --- SECCIÓN 2: ACTUALIZAR CORREO ELECTRÓNICO ---
            st.subheader("📧 Cambiar Correo Electrónico")
            st.caption(f"Correo actual: `{st.session_state.user.email}`")
            nuevo_correo = st.text_input("Nuevo Correo Electrónico")
            confirmar_correo = st.text_input("Confirmar Nuevo Correo")
            
            if st.button("Actualizar Correo", key="btn_update_email"):
                if not nuevo_correo or not confirmar_correo:
                    st.error("Todos los campos de correo son obligatorios.")
                elif nuevo_correo.strip().lower() != confirmar_correo.strip().lower():
                    st.error("Los correos electrónicos ingresados no coinciden.")
                else:
                    try:
                        # En Supabase, cambiar el correo envía confirmaciones por seguridad
                        supabase.auth.update_user({"email": nuevo_correo.strip().lower()})
                        st.success("📩 ¡Solicitud enviada! Se ha enviado un enlace de confirmación a tu nuevo correo para validar el cambio.")
                    except Exception as e:
                        st.error(f"Error al cambiar el correo: {e}")

            st.divider()

            # --- SECCIÓN 3: ACTUALIZAR CONTRASEÑA ---
            st.subheader("🔒 Cambiar Contraseña")
            nueva_pass = st.text_input("Nueva Contraseña", type="password")
            confirmar_pass = st.text_input("Confirmar Nueva Contraseña", type="password")
            
            if st.button("Actualizar Contraseña", key="btn_update_pass"):
                if not nueva_pass or not confirmar_pass:
                    st.error("Por favor, llena ambos campos de contraseña.")
                elif len(nueva_pass) < 6:
                    st.error("La nueva contraseña debe tener al menos 6 caracteres.")
                elif nueva_pass != confirmar_pass:
                    st.error("Las contraseñas no coinciden. Inténtalo de nuevo.")
                else:
                    try:
                        supabase.auth.update_user({"password": nueva_pass})
                        st.success("¡Contraseña actualizada correctamente! 🔒")
                    except Exception as e:
                        st.error(f"Error al cambiar la contraseña: {e}")
  
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
                  
                           c1, c2 = st.columns(2)
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
                         
                    
  #-------CERRAR SESIÓN------------------        
        st.sidebar.divider()
        if st.sidebar.button("Cerrar Sesión", use_container_width=True):
            controller.remove("sb_session")
            st.session_state.user = None            
if __name__ == "__main__":
    main()
