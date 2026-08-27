import io
import json
import urllib.error
from unittest.mock import MagicMock, patch
import pytest
from src.auth.facebook_auth import (
    get_facebook_credentials,
    MetaTokenInvalidError
)

@pytest.fixture
def mock_secret_client():
    with patch("src.auth.facebook_auth.secretmanager.SecretManagerServiceClient") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client
        yield mock_client

@pytest.fixture
def mock_urlopen():
    with patch("src.auth.facebook_auth.urllib.request.urlopen") as mock_open:
        yield mock_open

def test_get_facebook_credentials_success(mock_secret_client, mock_urlopen):
    # Setup Secret Manager Mock
    mock_response = MagicMock()
    mock_response.payload.data.decode.return_value = "mock_system_user_token"
    mock_secret_client.access_secret_version.return_value = mock_response

    # Setup Meta Graph API mock response
    mock_api_response = MagicMock()
    mock_api_response.read.return_value = json.dumps({
        "data": [
            {
                "id": "1089665547569807",
                "name": "WealthWise Daily",
                "access_token": "mock_page_token_123",
                "tasks": ["CREATE_CONTENT"]
            },
            {
                "id": "1154316767774881",
                "name": "The Thinking Room",
                "access_token": "mock_page_token_abc",
                "tasks": ["CREATE_CONTENT"]
            }
        ]
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_api_response

    token = get_facebook_credentials("wealthwise", "1089665547569807")
    assert token == "mock_page_token_123"

def test_get_facebook_credentials_missing_page(mock_secret_client, mock_urlopen):
    # Setup Secret Manager Mock
    mock_response = MagicMock()
    mock_response.payload.data.decode.return_value = "mock_system_user_token"
    mock_secret_client.access_secret_version.return_value = mock_response

    # Page ID not in resolved list
    mock_api_response = MagicMock()
    mock_api_response.read.return_value = json.dumps({
        "data": [
            {
                "id": "999999999999999",
                "name": "Some Other Page",
                "access_token": "mock_other_token",
                "tasks": ["CREATE_CONTENT"]
            }
        ]
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_api_response

    with pytest.raises(MetaTokenInvalidError) as exc_info:
        get_facebook_credentials("wealthwise", "1089665547569807")
    
    assert "was not found in the resolved accounts of the System User" in str(exc_info.value)

def test_get_facebook_credentials_oauth_190_error(mock_secret_client, mock_urlopen):
    # Setup Secret Manager Mock
    mock_response = MagicMock()
    mock_response.payload.data.decode.return_value = "mock_system_user_token"
    mock_secret_client.access_secret_version.return_value = mock_response

    # Setup Meta API Error 190 (Invalid OAuth Token)
    error_payload = json.dumps({
        "error": {
            "message": "Error validating access token: Session has expired.",
            "type": "OAuthException",
            "code": 190,
            "error_subcode": 463
        }
    }).encode("utf-8")
    
    mock_err_response = io.BytesIO(error_payload)
    mock_err_response.code = 400
    mock_err_response.msg = "Bad Request"
    
    http_error = urllib.error.HTTPError(
        url="https://graph.facebook.com/v26.0/me/accounts",
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=mock_err_response
    )
    mock_urlopen.side_effect = http_error

    with pytest.raises(MetaTokenInvalidError) as exc_info:
        get_facebook_credentials("wealthwise", "1089665547569807")
        
    assert "access token is invalid or expired" in str(exc_info.value)
    assert "code=190" in str(exc_info.value)

def test_get_facebook_credentials_other_api_error(mock_secret_client, mock_urlopen):
    # Setup Secret Manager Mock
    mock_response = MagicMock()
    mock_response.payload.data.decode.return_value = "mock_system_user_token"
    mock_secret_client.access_secret_version.return_value = mock_response

    # Setup other Meta API Error (e.g., Code 100 - Invalid parameter)
    error_payload = json.dumps({
        "error": {
            "message": "Invalid parameter value.",
            "type": "FacebookApiException",
            "code": 100
        }
    }).encode("utf-8")
    
    mock_err_response = io.BytesIO(error_payload)
    mock_err_response.code = 400
    mock_err_response.msg = "Bad Request"
    
    http_error = urllib.error.HTTPError(
        url="https://graph.facebook.com/v26.0/me/accounts",
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=mock_err_response
    )
    mock_urlopen.side_effect = http_error

    with pytest.raises(RuntimeError) as exc_info:
        get_facebook_credentials("wealthwise", "1089665547569807")
        
    assert "Meta Graph API HTTP 400 Error (code=100)" in str(exc_info.value)

def test_get_facebook_credentials_secret_manager_failure(mock_secret_client):
    # Setup Secret Manager Failure
    mock_secret_client.access_secret_version.side_effect = Exception("Connection Timeout")

    with pytest.raises(RuntimeError) as exc_info:
        get_facebook_credentials("wealthwise", "1089665547569807")
        
    assert "Secret Manager retrieval failed" in str(exc_info.value)
