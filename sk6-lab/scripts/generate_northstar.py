"""Generate the NorthStar Retail source data for SK-06 (Power BI).

Writes 11 CSV files into the folder given by --out (default: data).
Only the Python standard library is used. The random seed is fixed, so
every trainee gets exactly the same rows and the same lab numbers.
"""
import argparse
import bisect
import csv
import datetime as dt
import random
from pathlib import Path

SEED = 20260701
FIRST_DAY = dt.date(2023, 7, 1)   # start of FY2024
LAST_DAY = dt.date(2026, 6, 30)   # end of FY2026

REGIONS = ["Northeast", "Southeast", "Midwest", "West"]
# region -> list of (district, [(city, state, lat, lon), ...])
GEO = {
    "Northeast": [
        ("New England", [("Boston", "MA", 42.36, -71.06), ("Hartford", "CT", 41.77, -72.67), ("Providence", "RI", 41.82, -71.41)]),
        ("New York Metro", [("New York", "NY", 40.71, -74.01), ("Newark", "NJ", 40.74, -74.17), ("Albany", "NY", 42.65, -73.76)]),
        ("Pennsylvania", [("Philadelphia", "PA", 39.95, -75.17), ("Pittsburgh", "PA", 40.44, -79.99)]),
    ],
    "Southeast": [
        ("Georgia", [("Atlanta", "GA", 33.75, -84.39), ("Savannah", "GA", 32.08, -81.09)]),
        ("Florida", [("Miami", "FL", 25.76, -80.19), ("Orlando", "FL", 28.54, -81.38), ("Tampa", "FL", 27.95, -82.46)]),
        ("Carolinas & Tennessee", [("Charlotte", "NC", 35.23, -80.84), ("Raleigh", "NC", 35.78, -78.64), ("Nashville", "TN", 36.16, -86.78)]),
    ],
    "Midwest": [
        ("Great Lakes", [("Chicago", "IL", 41.88, -87.63), ("Milwaukee", "WI", 43.04, -87.91), ("Detroit", "MI", 42.33, -83.05)]),
        ("Ohio Valley", [("Columbus", "OH", 39.96, -83.00), ("Indianapolis", "IN", 39.77, -86.16)]),
        ("Plains", [("Minneapolis", "MN", 44.98, -93.27), ("St. Louis", "MO", 38.63, -90.20), ("Kansas City", "MO", 39.10, -94.58)]),
    ],
    "West": [
        ("Pacific Northwest", [("Seattle", "WA", 47.61, -122.33), ("Portland", "OR", 45.52, -122.68)]),
        ("California", [("Los Angeles", "CA", 34.05, -118.24), ("San Diego", "CA", 32.72, -117.16), ("San Jose", "CA", 37.34, -121.89)]),
        ("Mountain", [("Denver", "CO", 39.74, -104.99), ("Phoenix", "AZ", 33.45, -112.07), ("Salt Lake City", "UT", 40.76, -111.89)]),
    ],
}
STORES_PER_REGION = {"Northeast": 24, "Southeast": 22, "Midwest": 21, "West": 18}  # 85 stores

CATALOG = {  # category -> [(subcategory, min_price, max_price)]
    "Apparel": [("Tops", 12, 60), ("Bottoms", 20, 90), ("Outerwear", 45, 250), ("Footwear", 30, 180)],
    "Electronics": [("Audio", 20, 400), ("Computing", 80, 1200), ("Mobile Accessories", 8, 80), ("Smart Home", 25, 300)],
    "Home & Garden": [("Kitchen", 10, 200), ("Furniture", 60, 900), ("Decor", 8, 120), ("Garden", 10, 250)],
    "Grocery": [("Snacks", 2, 12), ("Beverages", 2, 25), ("Pantry", 3, 30), ("Household", 3, 40)],
    "Sports & Outdoors": [("Fitness", 10, 400), ("Camping", 15, 350), ("Cycling", 20, 900), ("Team Sports", 8, 150)],
}
CATEGORY_WEIGHT = {"Apparel": 1.2, "Electronics": 0.7, "Home & Garden": 0.9, "Grocery": 2.0, "Sports & Outdoors": 0.8}
BRANDS = ["Northwind", "Apex", "Lumen", "Harbor", "Summit", "Vista", "Crescent", "Evergreen"]
PRODUCTS_PER_SUBCATEGORY = 600  # 5 x 4 x 600 = 12,000 SKUs

FIRST_NAMES = ["Ama", "Kwame", "Efua", "Kofi", "Sarah", "James", "Linda", "David", "Grace", "Michael",
               "Akosua", "Yaw", "Esi", "Daniel", "Rita", "Paul", "Naomi", "Victor", "Abena", "Samuel"]
LAST_NAMES = ["Mensah", "Owusu", "Johnson", "Smith", "Boateng", "Brown", "Asante", "Williams", "Osei", "Davis",
              "Appiah", "Miller", "Addo", "Wilson", "Agyeman", "Taylor", "Ansah", "Clark", "Frimpong", "Lewis"]
SEGMENTS = (["Value", "Regular", "Premium"], [50, 35, 15])

