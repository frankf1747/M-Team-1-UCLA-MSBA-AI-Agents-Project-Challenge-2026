"""Generate a realistic 48h planning-window shipment feed for what-if simulation.

The provided workshop file (Incoming_shipments_14d_multi_corridor.csv) has only a
handful of planning-window rows, so a +20% demand spike never stresses the truck
fleet. The PDF explicitly invites teams to "simulate realistic values" and add
augmented CSVs. This feed is sized so that BASELINE is feasible (penalty 0) while
each of the three required disruptions clearly moves KPIs.

Run: python data-augmented/make_scenario_dataset.py
Output: data-augmented/incoming_shipments_scenario.csv (deterministic)
"""
import csv
import os

COLD = [
    (10021, "Remdesivir 100mg", "RMD"),
    (10022, "Insulin Lispro", "INS"),
    (10035, "Pembrolizumab", "PBR"),
]
WARM = [
    (10040, "Epinephrine Auto-Injector", "EPI"),
    (10050, "Heparin Sodium", "HEP"),
    (10070, "Albuterol Inhaler", "ALB"),
]
CORRIDORS = {
    "C1_I95_NJ_BOS": ["Boston-MGH", "Boston-BWH", "Boston-DanaFarber"],
    "C2_NJ_PHL": ["Philadelphia-UPenn", "Philadelphia-CHOP", "Philadelphia-Jefferson"],
}
DAYS = [("2026-03-02", "Day0"), ("2026-03-03", "Day1")]
COLD_PER_CELL = 9   # ceil(9*1.1/10)=1 reefer/corridor -> 2/day == 2 available
WARM_PER_CELL = 9   # ceil(9*1.1/10)=1 std/corridor    -> 2/day  <= 4 available


def build_rows():
    rows = []
    for date, day in DAYS:
        for corridor, hospitals in CORRIDORS.items():
            seq = 1
            for pool, n in ((COLD, COLD_PER_CELL), (WARM, WARM_PER_CELL)):
                for i in range(n):
                    iid, name, pref = pool[i % len(pool)]
                    # corridor digit + day digit so Day0/Day1 IDs never collide
                    cdig = "0" if corridor.startswith("C1") else "1"
                    ddig = "0" if day == "Day0" else "1"
                    suffix = f"{cdig}{ddig}"
                    rows.append({
                        "shipment_date": date,
                        "planning_day": day,
                        "is_planning_window": 1,
                        "corridor_id": corridor,
                        "item_id": iid,
                        "item_name": name,
                        "unique_item_id": f"{pref}-2026-{suffix}{seq:03d}",
                        "dispatch_location": hospitals[i % len(hospitals)],
                    })
                    seq += 1
    return rows


def main():
    out = os.path.join(os.path.dirname(__file__), "incoming_shipments_scenario.csv")
    rows = build_rows()
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
