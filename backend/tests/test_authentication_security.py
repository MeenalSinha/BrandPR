import time
import uuid
import pytest
from app.core.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings


def test_password_hashing_and_verification():
    raw_pass = "super_secure_password_123"
    hashed = hash_password(raw_pass)
    assert hashed.startswith("pbkdf2:sha256:100000$")
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("wrong_password", hashed) is False
    # Ensure two hashes of the same password produce distinct salts
    assert hash_password(raw_pass) != hashed


def test_jwt_token_creation_and_tamper_detection():
    payload = {"sub": "user-123", "name": "Alice", "role": "creator", "brand_ids": ["*"]}
    token = create_access_token(payload, expires_in=3600)
    decoded = decode_access_token(token)
    assert decoded["sub"] == "user-123"
    assert decoded["role"] == "creator"

    # Tampered signature
    parts = token.split(".")
    tampered_sig = parts[0] + "." + parts[1] + ".invalidSignature123"
    with pytest.raises(ValueError, match="Invalid cryptographic token signature"):
        decode_access_token(tampered_sig)

    # Tampered payload
    tampered_payload = "eyJuYW1lIjoiTWFsaWNpb3VzIn0." + parts[1] + "." + parts[2]
    with pytest.raises(ValueError, match="Invalid cryptographic token signature"):
        decode_access_token(tampered_payload)


def test_jwt_token_expiration():
    payload = {"sub": "user-exp", "name": "Bob", "role": "creator"}
    expired_token = create_access_token(payload, expires_in=-10)
    with pytest.raises(ValueError, match="expired"):
        decode_access_token(expired_token)


def test_production_mode_rejects_caller_asserted_headers(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(get_settings(), "app_env", "production")

    # Attempting to access protected actor endpoint with only X-Actor headers in production
    r = client.get(
        "/api/auth/me",
        headers={"X-Actor-Name": "Attacker", "X-Actor-Role": "admin"},
    )
    assert r.status_code == 401
    err = r.json().get("error", {})
    assert err.get("code") == "unauthorized"


def test_public_registration_cannot_escalate_to_reviewer_or_admin(client):
    r = client.post(
        "/api/auth/register",
        json={
            "name": "Malicious User",
            "email": "malicious@test.internal",
            "password": "password123",
            "role": "admin",  # Attempts to elevate to admin
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["user"]["role"] == "creator"  # Strictly defaulted to creator

    # Decode returned token and check claims
    token_claims = decode_access_token(data["access_token"])
    assert token_claims["role"] == "creator"


def test_login_flow_credentials_and_tokens(client):
    # Invalid password
    r = client.post(
        "/api/auth/login",
        json={"email": "creator@brandpr.internal", "password": "wrong_password"},
    )
    assert r.status_code == 401

    # Valid demo creator
    r = client.post(
        "/api/auth/login",
        json={"email": "creator@brandpr.internal", "password": "brandpr_creator_demo"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert token
    assert r.json()["user"]["role"] == "creator"

    # Use token to call /auth/me
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "creator"
    assert me_resp.json()["is_creator"] is True
    assert me_resp.json()["is_reviewer"] is False


def test_creator_cannot_perform_reviewer_operations(client, brand):
    # Create fact as creator
    f_res = client.post(
        f"/api/brands/{brand['id']}/facts",
        json={
            "name": "Chip speed",
            "value": "3.5 GHz",
            "category": "product_spec",
            "qualifications": "Standard testing",
            "owner": "Hardware Team",
            "source_note": "Engineering validation",
        },
        headers={"X-Actor-Name": "Morgan Creator", "X-Actor-Role": "creator"},
    )
    assert f_res.status_code == 201
    fact_id = f_res.json()["id"]

    # Propose material change
    p_res = client.patch(
        f"/api/facts/{fact_id}",
        json={
            "name": "Chip speed",
            "value": "4.0 GHz",
            "category": "product_spec",
            "qualifications": "Turbo boost",
            "owner": "Hardware Team",
        },
        headers={"X-Actor-Name": "Morgan Creator", "X-Actor-Role": "creator"},
    )
    assert p_res.status_code == 200

    # Creator tries to approve the fact -> 403 Forbidden
    creator_token = create_access_token({"sub": "c1", "name": "Creator", "role": "creator", "brand_ids": ["*"]})
    appr_res = client.post(
        f"/api/facts/{fact_id}/approve",
        json={"approval_notes": "I want my own edit approved."},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert appr_res.status_code == 403
    assert appr_res.json()["error"]["code"] == "reviewer_role_required"

    # Reviewer approves -> 200 OK
    reviewer_token = create_access_token({"sub": "r1", "name": "Reviewer", "role": "reviewer", "brand_ids": ["*"]})
    appr_ok = client.post(
        f"/api/facts/{fact_id}/approve",
        json={"approval_notes": "Verified with Hardware lead."},
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert appr_ok.status_code == 200
    assert appr_ok.json()["status"] == "active"
    assert appr_ok.json()["version"] == 3


def test_cross_brand_access_denial(client, brand, other_brand):
    # Create a fact in other_brand
    f_res = client.post(
        f"/api/brands/{other_brand['id']}/facts",
        json={
            "name": "Secret metric",
            "value": "Confidential",
            "category": "general",
            "qualifications": "Classified",
            "owner": "Other Team",
            "source_note": "Internal doc",
        },
        headers={"X-Actor-Name": "Other Person", "X-Actor-Role": "creator"},
    )
    assert f_res.status_code == 201
    other_fact_id = f_res.json()["id"]

    # Actor restricted strictly to 'brand' (cannot access 'other_brand')
    restricted_token = create_access_token(
        {
            "sub": "restricted-user",
            "name": "Brand A User",
            "role": "creator",
            "brand_ids": [str(brand["id"])],
        }
    )

    # Attempt to read fact from other_brand
    r = client.get(
        f"/api/facts/{other_fact_id}",
        headers={"Authorization": f"Bearer {restricted_token}"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "brand_access_denied"
