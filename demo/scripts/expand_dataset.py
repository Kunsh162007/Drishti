"""
expand_dataset.py — Grow DRISHTI's flat demo tables to a larger, still-realistic
dataset so the app can be shown working at scale (~25k FIRs by default).

Method (no fabrication of new *kinds* of facts): every synthetic FIR inherits a
real FIR as a template (its district, police_station, crime_type, crime_category,
severity band, coordinate cluster, modus-operandi / description text, weapon), then
perturbs only the location (small jitter, staying in-district) and the timeline
(a fresh occurred/reported datetime). H3 indices are recomputed from the jittered
point. Parties (complainant / victim / accused / witness) are generated per FIR by
recombining the existing name pool, with a small fraction of accused sharing a
true_identity_id so the entity-resolution / network views stay interesting.

All generated rows use collision-proof IDs (GEN- / GP / GV / GMP prefixes), so the
original 8,034-FIR corpus is left byte-for-byte intact and re-running is additive.
After this, re-run build_ksp_schema.py to re-ETL into the normalized KSP tables.

Usage:  python demo/scripts/expand_dataset.py [--target 25000] [path/to.db]
"""
from __future__ import annotations
import argparse, random, sqlite3, datetime as dt
from pathlib import Path

import h3

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "drishti_demo.db"

random.seed(20260701)  # reproducible

DATE_MIN = dt.datetime(2023, 1, 1)
DATE_MAX = dt.datetime(2026, 6, 30)
_SPAN = int((DATE_MAX - DATE_MIN).total_seconds())

STATUS_WEIGHTS = [  # mirrors the observed live distribution
    ("Closed", 39), ("ChargeSheeted", 24), ("UnderInvestigation", 23), ("Open", 14),
]
GENDERS = ["Male", "Female", "Male", "Female", "Trans"]  # ~ realistic skew, incl. rare Trans


def rand_dt():
    return DATE_MIN + dt.timedelta(seconds=random.randint(0, _SPAN))


def phone():
    return str(random.randint(6, 9)) + "".join(str(random.randint(0, 9)) for _ in range(9))


def address(district):
    return (f"{random.randint(1, 220)}/{random.randint(1, 90)}, "
            f"{random.choice(['MG Road','Station Rd','Gandhi Nagar','Market Rd','Lake View','Nehru St'])}, "
            f"{district} {random.randint(560001, 591346)}")


