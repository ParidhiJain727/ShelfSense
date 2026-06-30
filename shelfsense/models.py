"""
shelfsense/models.py
Pydantic v2 schemas for all Gemini structured outputs.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional


class IntentResult(BaseModel):
    """Output schema for the orchestrator's intent classification call."""
    intent: Literal["stock_check", "sales_log", "alert_watch", "reorder", "unknown"]
    product_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    timeframe_days: Optional[int] = None   # for queries like "last week's sales"
    confidence: float = 1.0


class StockCheckResult(BaseModel):
    """Structured view of a single inventory item."""
    sku: str
    name: str
    qty: float
    unit: str
    status: Literal["in_stock", "low_stock", "out_of_stock"]
    min_qty: float


class SalesLogResult(BaseModel):
    """Confirmation record after a sale is logged."""
    sku: str
    name: str
    qty_sold: float
    new_stock_level: float
    message: str


class AlertResult(BaseModel):
    """Summary of current open alerts."""
    alerts: list[dict]   # list of alert dicts from DB
    summary: str


class ReorderItem(BaseModel):
    """A single line item in a reorder plan."""
    sku: str
    name: str
    current_qty: float
    suggested_order_qty: float
    supplier_name: Optional[str] = None
    estimated_cost: Optional[float] = None
    reason: str


class ReorderPlan(BaseModel):
    """Complete reorder plan returned by the reorder agent."""
    items: list[ReorderItem]
    total_estimated_cost: Optional[float] = None
    purchase_order_text: str   # plain-text PO ready to send via WhatsApp
