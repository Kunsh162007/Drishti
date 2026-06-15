#!/usr/bin/env python3
"""
generate_extended_data.py — DRISHTI demo EXTENDED datasets.

Reads the EXISTING seed (crimes.csv, persons.csv) and produces NEW linked
datasets for extended features, WITHOUT touching the existing seed files:

  seed/cdr.csv                 (20,000 rows — fast-seeding subset)
  seed/accounts.csv            (~6,000 financial accounts)
  seed/transactions.csv        (~60,000 transactions, fraud chains embedded)
  seed/missing_persons.csv     (one row per existing Missing Person FIR)

  samples/cdr_large.csv        (full 120,000 CDR)
  samples/transactions.csv     (copy of the 60k transactions)

Everything is DETERMINISTIC (fixed seeds). Run:

  python scripts/generate_extended_data.py

Design goals (so analytics "light up"):
  * Many CDR msisdns are REAL phone numbers from persons.csv (person<->CDR link).
  * 6-8 "suspect rings": small groups that call each other & co-locate at towers.
  * ~40 fraud money-flow chains tagged is_flagged + linked to REAL Cybercrime FIRs.
  * missing_persons rows reuse REAL Missing Person FIRs; ~10% missing fields (never faked).
"""

import csv
import os
import random
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np

# --------------------------------------------------------------------------- #
# Paths & determinism
# --------------------------------------------------------------------------- #
HERE = os.path.dirname(os.path.abspath(__file__))
DEMO_DIR = os.path.dirname(HERE)
SEED_DIR = os.path.join(DEMO_DIR, "data", "seed")
SAMPLES_DIR = os.path.join(DEMO_DIR, "data", "samples")

CRIMES_CSV = os.path.join(SEED_DIR, "crimes.csv")
PERSONS_CSV = os.path.join(SEED_DIR, "persons.csv")

GLOBAL_SEED = 20260614
random.seed(GLOBAL_SEED)
np.random.seed(GLOBAL_SEED)
RNG = random.Random(GLOBAL_SEED)

NOW = datetime(2026, 6, 10, 0, 0, 0)          # upper bound for timestamps
TWELVE_MONTHS_AGO = NOW - timedelta(days=365)

# Target sizes
N_CDR_FULL = 120_000
N_CDR_SEED = 20_000
N_TOWERS = 400
N_ACCOUNTS = 6_000
MULE_FRACTION = 0.08
N_TXN = 60_000
N_FRAUD_CHAINS = 40
N_SUSPECT_RINGS = 7

BANKS = ["SBI", "Canara Bank", "HDFC Bank", "ICICI Bank", "Axis Bank",
         "Kotak Mahindra", "Karnataka Bank", "Union Bank", "Bank of Baroda",
         "PNB", "IDBI Bank", "Yes Bank"]
TXN_CHANNELS = ["UPI", "IMPS", "NEFT", "Card"]
CALL_TYPES = ["voice", "sms", "data"]


# --------------------------------------------------------------------------- #
# Load existing seed
# --------------------------------------------------------------------------- #
def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


print("Reading existing seed ...")
crimes = load_csv(CRIMES_CSV)
persons = load_csv(PERSONS_CSV)
print(f"  crimes:  {len(crimes):,}")
print(f"  persons: {len(persons):,}")


# District centroids computed from the REAL crime coordinates (robust + accurate)
_lat = defaultdict(list)
_lng = defaultdict(list)
for c in crimes:
    d = c["district"]
    try:
        _lat[d].append(float(c["latitude"]))
        _lng[d].append(float(c["longitude"]))
    except (TypeError, ValueError):
        continue

DISTRICT_CENTROIDS = {
    d: (float(np.mean(_lat[d])), float(np.mean(_lng[d])))
    for d in _lat if _lat[d]
}
DISTRICTS = sorted(DISTRICT_CENTROIDS.keys())

# Short district codes for tower ids
def district_code(d):
    if d.startswith("Bengaluru City"):
        return "BLR"
    if d.startswith("Bengaluru Rural"):
        return "BLRR"
    letters = "".join(ch for ch in d.upper() if ch.isalpha())
    return letters[:3]

