with col_login:
    if st.button("Entrar", use_container_width=True):
        res = login_user(email, password)
        if res:
            st.session_state.user = res.user
            st.session_state.cookies_initialized = True # <-- Evita que el validador de F5 espere tras el login manual
            
            # Guardamos los tokens en una cookie que dure 30 días
            session_data = {
                "access_token": res.session.access_token,
                "refresh_token": res.session.refresh_token
            }
            
            # Protegemos la escritura de la cookie contra desincronizaciones del JS interno
            try:
                controller.set("sb_session", session_data, expires=datetime.datetime.now() + datetime.timedelta(days=30))
            except TypeError:
                # Si el componente de cookies no está listo para escribir en este milisegundo,
                # se ignora el error. El st.session_state.user ya está asignado, por lo que la app entrará.
                pass
                
            st.rerun()
