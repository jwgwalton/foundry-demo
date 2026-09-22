"""FastAPI application for local synthetic business dependencies."""

from fastapi import FastAPI

from dummy_systems.business_api.products import router as products_router


app = FastAPI(
    title="Wella Foundry Demo Business API",
    version="0.1.0",
    description="Synthetic product and inventory services for local development.",
)
app.include_router(products_router)


@app.get("/health", tags=["health"], operation_id="get_health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}