# Persons that have a usable phone number
def valid_phone(p):
    ph = (p.get("phone") or "").strip()
    return ph if (len(ph) == 10 and ph[0] in "6789" and ph.isdigit()) else None

persons_with_phone = [p for p in persons if valid_phone(p)]
print(f"  persons with usable phone: {len(persons_with_phone):,}")

# Map fir_number -> district for quick lookup
fir_district = {c["fir_number"]: c["district"] for c in crimes}

# Group persons by true_identity gang (TID#### only — these are real linked gangs)
gang_members = defaultdict(list)
for p in persons_with_phone:
    tid = (p.get("true_identity_id") or "").strip()
    if tid.startswith("TID") and tid[3:].isdigit():
        gang_members[tid].append(p)
# Gangs with at least 4 phone-bearing members make good suspect rings
ring_candidate_gangs = sorted(
    [tid for tid, m in gang_members.items() if len(m) >= 4],
    key=lambda t: -len(gang_members[t]),
)
print(f"  gangs (>=4 phoned members) available for rings: {len(ring_candidate_gangs)}")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def rand_msisdn():
    """Random 10-digit Indian-style mobile number (prefix 6-9)."""
    return str(RNG.choice([6, 7, 8, 9])) + "".join(
        str(RNG.randint(0, 9)) for _ in range(9)
    )


def jitter(center, spread):
    lat, lng = center
    return (round(lat + RNG.gauss(0, spread), 6),
            round(lng + RNG.gauss(0, spread), 6))


def rand_time(start=TWELVE_MONTHS_AGO, end=NOW):
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=RNG.randint(0, span))


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


# --------------------------------------------------------------------------- #
# 1) Cell towers — ~400 across district centroids
# --------------------------------------------------------------------------- #
print("\nBuilding cell towers ...")
towers = []                      # list of dicts: id, lat, lng, district
towers_by_district = defaultdict(list)

# Distribute towers proportional to crime volume (more towers in busy districts),
# but guarantee at least 2 per district.
district_weight = {d: max(2, len(_lat[d])) for d in DISTRICTS}
total_w = sum(district_weight.values())
tower_seq = 0
for d in DISTRICTS:
    n = max(2, round(N_TOWERS * district_weight[d] / total_w))
    code = district_code(d)
    for _ in range(n):
        lat, lng = jitter(DISTRICT_CENTROIDS[d], 0.045)
        tid = f"TWR-{code}-{tower_seq:03d}"
        rec = {"cell_tower_id": tid, "tower_lat": lat,
               "tower_lng": lng, "district": d}
        towers.append(rec)
        towers_by_district[d].append(rec)
        tower_seq += 1
print(f"  towers: {len(towers)} across {len(towers_by_district)} districts")


def pick_tower(district):
    pool = towers_by_district.get(district) or towers
    return RNG.choice(pool)


# --------------------------------------------------------------------------- #
# 2) Suspect rings — build BEFORE generating CDR so we can inject their calls
# --------------------------------------------------------------------------- #
print("\nDefining suspect rings ...")
rings = []                       # each: {ring_id, district, members[], home_towers[]}
used_gangs = set()
ring_descriptions = []

