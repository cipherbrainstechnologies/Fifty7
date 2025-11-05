"""
Firebase Authentication Page Component
"""

import streamlit as st
from engine.firebase_auth import FirebaseAuth
from logzero import logger


def render_login_page(firebase_auth: FirebaseAuth, allowed_email: str = None):
    """
    Render login page with email/password - restricted to single static email.
    
    Args:
        firebase_auth: FirebaseAuth instance
        allowed_email: Only email allowed to login (if None, allows any)
    """
    st.title("🔐 NIFTY Options Trading System")
    st.markdown("### Login to Access Dashboard")
    
    # Show allowed email if restricted
    if allowed_email:
        st.info(f"📧 Authorized Email: `{allowed_email}`")
        st.caption("Only this email address can access the dashboard.")
    
    st.divider()
    _render_login_form(firebase_auth, allowed_email)


def _render_login_form(firebase_auth: FirebaseAuth, allowed_email: str = None):
    """Render login form - restricted to allowed email only"""
    st.subheader("Login")
    
    # Pre-fill email if restricted
    email_value = allowed_email if allowed_email else ""
    
    with st.form("login_form"):
        email = st.text_input(
            "Email", 
            value=email_value,
            placeholder="your.email@example.com",
            disabled=bool(allowed_email)  # Disable if email is restricted
        )
        
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        
        col1, col2 = st.columns(2)
        with col1:
            login_button = st.form_submit_button("Login", use_container_width=True, type="primary")
        with col2:
            reset_button = st.form_submit_button("Forgot Password?", use_container_width=True)
        
        if login_button:
            if not email or not password:
                st.error("Please enter both email and password")
            elif allowed_email and email.lower() != allowed_email.lower():
                st.error(f"❌ Access Denied. Only authorized email ({allowed_email}) can login.")
            else:
                with st.spinner("Logging in..."):
                    success, message, user = firebase_auth.sign_in(email, password)
                    if success:
                        # Double check email matches (case-insensitive)
                        if allowed_email and email.lower() != allowed_email.lower():
                            st.error(f"❌ Access Denied. Only authorized email can login.")
                            firebase_auth.sign_out()
                        else:
                            st.session_state.user = user
                            st.session_state.id_token = user['idToken']
                            st.session_state.refresh_token = user['refreshToken']
                            st.session_state.user_email = email
                            st.session_state.authenticated = True
                            st.success(message)
                            st.rerun()
                    else:
                        st.error(message)
        
        if reset_button:
            if not email:
                st.error("Please enter your email address")
            elif allowed_email and email.lower() != allowed_email.lower():
                st.error(f"❌ Only authorized email ({allowed_email}) can reset password.")
            else:
                with st.spinner("Sending password reset email..."):
                    success, message = firebase_auth.send_password_reset(email)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)

