from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

try:
    # MCP Python SDK
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise ImportError(
        "The 'mcp' package is required. Install it with: pip install mcp"
    ) from exc


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PRODUCTS_FILE = DATA_DIR / "products.json"
STORES_FILE = DATA_DIR / "stores.json"
INVENTORY_FILE = DATA_DIR / "inventory.json"

mcp = FastMCP("zava-inventory-server")


# -----------------------------
# Pydantic schemas
# -----------------------------
class Product(BaseModel):
    productId: int = Field(..., description="Unique numeric product identifier")
    sku: str = Field(..., description="Stock keeping unit, e.g. WBH-001")
    name: str = Field(..., description="Display product name")
    category: str = Field(..., description="Business category")
    description: str = Field(..., description="Human-friendly product description")
    price: float = Field(..., ge=0, description="Unit price in USD")


class NewProductInput(BaseModel):
    sku: str = Field(..., description="Unique SKU for the new product")
    name: str = Field(..., description="Display product name")
    category: str = Field(..., description="Business category")
    description: str = Field(..., description="Human-friendly product description")
    price: float = Field(..., ge=0, description="Unit price in USD")
    initialQuantityByStore: dict[int, int] = Field(
        default_factory=dict,
        description="Optional map of storeId -> starting inventory quantity",
    )
    reorderLevel: int = Field(
        10,
        ge=0,
        description="Threshold that indicates when the item should be reordered",
    )


class Store(BaseModel):
    id: int = Field(..., description="Unique numeric store identifier")
    name: str = Field(..., description="Store display name")
    address: str = Field(..., description="Store street address")
    city: str = Field(..., description="Store city")
    country: str = Field(..., description="Store country")


class InventoryItem(BaseModel):
    id: int = Field(..., description="Unique inventory row identifier")
    storeId: int = Field(..., description="Store identifier")
    productId: int = Field(..., description="Product identifier")
    sku: str = Field(..., description="Product SKU")
    productName: str = Field(..., description="Product name copy for quick display")
    productCategory: str = Field(..., description="Product category copy for quick display")
    productDescription: str = Field(..., description="Product description copy for quick display")
    price: float = Field(..., ge=0, description="Unit price in USD")
    quantity: int = Field(..., ge=0, description="On-hand quantity in that store")
    reorderLevel: int = Field(..., ge=0, description="Reorder threshold")
    inStock: bool = Field(..., description="Whether quantity is greater than zero")


class InventoryAdjustmentInput(BaseModel):
    storeId: int = Field(..., description="Store identifier")
    sku: str = Field(..., description="Product SKU to update")
    quantity: int = Field(..., ge=0, description="New on-hand quantity")
    reorderLevel: Optional[int] = Field(
        None,
        ge=0,
        description="Optional new reorder level for this store-product row",
    )


# -----------------------------
# File helpers
# -----------------------------
def _read_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)



def _write_json(path: Path, payload: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)



def _load_products() -> list[dict[str, Any]]:
    return _read_json(PRODUCTS_FILE)



def _save_products(products: list[dict[str, Any]]) -> None:
    _write_json(PRODUCTS_FILE, products)



def _load_stores() -> list[dict[str, Any]]:
    return _read_json(STORES_FILE)



def _load_inventory() -> list[dict[str, Any]]:
    return _read_json(INVENTORY_FILE)



def _save_inventory(inventory: list[dict[str, Any]]) -> None:
    _write_json(INVENTORY_FILE, inventory)



def _next_id(rows: list[dict[str, Any]], id_field: str = "id") -> int:
    if not rows:
        return 1
    return max(int(row[id_field]) for row in rows) + 1



def _find_store_by_id(store_id: int) -> Optional[dict[str, Any]]:
    return next((s for s in _load_stores() if int(s["id"]) == int(store_id)), None)



def _find_product_by_sku(sku: str) -> Optional[dict[str, Any]]:
    sku_normalized = sku.strip().lower()
    return next((p for p in _load_products() if p["sku"].strip().lower() == sku_normalized), None)


# -----------------------------
# MCP tools
# -----------------------------
@mcp.tool()
def get_products(
    category: Optional[str] = None,
    sku: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
) -> list[Product]:
    """Return products, optionally filtered by category, SKU, or free-text search."""
    products = _load_products()

    if category:
        products = [p for p in products if p["category"].lower() == category.strip().lower()]
    if sku:
        products = [p for p in products if p["sku"].lower() == sku.strip().lower()]
    if search:
        q = search.strip().lower()
        products = [
            p for p in products
            if q in p["name"].lower()
            or q in p["description"].lower()
            or q in p["category"].lower()
            or q in p["sku"].lower()
        ]

    limit = max(1, min(limit, 200))
    return [Product(**p) for p in products[:limit]]