for i in range(N_SUSPECT_RINGS):
    # Prefer a real gang; fall back to persons sharing a FIR.
    members = None
    src = None
    for tid in ring_candidate_gangs:
        if tid in used_gangs:
            continue
        used_gangs.add(tid)
        pool = gang_members[tid]
        size = min(len(pool), RNG.randint(4, 7))
        members = RNG.sample(pool, size)
        src = f"gang {tid}"
        break
    if members is None:
        # fallback: pick a FIR with >=4 phoned persons
        fir_groups = defaultdict(list)
        for p in persons_with_phone:
            fir_groups[p["fir_number"]].append(p)
        big = [f for f, m in fir_groups.items() if len(m) >= 4]
        f = RNG.choice(big)
        pool = fir_groups[f]
        members = RNG.sample(pool, min(len(pool), RNG.randint(4, 7)))
        src = f"FIR {f}"

    # Ring "home" district = modal district of its members
    dist_counts = defaultdict(int)
    for m in members:
        dist_counts[m["district"]] += 1
    home_district = max(dist_counts, key=dist_counts.get)
    if home_district not in towers_by_district:
        home_district = RNG.choice(DISTRICTS)
    # 2-3 shared towers the ring co-locates at
    home_towers = RNG.sample(
        towers_by_district[home_district],
        min(3, len(towers_by_district[home_district])),
    )
    member_msisdns = [valid_phone(m) for m in members]
    rings.append({
        "ring_id": f"RING-{i+1:02d}",
        "district": home_district,
        "members": members,
        "msisdns": member_msisdns,
        "home_towers": home_towers,
        "src": src,
    })
    ring_descriptions.append(
        f"RING-{i+1:02d}: {len(members)} numbers from {src}, "
        f"home={home_district}, co-locate towers="
        f"{[t['cell_tower_id'] for t in home_towers]}"
    )
    print(f"  {ring_descriptions[-1]}")


# --------------------------------------------------------------------------- #
# 3) Call Detail Records
# --------------------------------------------------------------------------- #
print("\nGenerating CDR ...")

# Build a pool of "real" msisdns + their home district (for tower locality)
real_numbers = []                 # (msisdn, district)
seen_numbers = set()
for p in persons_with_phone:
    ph = valid_phone(p)
    if ph and ph not in seen_numbers:
        seen_numbers.add(ph)
        real_numbers.append((ph, p["district"]))

# A background population of random numbers (so not every number is "real")
random_numbers = []
for _ in range(8000):
    n = rand_msisdn()
    random_numbers.append((n, RNG.choice(DISTRICTS)))

all_numbers = real_numbers + random_numbers     # caller pool
number_district = {n: d for n, d in all_numbers}

cdr_rows = []
cdr_seq = 0


def add_cdr(caller, callee, start_time, tower, call_type=None, dur=None):
    global cdr_seq
    if call_type is None:
        call_type = RNG.choices(CALL_TYPES, weights=[0.6, 0.3, 0.1])[0]
    if dur is None:
        if call_type == "voice":
            dur = max(5, int(RNG.expovariate(1 / 180)))
        elif call_type == "data":
            dur = RNG.randint(10, 3600)
        else:  # sms
            dur = 0
    cdr_rows.append({
        "cdr_id": f"CDR-{cdr_seq:07d}",
        "caller_msisdn": caller,
        "callee_msisdn": callee,
        "start_time": iso(start_time),
        "duration_sec": dur,
        "cell_tower_id": tower["cell_tower_id"],
        "tower_lat": tower["tower_lat"],
        "tower_lng": tower["tower_lng"],
        "call_type": call_type,
    })
    cdr_seq += 1


# --- 3a) Suspect-ring traffic: dense intra-ring calls + tower co-location ---
ring_cdr_count = 0
for ring in rings:
    msisdns = [m for m in ring["msisdns"] if m]
    if len(msisdns) < 2:
        continue
    # Each ring: many calls among members over several "meeting" bursts.
    n_calls = RNG.randint(180, 320)
    for _ in range(n_calls):
        a, b = RNG.sample(msisdns, 2)
        # Co-location: both endpoints logged at one of the ring's home towers
        tower = RNG.choice(ring["home_towers"])
        # Bursty windows: pick a base day, calls clustered within minutes
        base = rand_time()
        t = base + timedelta(minutes=RNG.randint(0, 90))
        add_cdr(a, b, t, tower,
                call_type=RNG.choices(["voice", "sms"], weights=[0.7, 0.3])[0])
        ring_cdr_count += 1
print(f"  ring CDR records: {ring_cdr_count:,}")


# --- 3b) Background CDR up to the full target -------------------------------
print("  generating background CDR (this is the bulk) ...")
target_remaining = N_CDR_FULL - len(cdr_rows)
real_set = set(n for n, _ in real_numbers)

