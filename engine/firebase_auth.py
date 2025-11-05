"""
Firebase Authentication Module for Email/Password + OTP Verification
"""

import os
from typing import Optional, Dict, Tuple
import streamlit as st
from logzero import logger

# Optional Firebase imports
try:
    import pyrebase
except ImportError:
    pyrebase = None
    logger.warning("pyrebase4 not installed. Install with: pip install pyrebase4")

try:
    import firebase_admin
    from firebase_admin import credentials, auth
except ImportError:
    firebase_admin = None
    credentials = None
    auth = None
    logger.warning("firebase-admin not installed. Install with: pip install firebase-admin")


class FirebaseAuth:
    """Firebase Authentication handler with email/password and OTP verification"""
    
    def __init__(self, config: Dict):
        """
        Initialize Firebase Authentication.
        
        Args:
            config: Dictionary containing Firebase configuration:
                - apiKey
                - authDomain
                - projectId
                - storageBucket
                - messagingSenderId
                - appId
                - serviceAccount (optional, for admin operations)
        """
        self.config = config
        self.firebase = None
        self.auth = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Initialize Firebase app and auth"""
        if pyrebase is None:
            raise ImportError("pyrebase4 not installed. Install with: pip install pyrebase4")
        
        try:
            # Initialize Pyrebase for client-side operations
            firebase_config = {
                "apiKey": self.config.get("apiKey"),
                "authDomain": self.config.get("authDomain"),
                "projectId": self.config.get("projectId"),
                "storageBucket": self.config.get("storageBucket"),
                "messagingSenderId": self.config.get("messagingSenderId"),
                "appId": self.config.get("appId"),
                "databaseURL": self.config.get("databaseURL", "")
            }
            
            self.firebase = pyrebase.initialize_app(firebase_config)
            self.auth = self.firebase.auth()
            
            # Initialize Firebase Admin SDK if service account is provided (optional)
            if self.config.get("serviceAccount") and firebase_admin:
                try:
                    # Check if already initialized
                    if not firebase_admin._apps:
                        # If serviceAccount is a file path
                        if os.path.exists(self.config["serviceAccount"]):
                            cred = credentials.Certificate(self.config["serviceAccount"])
                            firebase_admin.initialize_app(cred)
                        elif isinstance(self.config["serviceAccount"], dict):
                            # If serviceAccount is a dict
                            cred = credentials.Certificate(self.config["serviceAccount"])
                            firebase_admin.initialize_app(cred)
                        logger.info("Firebase Admin SDK initialized")
                except Exception as e:
                    logger.warning(f"Firebase Admin SDK not initialized (optional): {e}")
            
            logger.info("Firebase Authentication initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            raise
    
    def sign_up(self, email: str, password: str, allowed_email: str = None) -> Tuple[bool, str, Optional[Dict]]:
        """
        Sign up a new user with email and password (restricted if allowed_email is set).
        
        Args:
            email: User email
            password: User password
            allowed_email: Only this email can sign up (if None, any email can sign up)
            
        Returns:
            Tuple of (success, message, user_info)
        """
        # Check if email is restricted
        if allowed_email and email.lower() != allowed_email.lower():
            return False, f"Sign up is restricted. Only authorized email can create an account.", None
        
        try:
            user = self.auth.create_user_with_email_and_password(email, password)
            # Send email verification
            self.auth.send_email_verification(user['idToken'])
            return True, "Account created successfully. Please verify your email.", user
        except Exception as e:
            error_msg = str(e)
            if "EMAIL_EXISTS" in error_msg:
                return False, "Email already exists. Please login instead.", None
            elif "WEAK_PASSWORD" in error_msg:
                return False, "Password is too weak. Please use a stronger password.", None
            else:
                return False, f"Sign up failed: {error_msg}", None
    
    def sign_in(self, email: str, password: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Sign in with email and password.
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Tuple of (success, message, user_info)
        """
        try:
            user = self.auth.sign_in_with_email_and_password(email, password)
            
            # Check if email is verified
            user_info = self.auth.get_account_info(user['idToken'])
            email_verified = user_info['users'][0].get('emailVerified', False)
            
            if not email_verified:
                # Send verification email
                self.auth.send_email_verification(user['idToken'])
                return False, "Email not verified. Verification email sent. Please check your inbox.", None
            
            return True, "Login successful", user
            
        except Exception as e:
            error_msg = str(e)
            if "INVALID_PASSWORD" in error_msg or "INVALID_EMAIL" in error_msg:
                return False, "Invalid email or password.", None
            elif "USER_NOT_FOUND" in error_msg:
                return False, "User not found. Please sign up first.", None
            else:
                return False, f"Login failed: {error_msg}", None
    
    def send_password_reset(self, email: str) -> Tuple[bool, str]:
        """
        Send password reset email.
        
        Args:
            email: User email
            
        Returns:
            Tuple of (success, message)
        """
        try:
            self.auth.send_password_reset_email(email)
            return True, "Password reset email sent. Please check your inbox."
        except Exception as e:
            error_msg = str(e)
            if "USER_NOT_FOUND" in error_msg:
                return False, "User not found. Please sign up first."
            else:
                return False, f"Failed to send reset email: {error_msg}"
    
    def send_email_verification(self, id_token: str) -> Tuple[bool, str]:
        """
        Send email verification OTP.
        
        Args:
            id_token: User ID token
            
        Returns:
            Tuple of (success, message)
        """
        try:
            self.auth.send_email_verification(id_token)
            return True, "Verification email sent. Please check your inbox."
        except Exception as e:
            return False, f"Failed to send verification email: {str(e)}"
    
    def verify_email(self, id_token: str) -> Tuple[bool, str]:
        """
        Verify email (check if verified after user clicks link).
        
        Args:
            id_token: User ID token
            
        Returns:
            Tuple of (success, message)
        """
        try:
            user_info = self.auth.get_account_info(id_token)
            email_verified = user_info['users'][0].get('emailVerified', False)
            
            if email_verified:
                return True, "Email verified successfully."
            else:
                return False, "Email not yet verified. Please check your email."
        except Exception as e:
            return False, f"Verification check failed: {str(e)}"
    
    def get_user_info(self, id_token: str) -> Optional[Dict]:
        """
        Get user information from ID token.
        
        Args:
            id_token: User ID token
            
        Returns:
            User information dictionary
        """
        try:
            user_info = self.auth.get_account_info(id_token)
            return user_info['users'][0] if user_info.get('users') else None
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None
    
    def refresh_token(self, refresh_token: str) -> Optional[Dict]:
        """
        Refresh the authentication token.
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            New user info with tokens
        """
        try:
            user = self.auth.refresh(refresh_token)
            return user
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            return None
    
    def sign_out(self):
        """Sign out the current user"""
        try:
            if 'user' in st.session_state:
                del st.session_state['user']
            if 'id_token' in st.session_state:
                del st.session_state['id_token']
            if 'refresh_token' in st.session_state:
                del st.session_state['refresh_token']
            logger.info("User signed out")
        except Exception as e:
            logger.error(f"Sign out failed: {e}")