def main(db_path: Path, target: int):
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = OFF")
    cur = con.cursor()

    cur_total = cur.execute("SELECT COUNT(*) FROM crimes").fetchone()[0]
    to_add = max(0, target - cur_total)
    print(f"DB: {db_path}\nexisting FIRs: {cur_total:,}  target: {target:,}  to add: {to_add:,}")
    if to_add == 0:
        print("Already at/above target — nothing to do.")
        return

    # --- template pool + name pool from real data ---
    templates = cur.execute(
        "SELECT district, police_station, crime_type, crime_category, severity, latitude, longitude, "
        "modus_operandi, description, status, victim_count, accused_count, property_value_inr, weapon_used "
        "FROM crimes WHERE latitude IS NOT NULL AND longitude IS NOT NULL").fetchall()
    names = [r[0] for r in cur.execute(
        "SELECT DISTINCT full_name FROM persons WHERE full_name IS NOT NULL")]
    firsts = sorted({n.split()[0] for n in names if n.split()})
    lasts = sorted({n.split()[-1] for n in names if len(n.split()) > 1})

    def rand_name():
        return f"{random.choice(firsts)} {random.choice(lasts)}"

    # unique-ID starting points
    p_start = 1
    v_start = 1
    mp_start = 1

    crime_rows, person_rows, vehicle_rows, mp_rows = [], [], [], []
    serial_by_year: dict[int, int] = {}
    shared_tids: list[str] = []   # pool of reusable identities for cross-FIR linkage

    for i in range(to_add):
        t = random.choice(templates)
        (district, ps, ctype, cat, sev, lat, lng, mo, desc, _st, vc, ac, pval, weapon) = t

        # jitter location (~<=1.5km) but keep the real district/station
        nlat = round((lat or 12.97) + random.gauss(0, 0.012), 6)
        nlng = round((lng or 77.59) + random.gauss(0, 0.012), 6)
        try:
            r7 = h3.latlng_to_cell(nlat, nlng, 7)
            r8 = h3.latlng_to_cell(nlat, nlng, 8)
            r9 = h3.latlng_to_cell(nlat, nlng, 9)
        except Exception:
            r7 = r8 = r9 = None

        occ = rand_dt()
        rep = occ + dt.timedelta(days=random.randint(0, 10), hours=random.randint(0, 23))
        if rep > DATE_MAX:
            rep = DATE_MAX
        yr = occ.year
        serial_by_year[yr] = serial_by_year.get(yr, 0) + 1
        fir = f"GEN-{yr}-{serial_by_year[yr]:06d}"

        status = random.choices([s for s, _ in STATUS_WEIGHTS],
                                weights=[w for _, w in STATUS_WEIGHTS])[0]
        vc = vc if (vc is not None) else random.randint(0, 2)
        ac = ac if (ac is not None) else random.randint(0, 3)
        vc, ac = min(vc, 3), min(ac, 5)

        crime_rows.append((
            fir, district, ps, ctype, cat, sev, nlat, nlng, r7, r8, r9,
            occ.strftime("%Y-%m-%dT%H:%M:%S"), rep.strftime("%Y-%m-%dT%H:%M:%S"),
            occ.hour, occ.weekday(), mo, desc, status, vc, ac, pval, weapon, "demo-synthetic-scale"))

        # --- parties for this FIR ---
        # 1 complainant
        person_rows.append((f"GP{p_start:07d}", fir, rand_name(), None, "Complainant",
                            random.choice(GENDERS), random.randint(21, 70), phone(),
                            address(district), district, f"TID-GEN-{p_start}"))
        p_start += 1
        for _ in range(max(vc, 1) if ctype != "Missing Person" else 1):
            person_rows.append((f"GP{p_start:07d}", fir, rand_name(), None, "Victim",
                                random.choice(GENDERS), random.randint(5, 80), phone(),
                                address(district), district, f"TID-GEN-{p_start}"))
            p_start += 1
        for _ in range(ac):
            # 8% of accused reuse an existing identity -> cross-FIR link for ER/network views
            if shared_tids and random.random() < 0.08:
                tid = random.choice(shared_tids)
            else:
                tid = f"TID-GEN-{p_start}"
                if random.random() < 0.10:
                    shared_tids.append(tid)
            person_rows.append((f"GP{p_start:07d}", fir, rand_name(), None, "Accused",
                                random.choice(GENDERS), random.randint(18, 65), phone(),
                                address(district), district, tid))
            p_start += 1
        if random.random() < 0.25:  # occasional witness
            person_rows.append((f"GP{p_start:07d}", fir, rand_name(), None, "Witness",
                                random.choice(GENDERS), random.randint(18, 75), phone(),
                                address(district), district, f"TID-GEN-{p_start}"))
            p_start += 1

        # vehicle for theft/robbery/dacoity types
        if any(k in (ctype or "") for k in ("Theft", "Robbery", "Dacoity", "Snatching")) and random.random() < 0.4:
            reg = f"KA{random.randint(1,70):02d}{random.choice('ABCDEFGHJKLMNPQR')}{random.choice('ABCDEFGHJKLMNPQR')}{random.randint(1000,9999)}"
            vehicle_rows.append((f"GV{v_start:07d}", fir, reg,
                                 random.choice(["Motorcycle","Car","Scooter","Auto","Mini Truck","SUV"]),
                                 f"{random.choice(['Black','White','Silver','Red','Blue','Grey'])} "
                                 f"{random.choice(['Honda','Bajaj','Maruti','Hyundai','TVS','Hero'])}"))
            v_start += 1

        # missing-person record for the Missing type
        if ctype == "Missing Person":
            mp_rows.append((f"GMP{mp_start:06d}", fir, rand_name(), random.randint(4, 80),
                            random.choice(GENDERS), occ.strftime("%Y-%m-%d"),
                            "last seen near " + random.choice(["bus stand","market","school","railway station"]),
                            district, random.choice(["Low","Medium","High"]),
                            random.choice(["Open","Traced","Closed"]), random.randint(0, 2)))
            mp_start += 1

    # --- bulk insert ---
    cur.executemany(
        "INSERT INTO crimes (fir_number,district,police_station,crime_type,crime_category,severity,"
        "latitude,longitude,h3_r7,h3_r8,h3_r9,occurred_at,reported_at,hour,day_of_week,modus_operandi,"
        "description,status,victim_count,accused_count,property_value_inr,weapon_used,source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", crime_rows)
    cur.executemany(
        "INSERT INTO persons (person_id,fir_number,full_name,normalized_name,role,gender,age,phone,"
        "address,district,true_identity_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(pid, fir, nm, (nm or "").lower(), role, g, age, ph, addr, dist, tid)
         for (pid, fir, nm, _, role, g, age, ph, addr, dist, tid) in person_rows])
    if vehicle_rows:
        cur.executemany("INSERT INTO vehicles (vehicle_id,fir_number,reg_number,vehicle_type,make_color) "
                        "VALUES (?,?,?,?,?)", vehicle_rows)
    if mp_rows:
        cur.executemany("INSERT INTO missing_persons (mp_id,fir_number,name,age,gender,last_seen_date,"
                        "last_seen_location,district,risk_tier,status,repeat_count) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)", mp_rows)
    con.commit()

    print(f"\nadded: {len(crime_rows):,} crimes | {len(person_rows):,} persons | "
          f"{len(vehicle_rows):,} vehicles | {len(mp_rows):,} missing-persons")
    for tbl in ("crimes", "persons", "vehicles", "missing_persons"):
        n = cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:<16} now {n:>8,}")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("db", nargs="?", default=str(DEFAULT_DB))
    ap.add_argument("--target", type=int, default=25000)
    a = ap.parse_args()
    main(Path(a.db), a.target)
