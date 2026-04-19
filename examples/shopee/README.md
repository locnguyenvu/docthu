# Examples

## shopee/

Shopee order delivery notification emails — a real-world extraction scenario.

### Files

| File | Description |
|---|---|
| `template.html` | Annotated template with `{{ variable }}` placeholders |
| `test1.html` | Single order, two items, no coupon |
| `test2.html` | Single order, one item, Shopee + Shop coupons applied |
| `test3.html` | Single order, one item, Shopee coupon applied |

The test files are sanitised copies of real Shopee delivery emails. They represent three common checkout scenarios and can be used to verify that the template correctly extracts all fields across varying order structures.

### Variables extracted

| Variable | Type | Description |
|---|---|---|
| `order_id` | str | Order code (e.g. `#2401ABCD123456`) |
| `order_date` | datetime | Date and time the order was placed |
| `seller` | str | Shop name |
| `item.number` | str | Line item index |
| `item.name` | str | Product name |
| `item.variant` | str | Selected variant |
| `item.quantity` | int | Quantity ordered |
| `item.price` | float | Unit price (VND) |
| `total` | float | Final amount paid (VND) |

### Running the extraction

```python
from pathlib import Path
from docthu import Template

template_str = Path("shopee/template.html").read_text()
tpl = Template(template_str)

for test_file in ["shopee/test1.html", "shopee/test2.html", "shopee/test3.html"]:
    message = Path(test_file).read_text()
    result = tpl.match(message)
    print(f"--- {test_file} ---")
    print(result)
```

Run from the `examples/` directory:

```bash
cd examples
python run.py
```

Or inline from the project root:

```bash
cd docthu
python - << 'EOF'
from pathlib import Path
from docthu import Template

tpl = Template(Path("examples/shopee/template.html").read_text())

for name in ["test1", "test2", "test3"]:
    msg = Path(f"examples/shopee/{name}.html").read_text()
    print(f"\n--- {name} ---")
    import json
    print(json.dumps(tpl.match(msg), indent=2, ensure_ascii=False, default=str))
EOF
```

### Early exit (fast path)

If you only need the order ID and total, use `stop_on_filled` to skip parsing the rest of the document:

```python
result = tpl.match(message, stop_on_filled=["order_id", "total"])
```

### Expected output

**test1.html** — 2 items, no coupon

```json
{
  "order_id": "2401ABCD123456",
  "order_date": "2024-01-01 00:00:00",
  "seller": "9m.2m",
  "item": [
    {
      "number": "1",
      "name": "Cà Phê Arabica Sơn La Natural | Cà phê rang xay nguyên chất phù hợp pha pour over V60 trái cây",
      "variant": "250gr - Rang Light,Nguyên hạt",
      "quantity": 1,
      "price": 120000.0
    },
    {
      "number": "2",
      "name": "Cà Phê Arabica Sơn La | Cà phê rang xay nguyên chất phù hợp pha pour over V60 trái cây",
      "variant": "250gr - Light Roast,Nguyên hạt",
      "quantity": 1,
      "price": 80000.0
    }
  ],
  "total": 200000.0
}
```

**test2.html** — 1 item, Shopee + Shop coupons applied

```json
{
  "order_id": "2401EFGH789012",
  "order_date": "2024-01-01 00:00:00",
  "seller": "vbinhshop",
  "item": [
    {
      "number": "1",
      "name": "Máy xay cafe cầm tay cối xay cafe mini Chất Lượng cối xay cà phê Cao CNC 6 trục",
      "variant": "VBZ18-MàuBạc",
      "quantity": 1,
      "price": 800000.0
    }
  ],
  "total": 670000.0
}
```

**test3.html** — 1 item, Shopee coupon applied

```json
{
  "order_id": "2401IJKL345678",
  "order_date": "2024-01-01 00:00:00",
  "seller": "mujivn.official",
  "item": [
    {
      "number": "1",
      "name": "Áo Khoác Hoodie Nam Khóa Kéo Gấp Gọn Chống Tia Uv Nhanh Khô MUJI",
      "variant": "Xám nhạt,M",
      "quantity": 1,
      "price": 500000.0
    }
  ],
  "total": 450000.0
}
```