for _ in range(target_remaining):
    caller, cdist = RNG.choice(all_numbers)
    # 35% of calls go to another REAL number (boost person<->person linkage),
    # else to anyone in the pool.
    if RNG.random() < 0.35 and real_numbers:
        callee = RNG.choice(real_numbers)[0]
    else:
        callee = RNG.choice(all_numbers)[0]
    if callee == caller:
        callee = rand_msisdn()
    # Tower near the caller's home district most of the time
    if RNG.random() < 0.85:
        tower = pick_tower(cdist)
    else:
        tower = RNG.choice(towers)
    add_cdr(caller, callee, rand_time(), tower)

print(f"  total CDR: {len(cdr_rows):,}")


# --------------------------------------------------------------------------- #
# 4) Financial accounts
# --------------------------------------------------------------------------- #
print("\nGenerating accounts ...")
person_names = [p["full_name"].strip() for p in persons if p.get("full_name", "").strip()]
# Concentrate accounts (and later fraud) in Bengaluru
def weighted_district():
    if RNG.random() < 0.45:
        return "Bengaluru City"
    return RNG.choice(DISTRICTS)

accounts = []
account_index = {}              # account_id -> dict
n_mules_target = int(N_ACCOUNTS * MULE_FRACTION)
for i in range(N_ACCOUNTS):
    acc_id = f"ACC{i:06d}"
    # ~55% of holders reuse a real person name
    if RNG.random() < 0.55 and person_names:
        holder = RNG.choice(person_names)
    else:
        holder = RNG.choice(person_names) if person_names else f"Holder {i}"
    rec = {
        "account_id": acc_id,
        "holder_name": holder,
        "bank": RNG.choice(BANKS),
        "district": weighted_district(),
        "is_mule": False,
    }
    accounts.append(rec)
    account_index[acc_id] = rec

# Mark a baseline set of mules (random), concentrated in Bengaluru.
mule_pool = sorted(accounts,
                   key=lambda a: (a["district"] != "Bengaluru City", RNG.random()))
for a in mule_pool[:n_mules_target]:
    a["is_mule"] = True
print(f"  accounts: {len(accounts):,}  (mules so far: {sum(a['is_mule'] for a in accounts)})")


# --------------------------------------------------------------------------- #
# 5) Transactions — normal traffic + fraud money-flow chains
# --------------------------------------------------------------------------- #
print("\nGenerating transactions ...")

# Real Cybercrime FIRs to attach to fraud chains (Online Financial Fraud / Phishing)
cyber_firs = [
    c["fir_number"] for c in crimes
    if c["crime_category"] == "Cybercrime"
    and c["crime_type"] in ("Online Financial Fraud", "Phishing / OTP Fraud")
]
RNG.shuffle(cyber_firs)
print(f"  Cybercrime FIRs available for fraud linkage: {len(cyber_firs)}")

txn_rows = []
txn_seq = 0


def add_txn(frm, to, amount, ts, channel=None, fir="", flagged=False):
    global txn_seq
    if channel is None:
        channel = RNG.choices(TXN_CHANNELS, weights=[0.5, 0.2, 0.15, 0.15])[0]
    txn_rows.append({
        "txn_id": f"TXN{txn_seq:07d}",
        "from_account": frm,
        "to_account": to,
        "amount_inr": round(amount, 2),
        "timestamp": iso(ts),
        "channel": channel,
        "fir_number": fir,
        "is_flagged": str(flagged).lower(),
    })
    txn_seq += 1


# --- 5a) Fraud money-flow chains -------------------------------------------
# victim -> mule1 -> {mule2, mule3} -> cash-out, rapid pass-through + layering.
bengaluru_accounts = [a for a in accounts if a["district"] == "Bengaluru City"]
flagged_fir_links = 0
chain_descriptions = []

