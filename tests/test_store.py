from __future__ import annotations

import os
import unittest
from datetime import timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from bson.decimal128 import Decimal128

from retail_agent.agent import RetailAgent
from retail_agent.mongo_store import _date_string, _decimal, _mongo_date
from retail_agent.store import RetailStore, StoreError
from retail_agent.store_factory import create_store
from scripts.import_csv_to_mongodb import COLLECTIONS, parse_csv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CsvStoreRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = RetailStore(PROJECT_ROOT / "data")

    def test_seed_counts_and_revenue(self) -> None:
        self.assertEqual(len(self.store.products_by_sku), 13)
        self.assertEqual(len(self.store.orders_by_id), 15)
        self.assertEqual(
            self.store.revenue_report(),
            {
                "start_date": "2026-05-01",
                "end_date": "2026-05-31",
                "gross_revenue": "1786.20",
                "refunds_issued": "54.00",
                "net_revenue": "1732.20",
                "order_count": 15,
                "units_sold": 80,
            },
        )

    def test_sale_mutates_inventory_and_creates_order(self) -> None:
        before = self.store.inventory_by_sku["TOTE"].on_hand_qty
        result = self.store.ring_up_sale(
            [{"product_name": "Canvas Tote", "quantity": 1}]
        )
        self.assertEqual(result["order_id"], "O-1016")
        self.assertEqual(result["total"], "18.00")
        self.assertEqual(self.store.inventory_by_sku["TOTE"].on_hand_qty, before - 1)

    def test_empty_sale_is_rejected_before_persistence(self) -> None:
        with self.assertRaisesRegex(StoreError, "At least one sale item"):
            self.store.ring_up_sale([])

    def test_rule_parser_accepts_an_exact_sku(self) -> None:
        agent = RetailAgent(self.store, provider="rules")
        response = agent._rule_sale("ring up 5 TEE-BLU-M for a walk in")
        self.assertEqual(response["lines"][0]["sku"], "TEE-BLU-M")
        self.assertEqual(response["lines"][0]["quantity"], 5)


class MongoMappingTests(unittest.TestCase):
    def test_decimal128_round_trip(self) -> None:
        self.assertEqual(_decimal(Decimal128("18.00")), Decimal("18.00"))

    def test_date_round_trip(self) -> None:
        value = _mongo_date("2026-05-31")
        self.assertEqual(value.tzinfo, timezone.utc)
        self.assertEqual(_date_string(value), "2026-05-31")

    def test_importer_applies_bson_types(self) -> None:
        products = next(spec for spec in COLLECTIONS if spec.collection == "products")
        document = parse_csv(products)[0]
        self.assertIsInstance(document["retail_price"], Decimal128)

        inventory = next(spec for spec in COLLECTIONS if spec.collection == "inventory")
        document = parse_csv(inventory)[0]
        self.assertIsInstance(document["on_hand_qty"], int)

    @patch("retail_agent.store_factory.load_dotenv")
    def test_factory_rejects_partial_mongodb_configuration(self, _: object) -> None:
        with patch.dict(
            os.environ,
            {"MONGODB_URI": "mongodb://example"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "must either both be set"):
                create_store(PROJECT_ROOT / "data")


if __name__ == "__main__":
    unittest.main()