MONTH_FACTOR = {1: 0.85, 2: 0.85, 3: 0.95, 4: 0.95, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.05, 9: 0.95, 10: 1.0, 11: 1.25, 12: 1.45}
WEEKDAY_FACTOR = {0: 0.92, 1: 0.92, 2: 0.92, 3: 0.95, 4: 1.05, 5: 1.30, 6: 1.15}  # Mon..Sun
FY_GROWTH = {2024: 1.00, 2025: 1.07, 2026: 1.15}
BASE_ORDERS_PER_DAY = 140


def fiscal_year(d):
    return d.year + 1 if d.month >= 7 else d.year


def write_csv(folder, name, header, rows):
    path = folder / name
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {name:<22} {len(rows):>8,} rows")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data")
    out = Path(parser.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    print(f"Generating NorthStar Retail data (seed {SEED}) into {out.resolve()}")

    # ---- geography: regions, districts, stores --------------------------
    regions = [(i + 1, r) for i, r in enumerate(REGIONS)]
    districts, stores = [], []
    store_weight = []
    district_id = 0
    store_id = 100
    for region_id, region in regions:
        geo = GEO[region]
        region_districts = []
        for district_name, cities in geo:
            district_id += 1
            districts.append((district_id, district_name, region_id))
            region_districts.append((district_id, cities))
        for n in range(STORES_PER_REGION[region]):
            d_id, cities = region_districts[n % len(region_districts)]
            city, state, lat, lon = cities[(n // len(region_districts)) % len(cities)]
            store_id += 1
            open_date = dt.date(2008, 1, 1) + dt.timedelta(days=rng.randint(0, 5000))
            stores.append((store_id, f"NorthStar {city} #{store_id}", d_id, city, state,
                           round(lat + rng.uniform(-0.15, 0.15), 6), round(lon + rng.uniform(-0.15, 0.15), 6),
                           open_date.isoformat()))
            store_weight.append(rng.uniform(0.6, 1.6))
    store_ids = [s[0] for s in stores]
    store_cum = list(_cumulative(store_weight))

    # ---- products ----------------------------------------------------------
    categories, subcategories, products = [], [], []
    product_weight = []
    product_price, product_cost = {}, {}
    sub_id = 0
    product_id = 10000
    for cat_id, (cat, subs) in enumerate(CATALOG.items(), start=1):
        categories.append((cat_id, cat))
        for sub, lo, hi in subs:
            sub_id += 1
            subcategories.append((sub_id, sub, cat_id))
            for _ in range(PRODUCTS_PER_SUBCATEGORY):
                product_id += 1
                brand = rng.choice(BRANDS)
                price = round(rng.uniform(lo, hi), 2)
                cost = round(price * rng.uniform(0.55, 0.72), 2)
                products.append((product_id, f"{brand} {sub} {product_id}", sub_id, brand,
                                 f"{cost:.2f}", f"{price:.2f}"))
                product_price[product_id] = price
                product_cost[product_id] = cost
                # long-tail popularity: a few products sell a lot (Pareto)
                popularity = 1.0 / (rng.randint(1, PRODUCTS_PER_SUBCATEGORY) ** 0.9)
                product_weight.append(popularity * CATEGORY_WEIGHT[cat] / (price ** 0.35))
    product_ids = [p[0] for p in products]
    product_cum = list(_cumulative(product_weight))

    # ---- customers ---------------------------------------------------------
    customers = []
    n_customers = 30000
    span_before = (FIRST_DAY - dt.date(2019, 1, 1)).days
    span_during = (LAST_DAY - FIRST_DAY).days
    reg_dates = []
    for _ in range(n_customers):
        if rng.random() < 0.40:
            reg = dt.date(2019, 1, 1) + dt.timedelta(days=rng.randint(0, span_before - 1))
        else:
            reg = FIRST_DAY + dt.timedelta(days=rng.randint(0, span_during))
        reg_dates.append(reg)
    reg_dates.sort()
    for i, reg in enumerate(reg_dates, start=1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        city, state = rng.choice([(c[0], c[1]) for g in GEO.values() for _, cs in g for c in cs])
        segment = rng.choices(*SEGMENTS)[0]
        customers.append((i, first, last, f"customer{i}@example.com", segment, reg.isoformat(), city, state))
    customer_by_reg_day = {}
    for c in customers:
        customer_by_reg_day.setdefault(c[5], []).append(c[0])

    # ---- promotions ----------------------------------------------------------
    promotions = [(0, "No Promotion", "None", "0.00", FIRST_DAY.isoformat(), LAST_DAY.isoformat())]
    promo_templates = [("Back to School", "Seasonal", 8, 10), ("Black Friday", "Holiday", 11, 24),
                       ("Holiday Gift Event", "Holiday", 12, 10), ("New Year Clearance", "Clearance", 1, 3),
                       ("Spring Refresh", "Seasonal", 3, 15), ("Summer Loyalty Days", "Loyalty", 6, 5)]
    promo_days = {}
    pid = 0
    for fy in (2024, 2025, 2026):
        for name, ptype, month, day in promo_templates:
            pid += 1
            year = fy - 1 if month >= 7 else fy
            start = dt.date(year, month, day)
            end = start + dt.timedelta(days=rng.randint(6, 16))
            pct = rng.choice([0.10, 0.15, 0.20, 0.25])
            promotions.append((pid, f"{name} {year}", ptype, f"{pct:.2f}", start.isoformat(), end.isoformat()))
            d = start
            while d <= end:
                promo_days[d] = (pid, pct)
                d += dt.timedelta(days=1)

    # ---- orders and order lines ------------------------------------------------
    orders, lines = [], []
    order_id = 1000000
    line_id = 0
    store_month_revenue = {}
    day = FIRST_DAY
    total_days = (LAST_DAY - FIRST_DAY).days
    while day <= LAST_DAY:
        fy = fiscal_year(day)
        trend = 1 + 0.03 * ((day - FIRST_DAY).days / total_days)
        expected = BASE_ORDERS_PER_DAY * MONTH_FACTOR[day.month] * WEEKDAY_FACTOR[day.weekday()] * FY_GROWTH[fy] * trend
        n_orders = max(1, int(round(rng.gauss(expected, expected ** 0.5))))
        bound = bisect.bisect_right(reg_dates, day)  # customers registered on/before this day
        new_today = customer_by_reg_day.get(day.isoformat(), [])
        promo = promo_days.get(day)
        for k in range(n_orders):
            order_id += 1
            # every customer who registers today places their first order today
            customer_id = new_today[k] if k < len(new_today) else rng.randint(1, bound)
            r = rng.random()
            ship_date = "" if r < 0.01 else (day + dt.timedelta(days=rng.choices([1, 2, 3, 4, 5, 6, 7], [10, 25, 25, 15, 10, 8, 7])[0])).isoformat()
            is_returned = 1 if rng.random() < 0.04 else 0
            orders.append((order_id, day.isoformat(), ship_date, customer_id, is_returned, "pos_loader", "POS"))
            store = store_ids[bisect.bisect_left(store_cum, rng.random() * store_cum[-1])]
            n_lines = rng.choices([1, 2, 3, 4], [50, 30, 15, 5])[0]
            for line_number in range(1, n_lines + 1):
                line_id += 1
                prod = product_ids[bisect.bisect_left(product_cum, rng.random() * product_cum[-1])]
                qty = rng.choices([1, 2, 3, 4], [60, 25, 10, 5])[0]
                price = product_price[prod]
                promo_id, discount = 0, 0.0
                if promo and rng.random() < 0.35:
                    promo_id = promo[0]
                    discount = round(qty * price * promo[1], 2)
                lines.append((line_id, order_id, line_number, prod, store, promo_id, qty, f"{price:.2f}", f"{discount:.2f}"))
                key = (store, day.replace(day=1))
                store_month_revenue[key] = store_month_revenue.get(key, 0.0) + qty * price - discount
        day += dt.timedelta(days=1)

    # ---- monthly revenue targets per store ---------------------------------------
    # targets were set ambitiously for some regions, so the RAG status varies
    region_of_store = {s[0]: REGIONS[districts[s[2] - 1][2] - 1] for s in stores}
    ambition = {"Northeast": 0.97, "Southeast": 1.03, "Midwest": 1.07, "West": 1.14}
    targets = []
    for (store, month), revenue in sorted(store_month_revenue.items()):
        factor = ambition[region_of_store[store]] * rng.uniform(0.95, 1.05)
        target = round(revenue * factor, -2)
        targets.append((store, month.isoformat(), f"{target:.2f}"))

    # ---- write files ---------------------------------------------------------------
    write_csv(out, "regions.csv", ["region_id", "region_name"], regions)
    write_csv(out, "districts.csv", ["district_id", "district_name", "region_id"], districts)
    write_csv(out, "stores.csv", ["store_id", "store_name", "district_id", "city", "state", "latitude", "longitude", "open_date"], stores)
    write_csv(out, "categories.csv", ["category_id", "category_name"], categories)
    write_csv(out, "subcategories.csv", ["subcategory_id", "subcategory_name", "category_id"], subcategories)
    write_csv(out, "products.csv", ["product_id", "product_name", "subcategory_id", "brand", "unit_cost", "list_price"], products)
    write_csv(out, "customers.csv", ["customer_id", "first_name", "last_name", "email", "customer_segment", "registration_date", "city", "state"], customers)
    write_csv(out, "promotions.csv", ["promotion_id", "promotion_name", "promotion_type", "discount_pct", "start_date", "end_date"], promotions)
    write_csv(out, "orders.csv", ["order_id", "order_date", "ship_date", "customer_id", "is_returned", "created_by", "source_system"], orders)
    write_csv(out, "order_lines.csv", ["order_line_id", "order_id", "line_number", "product_id", "store_id", "promotion_id", "quantity", "unit_price", "discount_amount"], lines)
    write_csv(out, "revenue_targets.csv", ["store_id", "target_month", "revenue_target"], targets)
    print("Done.")


def _cumulative(weights):
    total = 0.0
    for w in weights:
        total += w
        yield total


if __name__ == "__main__":
    main()