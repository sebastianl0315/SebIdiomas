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
def validar_respuesta(intento, correcta):
    # .strip() quita espacios al inicio/final
    # .lower() convierte a minúsculas
    # .rstrip('.') quita el punto final si existe
    intento_limpio = intento.strip().lower().rstrip('.')
    correcta_limpia = correcta.strip().lower().rstrip('.')
    
    # Comparación directa de las versiones limpias
    return intento_limpio == correcta_limpia

def generar_ejercicio_ia(tema, tipo_ejercicio="translate"):
    api_key = st.secrets["GOOGLE_API_KEY"]
    
    # Usamos el alias que nos funcionó
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    
    # Instrucciones específicas para el contexto colombiano
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

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            res_json = response.json()
            texto = res_json['candidates'][0]['content']['parts'][0]['text']
            # Limpiamos el texto de posibles marcas de markdown
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
    # Si es un ejercicio de IA, no intentamos guardar progreso por ahora o usamos un ID especial
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
        f"Explica de forma breve, amable y en español de Colombia por qué la respuesta del estudiante es incorrecta "
        f"y cuál es la regla gramatical que debe aplicar. Máximo 3 oraciones."
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
    except:
        return "Lo siento, no pude conectar con el profe IA en este momento."
    return "No pude generar la explicación."

# --- 3. INTERFAZ PRINCIPAL ---