for ci in range(N_FRAUD_CHAINS):
    fir = cyber_firs[ci % len(cyber_firs)] if cyber_firs else ""
    if fir:
        flagged_fir_links += 1
    # Victim account (normal, not a mule)
    victim = RNG.choice([a for a in bengaluru_accounts if not a["is_mule"]]
                        or bengaluru_accounts)
    # Choose/assign mules (force is_mule=True for chain mules)
    def grab_mule():
        cand = RNG.choice(bengaluru_accounts)
        cand["is_mule"] = True
        return cand

    mule1 = grab_mule()
    layer2 = [grab_mule() for _ in range(RNG.randint(2, 3))]   # fan-out
    cashouts = [grab_mule() for _ in range(RNG.randint(1, 2))]

    # Big inflow to mule1 within a tight window
    t0 = rand_time(NOW - timedelta(days=300), NOW - timedelta(days=2))
    principal = round(RNG.uniform(150_000, 1_800_000), 2)
    add_txn(victim["account_id"], mule1["account_id"], principal, t0,
            channel=RNG.choice(["IMPS", "UPI", "NEFT"]), fir=fir, flagged=True)

    # Rapid split-out (layering) from mule1 to layer2 within minutes/hours
    remaining = principal
    t = t0
    for m in layer2:
        t = t + timedelta(minutes=RNG.randint(2, 240))
        share = round(remaining * RNG.uniform(0.25, 0.5), 2)
        remaining -= share
        add_txn(mule1["account_id"], m["account_id"], share, t,
                channel=RNG.choice(["IMPS", "UPI"]), fir=fir, flagged=True)
        # Fan-in / cash-out: each layer2 forwards to a cash-out account
        for co in cashouts:
            t2 = t + timedelta(minutes=RNG.randint(1, 180))
            add_txn(m["account_id"], co["account_id"],
                    round(share * RNG.uniform(0.3, 0.6), 2), t2,
                    channel=RNG.choice(["UPI", "Card", "IMPS"]),
                    fir=fir, flagged=True)
    chain_descriptions.append(
        f"chain {ci+1}: {victim['account_id']} -> {mule1['account_id']} -> "
        f"{len(layer2)} mules -> {len(cashouts)} cash-out  (FIR {fir or 'n/a'}, "
        f"principal Rs {principal:,.0f})"
    )

print(f"  fraud-chain flagged txns: {len(txn_rows):,} "
      f"(chains={N_FRAUD_CHAINS}, linked to real FIRs={flagged_fir_links})")


# --- 5b) Normal peer transactions to fill to target -------------------------
acc_ids = [a["account_id"] for a in accounts]
target_remaining = N_TXN - len(txn_rows)
for _ in range(target_remaining):
    frm, to = RNG.sample(acc_ids, 2)
    amount = round(RNG.choice([
        RNG.uniform(50, 2_000),       # small everyday
        RNG.uniform(2_000, 25_000),   # medium
        RNG.uniform(25_000, 120_000), # larger
    ]), 2)
    add_txn(frm, to, amount, rand_time(NOW - timedelta(days=365), NOW))

RNG.shuffle(txn_rows)
# Re-id after shuffle so txn_ids stay ordered/clean
for i, r in enumerate(txn_rows):
    r["txn_id"] = f"TXN{i:07d}"
print(f"  total transactions: {len(txn_rows):,}  "
      f"(flagged: {sum(1 for r in txn_rows if r['is_flagged']=='true')})")


# --------------------------------------------------------------------------- #
# 6) Missing persons — one row per existing 'Missing Person' FIR
# --------------------------------------------------------------------------- #
print("\nGenerating missing_persons ...")
missing_firs = [c for c in crimes if c["crime_type"] == "Missing Person"]
# Index persons by FIR to reuse a real victim name where available
persons_by_fir = defaultdict(list)
for p in persons:
    persons_by_fir[p["fir_number"]].append(p)

RISK_TIERS = ["High", "Medium", "Low"]
STATUSES = ["Open", "Traced", "Closed"]

