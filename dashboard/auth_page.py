"""
Firebase Authentication Page Component
"""

import json
import os
from datetime import datetime
import streamlit as st
from engine.firebase_auth import FirebaseAuth
from logzero import logger

_SESSION_STORE_PATH = os.path.join("logs", ".firebase_session.json")


def _ensure_session_store_dir():
    directory = os.path.dirname(_SESSION_STORE_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)


def persist_firebase_session(user_email: str, id_token: str, refresh_token: str) -> None:
    """Persist Firebase session tokens to disk for browser refresh resilience."""
    try:
        if not user_email or not refresh_token:
            return
        _ensure_session_store_dir()
        payload = {
            "user_email": user_email,
            "id_token": id_token,
            "refresh_token": refresh_token,
            "saved_at": datetime.utcnow().isoformat() + "Z",
        }
        with open(_SESSION_STORE_PATH, "w", encoding="utf-8") as fp:
            json.dump(payload, fp)
        logger.debug("Firebase session persisted to disk")
    except Exception as exc:
        logger.warning(f"Unable to persist Firebase session: {exc}")


def load_persisted_firebase_session() -> dict:
    """Load persisted Firebase session tokens if available."""
    try:
        if not os.path.exists(_SESSION_STORE_PATH):
            return {}
        with open(_SESSION_STORE_PATH, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        logger.warning(f"Unable to load persisted Firebase session: {exc}")
        return {}


def clear_persisted_firebase_session() -> None:
    """Remove persisted Firebase session tokens."""
    try:
        if os.path.exists(_SESSION_STORE_PATH):
            os.remove(_SESSION_STORE_PATH)
            logger.debug("Firebase session persistence cleared")
    except Exception as exc:
        logger.warning(f"Unable to clear persisted Firebase session: {exc}")


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
                            # Set session state FIRST, before rerun
                            st.session_state.user = user
                            st.session_state.id_token = user['idToken']
                            st.session_state.refresh_token = user['refreshToken']
                            st.session_state.user_email = email.lower()  # Normalize email to lowercase
                            st.session_state.authenticated = True
                            
                            # Persist session to disk
                            persist_firebase_session(email, user['idToken'], user['refreshToken'])
                            
                            # Force rerun to show dashboard
                            logger.info(f"Login successful for {email}. Triggering rerun...")
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

