from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PRODUCTS_FILE = DATA_DIR / "products.json"
STORES_FILE = DATA_DIR / "stores.json"
INVENTORY_FILE = DATA_DIR / "inventory.json"


class DataFileError(Exception):
    """Raised when a JSON data file is invalid or cannot be processed."""


def ensure_data_dir() -> Path:
    """Ensure the data directory exists and return it."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def read_json_file(path: Path) -> list[dict[str, Any]]:
    """Read a JSON array file and return a list of dictionaries.

    Missing files return an empty list so the MCP server can start cleanly.
    """
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except json.JSONDecodeError as exc:
        raise DataFileError(f"Invalid JSON in file: {path}") from exc
    except OSError as exc:
        raise DataFileError(f"Could not read file: {path}") from exc

    if not isinstance(payload, list):
        raise DataFileError(f"Expected a JSON array in file: {path}")

    return payload


def write_json_file(path: Path, payload: list[dict[str, Any]]) -> None:
    """Write a list of dictionaries to a JSON file."""
    ensure_data_dir()

    if not isinstance(payload, list):
        raise DataFileError("Payload must be a list of dictionaries.")

    try:
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)
    except OSError as exc:
        raise DataFileError(f"Could not write file: {path}") from exc


def get_next_id(rows: list[dict[str, Any]], id_field: str = "id") -> int:
    """Return the next numeric identifier for the given collection."""
    if not rows:
        return 1
    return max(int(row[id_field]) for row in rows) + 1


def load_products() -> list[dict[str, Any]]:
    return read_json_file(PRODUCTS_FILE)


def save_products(products: list[dict[str, Any]]) -> None:
    write_json_file(PRODUCTS_FILE, products)


def load_stores() -> list[dict[str, Any]]:
    return read_json_file(STORES_FILE)


def save_stores(stores: list[dict[str, Any]]) -> None:
    write_json_file(STORES_FILE, stores)


def load_inventory() -> list[dict[str, Any]]:
    return read_json_file(INVENTORY_FILE)


def save_inventory(inventory: list[dict[str, Any]]) -> None:
    write_json_file(INVENTORY_FILE, inventory)


def find_store_by_id(store_id: int) -> dict[str, Any] | None:
    return next((store for store in load_stores() if int(store.get("id", 0)) == int(store_id)), None)


def find_product_by_sku(sku: str) -> dict[str, Any] | None:
    normalized_sku = sku.strip().lower()
    return next(
        (
            product
            for product in load_products()
            if str(product.get("sku", "")).strip().lower() == normalized_sku
        ),
        None,
    )
