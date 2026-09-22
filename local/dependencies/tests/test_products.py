from fastapi.testclient import TestClient

from dummy_systems.business_api.app import app


client = TestClient(app)


def test_get_product_returns_typed_catalogue_data() -> None:
    response = client.get("/products/PRODUCT-1042")

    assert response.status_code == 200
    assert response.json() == {
        "sku": "PRODUCT-1042",
        "name": "Professional Permanent Colour 8/1",
        "category": "hair_colour",
        "product_line": "Professional Colour",
        "size_ml": 60,
        "status": "active",
        "markets": ["GB", "DE", "FR"],
    }


def test_get_product_returns_not_found_for_unknown_sku() -> None:
    response = client.get("/products/PRODUCT-9999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Product 'PRODUCT-9999' was not found"}


def test_get_product_rejects_malformed_sku() -> None:
    response = client.get("/products/not-a-sku")

    assert response.status_code == 422


def test_product_route_has_stable_operation_id_and_no_security_requirement() -> None:
    response = client.get("/openapi.json")
    operation = response.json()["paths"]["/products/{sku}"]["get"]

    assert operation["operationId"] == "get_product"
    assert "security" not in operation


def test_health_endpoint_is_available() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}