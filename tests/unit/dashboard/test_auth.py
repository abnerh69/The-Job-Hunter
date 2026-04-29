import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from jobhunter.dashboard.auth import check_password, logout

@pytest.fixture
def mock_streamlit():
    with patch("jobhunter.dashboard.auth.st") as mock_st:
        mock_st.session_state = {}
        yield mock_st

@pytest.fixture
def mock_settings():
    with patch("jobhunter.dashboard.auth.Settings") as mock_s:
        mock_instance = MagicMock()
        mock_instance.DASHBOARD_PASSWORD.get_secret_value.return_value = "secret123"
        mock_instance.DASHBOARD_SESSION_TIMEOUT_MINUTES = 60
        mock_s.return_value = mock_instance
        yield mock_instance

def test_check_password_no_state(mock_streamlit, mock_settings):
    # Should show text input and return False if no state
    assert check_password() is False
    mock_streamlit.text_input.assert_called_once()

def test_check_password_correct(mock_streamlit, mock_settings):
    mock_streamlit.session_state["password"] = "secret123"

    # We need to simulate the callback manually since we are unit testing the logic
    # In streamlit, on_change calls the function.
    # The current implementation of check_password calls password_entered internally.
    # But password_entered is defined INSIDE check_password.
    # Wait, my implementation of check_password returns False if "password_correct" not in st.session_state.

    # Let's simulate what happens when password_entered is called.
    # Since I can't easily call the nested function, I'll test the state transitions.

    # If password is correct, password_entered sets password_correct = True
    # Let's mock the text_input to simulate user entry if we were doing E2E,
    # but here we test the logic of check_password given a state.

    mock_streamlit.session_state["password_correct"] = True
    mock_streamlit.session_state["last_login"] = datetime.now()

    assert check_password() is True

def test_check_password_incorrect(mock_streamlit, mock_settings):
    mock_streamlit.session_state["password_correct"] = False
    assert check_password() is False
    mock_streamlit.error.assert_called_with("😕 Password incorrect")

def test_check_password_timeout(mock_streamlit, mock_settings):
    mock_streamlit.session_state["password_correct"] = True
    mock_streamlit.session_state["last_login"] = datetime.now() - timedelta(minutes=61)

    assert check_password() is False
    assert mock_streamlit.session_state["password_correct"] is False
    mock_streamlit.rerun.assert_called_once()

def test_logout(mock_streamlit):
    mock_streamlit.session_state["password_correct"] = True
    logout()
    assert mock_streamlit.session_state["password_correct"] is False
    mock_streamlit.rerun.assert_called_once()