@mcp.tool()
def get_product_by_sku(sku: str) -> Product:
    """Return one product by SKU."""
    product = _find_product_by_sku(sku)
    if not product:
        raise ValueError(f"No product found for SKU '{sku}'.")
    return Product(**product)


@mcp.tool()
def add_product(payload: NewProductInput) -> dict[str, Any]:
    """Add a new product and optionally seed inventory rows by store."""
    products = _load_products()
    inventory = _load_inventory()
    stores = _load_stores()

    if any(p["sku"].strip().lower() == payload.sku.strip().lower() for p in products):
        raise ValueError(f"SKU '{payload.sku}' already exists.")

    new_product = Product(
        productId=_next_id(products, "productId"),
        sku=payload.sku,
        name=payload.name,
        category=payload.category,
        description=payload.description,
        price=payload.price,
    )
    products.append(new_product.model_dump())
    _save_products(products)

    next_inventory_id = _next_id(inventory, "id")
    seeded_rows = []
    valid_store_ids = {int(s["id"]) for s in stores}

    for store_id, qty in payload.initialQuantityByStore.items():
        if int(store_id) not in valid_store_ids:
            raise ValueError(f"Store id '{store_id}' does not exist.")

        row = InventoryItem(
            id=next_inventory_id,
            storeId=int(store_id),
            productId=new_product.productId,
            sku=new_product.sku,
            productName=new_product.name,
            productCategory=new_product.category,
            productDescription=new_product.description,
            price=new_product.price,
            quantity=int(qty),
            reorderLevel=payload.reorderLevel,
            inStock=int(qty) > 0,
        )
        seeded_rows.append(row.model_dump())
        next_inventory_id += 1

    if seeded_rows:
        inventory.extend(seeded_rows)
        _save_inventory(inventory)

    return {
        "message": "Product added successfully.",
        "product": new_product.model_dump(),
        "seededInventoryRows": seeded_rows,
    }


@mcp.tool()
def get_stores() -> list[Store]:
    """Return all stores."""
    return [Store(**s) for s in _load_stores()]


@mcp.tool()
def list_inventory_by_store(
    store_id: Optional[int] = None,
    store_name: Optional[str] = None,
    low_stock_only: bool = False,
) -> dict[str, Any]:
    """Return inventory rows for a store, resolved by store_id or store_name."""
    stores = _load_stores()
    inventory = _load_inventory()

    if store_id is None and not store_name:
        raise ValueError("Provide either store_id or store_name.")

    store = None
    if store_id is not None:
        store = next((s for s in stores if int(s["id"]) == int(store_id)), None)
    elif store_name:
        store = next((s for s in stores if s["name"].strip().lower() == store_name.strip().lower()), None)

    if not store:
        raise ValueError("Store not found.")

    rows = [r for r in inventory if int(r["storeId"]) == int(store["id"])]
    if low_stock_only:
        rows = [r for r in rows if int(r["quantity"]) <= int(r.get("reorderLevel", 0))]

    rows.sort(key=lambda r: (r["productCategory"], r["productName"]))
    return {
        "store": store,
        "itemCount": len(rows),
        "items": [InventoryItem(**r).model_dump() for r in rows],
    }


@mcp.tool()
def update_inventory(payload: InventoryAdjustmentInput) -> dict[str, Any]:
    """Update quantity/reorderLevel for a specific store + SKU inventory row."""
    inventory = _load_inventory()

    target = next(
        (
            r for r in inventory
            if int(r["storeId"]) == int(payload.storeId)
            and r["sku"].strip().lower() == payload.sku.strip().lower()
        ),
        None,
    )

    if not target:
        raise ValueError(
            f"No inventory row found for storeId={payload.storeId} and sku='{payload.sku}'."
        )

    target["quantity"] = int(payload.quantity)
    target["inStock"] = int(payload.quantity) > 0
    if payload.reorderLevel is not None:
        target["reorderLevel"] = int(payload.reorderLevel)

    _save_inventory(inventory)

    return {
        "message": "Inventory updated successfully.",
        "inventoryItem": InventoryItem(**target).model_dump(),
    }


@mcp.tool()
def get_inventory_summary() -> dict[str, Any]:
    """Return high-level counts for quick dashboarding/testing."""
    products = _load_products()
    stores = _load_stores()
    inventory = _load_inventory()

    total_units = sum(int(row["quantity"]) for row in inventory)
    low_stock_rows = [row for row in inventory if int(row["quantity"]) <= int(row.get("reorderLevel", 0))]

    return {
        "productCount": len(products),
        "storeCount": len(stores),
        "inventoryRowCount": len(inventory),
        "totalUnits": total_units,
        "lowStockRowCount": len(low_stock_rows),
    }


if __name__ == "__main__":
    # Runs over stdio, which is the most common transport for local MCP integrations.
    mcp.run()