mp_rows = []
for i, c in enumerate(missing_firs):
    fir = c["fir_number"]
    district = c["district"]
    # Choose a person on this FIR (prefer Victim/Complainant subject)
    cand = persons_by_fir.get(fir, [])
    subject = None
    for role in ("Victim", "Missing", "Complainant"):
        match = [p for p in cand if p.get("role") == role]
        if match:
            subject = match[0]
            break
    if subject is None and cand:
        subject = cand[0]

    name = subject["full_name"].strip() if subject else f"Unknown {i}"
    gender = (subject.get("gender") or "").strip() if subject else ""
    if gender not in ("Male", "Female"):
        gender = RNG.choice(["Male", "Female"])

    # Age: reuse real age if present, else sometimes leave missing
    age = ""
    if subject and (subject.get("age") or "").strip():
        try:
            age = str(int(float(subject["age"])))
        except ValueError:
            age = ""
    elif RNG.random() < 0.6:
        age = str(RNG.choice(
            list(range(5, 17)) + list(range(17, 70)) + list(range(70, 86))
        ))

    # Risk tier skews High for minors/elderly
    age_num = int(age) if age.isdigit() else None
    if age_num is not None and (age_num < 16 or age_num >= 65):
        risk = RNG.choices(RISK_TIERS, weights=[0.7, 0.25, 0.05])[0]
    else:
        risk = RNG.choices(RISK_TIERS, weights=[0.3, 0.4, 0.3])[0]

    status = RNG.choices(STATUSES, weights=[0.45, 0.35, 0.20])[0]
    repeat_count = RNG.choices([0, 1, 2, 3, 4],
                               weights=[0.55, 0.22, 0.13, 0.07, 0.03])[0]

    # last_seen_date: a bit before reported_at
    try:
        rep = datetime.fromisoformat(c["reported_at"])
        last_seen = rep - timedelta(days=RNG.randint(0, 7),
                                    hours=RNG.randint(0, 23))
        last_seen_date = last_seen.strftime("%Y-%m-%d")
    except (ValueError, KeyError):
        last_seen_date = ""

    # last_seen_location from MO snippet; ~10% left blank (never fabricated)
    if RNG.random() < 0.10:
        last_seen_location = ""
    else:
        mo = (c.get("modus_operandi") or "").split(",")[0].strip()
        last_seen_location = mo if mo else ""

    # ~10% missing age explicitly (override) — never fabricate
    if RNG.random() < 0.10:
        age = ""

    mp_rows.append({
        "mp_id": f"MP{i:05d}",
        "fir_number": fir,
        "name": name,
        "age": age,
        "gender": gender,
        "last_seen_date": last_seen_date,
        "last_seen_location": last_seen_location,
        "district": district,
        "risk_tier": risk,
        "status": status,
        "repeat_count": repeat_count,
    })
print(f"  missing_persons rows: {len(mp_rows):,}")


# --------------------------------------------------------------------------- #
# 7) Write files
# --------------------------------------------------------------------------- #
def write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


print("\nWriting files ...")

CDR_FIELDS = ["cdr_id", "caller_msisdn", "callee_msisdn", "start_time",
              "duration_sec", "cell_tower_id", "tower_lat", "tower_lng",
              "call_type"]
ACC_FIELDS = ["account_id", "holder_name", "bank", "district", "is_mule"]
TXN_FIELDS = ["txn_id", "from_account", "to_account", "amount_inr",
              "timestamp", "channel", "fir_number", "is_flagged"]
MP_FIELDS = ["mp_id", "fir_number", "name", "age", "gender", "last_seen_date",
             "last_seen_location", "district", "risk_tier", "status",
             "repeat_count"]

# Full CDR -> samples; a 20k subset (KEEP all ring rows so analytics work) -> seed
ring_cdr = cdr_rows[:ring_cdr_count]
bg_cdr = cdr_rows[ring_cdr_count:]
RNG.shuffle(bg_cdr)
seed_cdr = ring_cdr + bg_cdr[: max(0, N_CDR_SEED - len(ring_cdr))]
RNG.shuffle(seed_cdr)
# Re-id seed subset cleanly
for i, r in enumerate(seed_cdr):
    r = dict(r)  # not strictly needed; ids are independent across files
# (ids already unique; leave as-is)

write_csv(os.path.join(SAMPLES_DIR, "cdr_large.csv"), cdr_rows, CDR_FIELDS)
write_csv(os.path.join(SEED_DIR, "cdr.csv"), seed_cdr, CDR_FIELDS)

# Account is_mule as lowercase bool
for a in accounts:
    a["is_mule"] = str(bool(a["is_mule"])).lower()
write_csv(os.path.join(SEED_DIR, "accounts.csv"), accounts, ACC_FIELDS)

