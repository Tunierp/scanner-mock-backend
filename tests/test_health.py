def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_url_uses_uniform_error_format(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json() == {"success": False, "error": {"code": "NOT_FOUND", "message": "Ressource introuvable."}}