def main():
    st.set_page_config(
        page_title="SebIdiomas", 
        page_icon="favicon.png", # Aquí pones el nombre de tu archivo
        layout="centered"
        )
    
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
        st.sidebar.image("logo.png", use_container_width=True)      
        st.sidebar.title("     SebIdiomas")
        opciones = ["Práctica Diaria", "Ranking de la Clase"]
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

                # --- LÓGICA DE SELECCIÓN DE EJERCICIO ---
                if st.session_state.ejercicio_actual is None:
                    # 1. Obtener info del grupo
                    user_info = supabase.table("profiles").select("group_id, groups(group_name)").eq("id", st.session_state.user.id).single().execute()
                    nombre_grupo = user_info.data['groups']['group_name'] if user_info.data['groups'] else "Sin Grupo"
                    temas_permitidos = RUTA_GRADOS.get(nombre_grupo, ["Vocabulary A1"])
                    
                    # 2. Traer ejercicios de Supabase que coincidan con los temas
                    res_ex = supabase.table("exercises").select("*").in_("topic", temas_permitidos).execute()
                    
                    # 3. Traer progreso del usuario
                    res_prog = supabase.table("user_progress").select("exercise_id, next_review").eq("user_id", st.session_state.user.id).execute()
                    progreso_map = {p['exercise_id']: p['next_review'] for p in res_prog.data}
                    
                    ahora = datetime.datetime.now(datetime.timezone.utc)
                    
                    # 4. Filtrar: Ejercicios que nunca ha hecho O que ya toca repetir
                    pendientes = []
                    for ex in res_ex.data:
                        if ex['id'] not in progreso_map:
                            pendientes.append(ex)
                        else:
                            # Ajuste de formato de fecha para Python
                            fecha_repaso = datetime.datetime.fromisoformat(progreso_map[ex['id']].replace('Z', '+00:00'))
                            if ahora >= fecha_repaso:
                                pendientes.append(ex)

                    # 5. ASIGNACIÓN FINAL
                    if pendientes:
                        st.session_state.ejercicio_actual = random.choice(pendientes)
                    else:
                        # Solo si no hay nada en Supabase, llamamos a la IA
                        tema_para_ia = random.choice(temas_permitidos)
                        with st.spinner(f"Generando práctica de {tema_para_ia}..."):
                            nuevo_ejercicio = generar_ejercicio_ia(tema_para_ia)
                            if nuevo_ejercicio:
                                st.session_state.ejercicio_actual = nuevo_ejercicio
                            else:
                                st.error("No hay ejercicios disponibles ni conexión con la IA.")
                    
                    # Una sola recarga después de decidir qué ejercicio mostrar
                    st.session_state.respondido = False
                    st.session_state.es_correcto = False
                    st.rerun()

                # --- RENDERIZADO DEL EJERCICIO ---
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
                        # Mostramos las palabras desordenadas en un formato llamativo
                        palabras = contenido['words']
                        random.shuffle(palabras) # Las desordenamos por si acaso
                        st.info("**Ordena la oración:**")
                        st.subheader(f"🧩 {' / '.join(palabras)}") # Ejemplo: lives / in / She / El Paujil
                        resp_user = st.text_input("Tu respuesta:", key=f"scr_{ex_id}_{st.session_state.input_counter}").strip()
                        # El botón de verificar y la función validar_respuesta que ya tienes 
                        # funcionarán perfecto porque al final es una comparación de texto.

                    if not st.session_state.respondido:
                        if st.button("Verificar", use_container_width=True):
                            # --- 3. USO DE LA FUNCIÓN validar_respuesta ---
                            # Esto es lo que permite ignorar el punto final
                            respuestas_correctas = str(contenido['answer']).split('|')
                            
                            # Comprobamos si coincide con alguna de las opciones válidas usando tu lógica
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
                        # --- Dentro del bloque 'else' de respuesta incorrecta ---
                        else:                              
                            st.error(f"❌ La respuesta correcta era: {str(contenido['answer']).split('|')[0]}")
    
                            # Botón para pedir la explicación
                            if st.button("🤔 ¿Por qué me equivoqué? Explícame", key=f"expl_{ex_id}"):
                                # Usamos el 'item' que ya definiste arriba en la línea 268
                                if item and 'content' in item:
                                    with st.spinner("El profe está revisando tu respuesta..."):
                                        # Extraemos los datos de manera segura
                                        pregunta_texto = item['content'].get('question', 'la frase anterior')
                                        respuesta_profe = str(item['content'].get('answer', '')).split('|')[0]
                                        tema_ejercicio = item.get('topic', 'Inglés')

                                        explicacion = explicar_error_ia(
                                            pregunta_texto, 
                                            respuesta_profe, 
                                            resp_user,
                                            tema_ejercicio
                                        )
                                        st.info(explicacion)
                                else:
                                    st.error("No se pudo recuperar la información del ejercicio para la IA.")
                                      
                                if ex_id != "ia_gen":
                                    if st.button("Mi respuesta es correcta", key=f"btn_reclamo_{ex_id}"):
                                        try:
                                            # Usamos el ID directamente del objeto de sesión
                                            reporte = {
                                            "user_id": st.session_state.user.id, 
                                            "exercise_id": ex_id,
                                            "user_answer": str(resp_user),
                                            "expected_answer": str(contenido['answer']),
                                            "status": "pending"
                                            }
        
                                            # Ejecutar inserción
                                            res = supabase.table("exercise_reports").insert(reporte).execute()
                                            # Si no hubo excepción, procedemos
                                            st.success("✅ Reporte enviado. El Profe Sebastián lo revisará.")
                                            st.rerun()
                                        except Exception as e:
                                            # Si falla, imprimimos el error completo para debuggear
                                            st.error(f"Error al enviar: {e}")
                                            #except Exception:
                                            #st.warning("No se pudo enviar el reporte automáticamente, pero tu observación fue tomada en cuenta.")
                                            pass

                        if st.button("Siguiente Ejercicio ➡️", use_container_width=True):
                            if not st.session_state.es_correcto: 
                                guardar_progreso(st.session_state.user.id, ex_id, 0)
                            
                            # --- 4. RESETEO Y AUMENTO DEL CONTADOR ---
                            st.session_state.ejercicio_actual = None
                            st.session_state.input_counter += 1 # Esto limpia el campo para la próxima
                            st.rerun()

            except Exception as e:
                st.error(f"Error en práctica: {e}")
            
            # --- CÁLCULO DE META DINÁMICA ---
            try:
                # 1. Obtener la meta específica del grupo del usuario
                user_data = supabase.table("profiles").select("groups(weekly_goal)").eq("id", st.session_state.user.id).single().execute()
                meta_dinamica = user_data.data['groups']['weekly_goal'] if user_data.data['groups'] else 100

                # 2. Contar ejercicios de la última semana
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
            st.subheader("🚩 Reportes de Errores")
            try:
                res_reports = supabase.table("exercise_reports").select("id, user_answer, expected_answer, profiles(username), exercises(content, topic)").eq("status", "pending").execute()
                if not res_reports.data:
                    st.write("No hay reportes nuevos.")
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

            st.divider()
            st.subheader("Estudiantes por Grupo")
            try:
                res_est = supabase.table("profiles").select("id, username, groups(group_name)").execute()
                if res_est.data:
                    nombres_grupos = sorted(list(set([e['groups']['group_name'] for e in res_est.data if e['groups']])))
                    sel = st.selectbox("Seleccionar Grupo:", nombres_grupos)
                    for est in [e for e in res_est.data if e['groups'] and e['groups']['group_name'] == sel]:
                        st.write(f"👤 {est['username']}")
            except Exception as e:
                st.error(f"Error panel: {e}")
            
            st.divider()
            st.subheader("📈 Seguimiento de Metas")
            
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
            st.session_state.user = None
            st.rerun()

if __name__ == "__main__":
    main()
