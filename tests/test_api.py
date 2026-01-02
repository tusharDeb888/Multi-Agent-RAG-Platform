"""
Tests for API endpoints.
"""
import pytest
from fastapi.testclient import TestClient

def test_login(client, test_user):
    """Test login endpoint."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "testpass"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_upload_document(client, auth_headers):
    """Test document upload."""
    # Create a dummy PDF file
    files = {"file": ("test.pdf", b"%PDF-1.4 content", "application/pdf")}
    
    response = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers,
        files=files
    )
    
    assert response.status_code == 202
    data = response.json()
    assert data["filename"] == "test.pdf"
    assert data["status"] == "pending"

def test_list_documents(client, auth_headers):
    """Test listing documents."""
    response = client.get("/api/v1/documents/", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
