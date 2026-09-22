"""Product catalogue routes for the local dummy business API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path as PathParam
from pydantic import BaseModel, ConfigDict, Field


class Product(BaseModel):
    """Public product catalogue representation."""

    model_config = ConfigDict(extra="forbid")

    sku: str = Field(pattern=r"^PRODUCT-[0-9]{4}$")
    name: str
    category: str
    product_line: str
    size_ml: int | None = Field(default=None, gt=0)
    status: str
    markets: list[str]


def _load_products() -> dict[str, Product]:
    fixture_path = Path(__file__).parents[3] / "fixtures" / "products" / "products.json"
    records = json.loads(fixture_path.read_text(encoding="utf-8"))
    return {record["sku"]: Product.model_validate(record) for record in records}


PRODUCTS = _load_products()
router = APIRouter(prefix="/products", tags=["products"])


@router.get(
    "/{sku}",
    response_model=Product,
    operation_id="get_product",
    summary="Get a product by SKU",
    description="Returns synthetic catalogue data for a known product SKU.",
    responses={404: {"description": "Product SKU was not found"}},
)
def get_product(
    sku: Annotated[
        str,
        PathParam(description="Stable product identifier", pattern=r"^PRODUCT-[0-9]{4}$"),
    ],
) -> Product:
    """Return a deterministic product fixture or a not-found response."""

    product = PRODUCTS.get(sku)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product '{sku}' was not found")
    return product