write_csv(os.path.join(SEED_DIR, "transactions.csv"), txn_rows, TXN_FIELDS)
write_csv(os.path.join(SAMPLES_DIR, "transactions.csv"), txn_rows, TXN_FIELDS)

write_csv(os.path.join(SEED_DIR, "missing_persons.csv"), mp_rows, MP_FIELDS)


# --------------------------------------------------------------------------- #
# 8) Linkage stats + verification
# --------------------------------------------------------------------------- #
print("\nComputing linkage stats ...")

real_phone_set = set(valid_phone(p) for p in persons_with_phone)
real_phone_set.discard(None)

cdr_numbers = set()
for r in cdr_rows:
    cdr_numbers.add(r["caller_msisdn"])
    cdr_numbers.add(r["callee_msisdn"])
cdr_matching_persons = len(cdr_numbers & real_phone_set)

flagged_txns = [r for r in txn_rows if r["is_flagged"] == "true"]
flagged_with_fir = [r for r in flagged_txns if r["fir_number"]]
distinct_fraud_firs = set(r["fir_number"] for r in flagged_with_fir)
real_fir_set = set(c["fir_number"] for c in crimes)
flagged_fir_real = set(r["fir_number"] for r in flagged_with_fir) & real_fir_set

n_mules_final = sum(1 for a in accounts if a["is_mule"] == "true")

# Verify every file parses
print("\nVerifying files parse ...")
verify = {
    "seed/cdr.csv": os.path.join(SEED_DIR, "cdr.csv"),
    "samples/cdr_large.csv": os.path.join(SAMPLES_DIR, "cdr_large.csv"),
    "seed/accounts.csv": os.path.join(SEED_DIR, "accounts.csv"),
    "seed/transactions.csv": os.path.join(SEED_DIR, "transactions.csv"),
    "samples/transactions.csv": os.path.join(SAMPLES_DIR, "transactions.csv"),
    "seed/missing_persons.csv": os.path.join(SEED_DIR, "missing_persons.csv"),
}
for label, path in verify.items():
    rows = load_csv(path)
    print(f"  OK  {label:<28} rows={len(rows):,}")


# --------------------------------------------------------------------------- #
# 9) Summary
# --------------------------------------------------------------------------- #
print("\n" + "=" * 70)
print("EXTENDED DATA SUMMARY")
print("=" * 70)
print(f"CDR (full samples/cdr_large.csv): {len(cdr_rows):,}")
print(f"CDR (seed/cdr.csv subset):        {len(seed_cdr):,}")
print(f"  cell towers:                    {len(towers)}")
print(f"  distinct msisdns in CDR:        {len(cdr_numbers):,}")
print(f"  CDR numbers matching persons:   {cdr_matching_persons:,}")
print(f"Accounts:                         {len(accounts):,} "
      f"(mules={n_mules_final}, {100*n_mules_final/len(accounts):.1f}%)")
print(f"Transactions:                     {len(txn_rows):,} "
      f"(flagged={len(flagged_txns):,})")
print(f"  flagged txns linked to FIR:     {len(flagged_with_fir):,}")
print(f"  distinct REAL FIRs in fraud:    {len(flagged_fir_real)}")
print(f"Missing persons:                  {len(mp_rows):,} "
      f"(from {len(missing_firs)} Missing Person FIRs)")
mp_missing_age = sum(1 for r in mp_rows if not r["age"])
mp_missing_loc = sum(1 for r in mp_rows if not r["last_seen_location"])
print(f"  missing age (left blank):       {mp_missing_age} "
      f"({100*mp_missing_age/len(mp_rows):.0f}%)")
print(f"  missing last_seen_location:     {mp_missing_loc} "
      f"({100*mp_missing_loc/len(mp_rows):.0f}%)")

print("\nSuspect rings embedded in CDR:")
for d in ring_descriptions:
    print("  - " + d)

print(f"\nFraud money-flow chains embedded ({len(chain_descriptions)}):")
for d in chain_descriptions[:6]:
    print("  - " + d)
print(f"  ... and {max(0, len(chain_descriptions)-6)} more chains")
print("=" * 70)
print("DONE.")
