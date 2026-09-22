from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.security import safe_resolve_path, PathTraversalError

client = TestClient(app)

def test_safe_resolve_path_valid():
    base_dir = Path("O:/mock/repo/data").resolve(strict=False)
    result = safe_resolve_path(base_dir, "processed")
    assert str(result) == str(base_dir / "processed")

def test_safe_resolve_path_traversal():
    base_dir = Path("/mock/repo/data")
    with pytest.raises(PathTraversalError):
        safe_resolve_path(base_dir, "../../etc/passwd")

def test_payload_size_limit():
    # Simulate a giant payload (assuming the middleware triggers)
    large_payload = "A" * (100 * 1024 * 1024 + 1)
    
    # Send request with content-length header mocking a large payload
    headers = {"Content-Length": str(len(large_payload))}
    response = client.post("/analytics/rules/run", headers=headers, json={"input_path": "fake"})
    
    # We expect HTTP 413 Payload Too Large
    assert response.status_code == 413
    assert "Payload too large" in response.json()["detail"]

def test_api_rejection_of_path_traversal():
    # Test one of the endpoints
    response = client.post(
        "/analytics/rules/run",
        json={
            "input_path": "../../../etc/passwd"
        }
    )
    # The global exception handler should catch PathTraversalError and return 400
    assert response.status_code == 400
    assert "Invalid or disallowed path" in response.json()["detail"]
