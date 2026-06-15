"""
generate_data.py — Synthetic Karnataka crime data generator for the DRISHTI demo.

Generates THREE linked tables (crimes, persons, vehicles) matching the canonical
schema in demo/SPEC.md + demo/backend/constants.py exactly, with realism deliberately
engineered so every analytics demo "lights up":

  * Bengaluru City hotspot (~30-40% of records) + tight spatiotemporal clusters
    (burglary spree, chain-snatching market cluster) for hotspot / near-repeat demos.
  * Realistic lat/lng from hard-coded district centroids + gaussian jitter; h3 r7/r8/r9.
  * Time patterns over ~3 years to 2026-06-10; property/violent skew night, cyber uniform;
    reported_at = occurred_at + realistic delay; hour/day_of_week derived consistently.
  * Cybercrime concentrated in Bengaluru (India's cyber-fraud hub).
  * Templated modus_operandi fragments so MO-similarity linkage finds real overlaps;
    several serial offenders reuse near-identical MO across FIRs/jurisdictions.
  * ~150 "true identities" recurring across FIRs under NAME VARIANTS (entity resolution),
    sometimes sharing phone numbers; normalized_name = lowercased, punct-stripped, sorted tokens.
  * Recurring persons + vehicles across FIRs (network / gang components).
  * Deliberate missing data (NULLs) in realistic fractions — never fabricated.

Outputs (created by running this file):
  demo/data/seed/    -> crimes.csv, persons.csv, vehicles.csv          (8,000-crime SEED set)
  demo/data/samples/ -> crimes_large.csv (50k), crimes.json, crimes.ndjson,
                        crimes.geojson, crimes.xlsx, new_incidents.csv (~600 June-2026),
                        connect_your_own_TEMPLATE.csv, MAPPING_EXAMPLE.json

Run from repo root:  python demo/scripts/generate_data.py
"""

from __future__ import annotations

import json
import random
import re
import string
import sys
from datetime import datetime, timedelta
from pathlib import Path

import h3
import numpy as np
import pandas as pd
from faker import Faker

# --- make backend constants importable (single source of truth) -----------------
ROOT = Path(__file__).resolve().parents[2]  # repo root
sys.path.insert(0, str(ROOT))
from demo.backend.constants import (  # noqa: E402
    CRIME_COLUMNS,
    CRIME_TYPES,
    KARNATAKA_DISTRICTS,
    PERSON_COLUMNS,
    STATUSES,
    VEHICLE_COLUMNS,
)

# --- determinism ----------------------------------------------------------------
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker("en_IN")
Faker.seed(SEED)

SEED_DIR = ROOT / "demo" / "data" / "seed"
SAMPLES_DIR = ROOT / "demo" / "data" / "samples"
SEED_DIR.mkdir(parents=True, exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

END_DATE = datetime(2026, 6, 10, 23, 59)
START_DATE = END_DATE - timedelta(days=3 * 365)  # ~3 years

# --- Karnataka district centroids (approx lat, lng) -----------------------------
# Used as cluster centres; small gaussian jitter (~±0.03 deg) added per incident.
DISTRICT_CENTROIDS = {
    "Bengaluru City": (12.9716, 77.5946),
    "Bengaluru Rural": (13.2257, 77.5750),
    "Mysuru": (12.2958, 76.6394),
    "Mangaluru": (12.9141, 74.8560),
    "Hubballi-Dharwad": (15.3647, 75.1240),
    "Belagavi": (15.8497, 74.4977),
    "Kalaburagi": (17.3297, 76.8343),
    "Ballari": (15.1394, 76.9214),
    "Vijayapura": (16.8302, 75.7100),
    "Davanagere": (14.4644, 75.9218),
    "Shivamogga": (13.9299, 75.5681),
    "Tumakuru": (13.3392, 77.1010),
    "Raichur": (16.2076, 77.3463),
    "Bidar": (17.9133, 77.5301),
    "Hassan": (13.0072, 76.1003),
    "Udupi": (13.3409, 74.7421),
    "Chitradurga": (14.2251, 76.3980),
    "Kolar": (13.1357, 78.1326),
    "Mandya": (12.5223, 76.8954),
    "Chikkamagaluru": (13.3161, 75.7720),
    "Koppal": (15.3500, 76.1547),
    "Bagalkote": (16.1691, 75.6615),
    "Haveri": (14.7935, 75.4045),
    "Gadag": (15.4315, 75.6355),
    "Chamarajanagar": (11.9261, 76.9404),
    "Yadgir": (16.7700, 77.1376),
    "Ramanagara": (12.7217, 77.2807),
    "Chikkaballapura": (13.4355, 77.7315),
    "Dakshina Kannada": (12.8703, 75.2479),
    "Uttara Kannada": (14.7937, 74.6869),
}

# District-weighting: Bengaluru City a clear hotspot (~33% before clusters push higher).
def _district_weights():
    w = {d: 1.0 for d in KARNATAKA_DISTRICTS}
    w["Bengaluru City"] = 12.5
    for d in ["Mysuru", "Mangaluru", "Hubballi-Dharwad", "Belagavi", "Bengaluru Rural"]:
        w[d] = 2.5
    arr = np.array([w[d] for d in KARNATAKA_DISTRICTS], dtype=float)
    return arr / arr.sum()


DISTRICT_PROBS = _district_weights()

# --- crime-type mix by category -------------------------------------------------
# Higher weight => more frequent. Cyber types boosted because they're common + we
# additionally pin most of them to Bengaluru (cyber-fraud hub) downstream.
CRIME_TYPE_WEIGHTS = {
    "Burglary": 9, "House Theft": 8, "Vehicle Theft": 11, "Chain Snatching": 6,
    "Robbery": 5, "Dacoity": 1.5,
    "Cheating / Fraud": 7,
    "Online Financial Fraud": 12, "Phishing / OTP Fraud": 9,
    "Assault": 8, "Murder": 2, "Attempt to Murder": 2.5, "Rioting": 2, "Kidnapping": 2,
    "Domestic Violence": 5, "Dowry Harassment": 3, "Molestation": 3,
    "POCSO": 1.5,
    "Missing Person": 3,
    "Drug Possession (NDPS)": 4, "Excise / Illicit Liquor": 3,
}
CRIME_TYPE_LIST = list(CRIME_TYPE_WEIGHTS.keys())
_ct_w = np.array([CRIME_TYPE_WEIGHTS[c] for c in CRIME_TYPE_LIST], dtype=float)
CRIME_TYPE_PROBS = _ct_w / _ct_w.sum()

CYBER_TYPES = {"Online Financial Fraud", "Phishing / OTP Fraud", "Cheating / Fraud"}
PROPERTY_NIGHT = {"Burglary", "House Theft", "Vehicle Theft", "Robbery", "Dacoity"}
VIOLENT_NIGHT = {"Assault", "Murder", "Attempt to Murder", "Rioting"}
WEAPON_TYPES = {"Robbery", "Dacoity", "Murder", "Attempt to Murder", "Assault", "Rioting", "Kidnapping"}
PROPERTY_VALUE_TYPES = {
    "Burglary", "House Theft", "Vehicle Theft", "Chain Snatching", "Robbery", "Dacoity",
    "Cheating / Fraud", "Online Financial Fraud", "Phishing / OTP Fraud",
}
VEHICLE_INVOLVED_TYPES = {
    "Vehicle Theft", "Robbery", "Dacoity", "Chain Snatching", "Kidnapping", "Murder",
}

# --- modus operandi fragment templates (per crime type) -------------------------
# Built from interchangeable fragments so MO-similarity finds genuine overlaps.
MO_FRAGMENTS = {
    "Burglary": {
        "entry": ["rear window broken", "grille cut open", "lock picked", "ventilator forced",
                  "duplicate key used", "back door pried open"],
        "loot": ["jewellery taken", "cash and gold stolen", "electronics removed", "almirah emptied"],
        "extra": ["night-time entry", "occupants away on travel", "CCTV wires cut", "guard dog poisoned"],
    },
    "House Theft": {
        "entry": ["door latch lifted", "unlocked door entered", "false ceiling crawled"],
        "loot": ["cash from drawer taken", "mobile phones lifted", "ornaments stolen"],
        "extra": ["daytime when house empty", "domestic help suspected", "no forced entry"],
    },
    "Vehicle Theft": {
        "entry": ["ignition hot-wired", "steering lock broken", "duplicate key used", "master key used"],
        "loot": ["two-wheeler driven away", "car taken from parking lot", "vehicle parts stripped"],
        "extra": ["from apartment basement", "outside shopping mall", "near railway station", "number plate swapped"],
    },
    "Chain Snatching": {
        "entry": ["two riders on motorcycle", "pillion rider snatched", "approached from behind"],
        "loot": ["gold chain snatched", "mangalsutra pulled", "necklace grabbed"],
        "extra": ["near market crowd", "victim walking alone", "fled towards main road", "morning walk hours"],
    },
    "Robbery": {
        "entry": ["knife brandished", "threatened with weapon", "gang surrounded victim"],
        "loot": ["cash and phone taken", "wallet snatched", "valuables looted"],
        "extra": ["on isolated stretch", "late night near ATM", "victim assaulted"],
    },
    "Dacoity": {
        "entry": ["armed gang of five", "house surrounded at night", "family held hostage"],
        "loot": ["locker looted", "gold and cash taken", "valuables carried in bags"],
        "extra": ["faces masked", "telephone lines cut", "fled in waiting vehicle"],
    },
    "Cheating / Fraud": {
        "entry": ["fake investment scheme", "posed as bank official", "forged documents used"],
        "loot": ["amount transferred to mule account", "deposits collected and absconded", "cheque dishonoured"],
        "extra": ["promised high returns", "multiple victims targeted", "shell company used"],
    },
    "Online Financial Fraud": {
        "entry": ["fake customer-care number", "phishing link sent", "remote-access app installed",
                  "UPI collect request", "fake KYC update message"],
        "loot": ["amount debited via UPI", "OTP shared by victim", "card details captured"],
        "extra": ["money routed through mule accounts", "victim contacted on WhatsApp",
                  "spoofed bank SMS", "withdrawn from distant ATM"],
    },
    "Phishing / OTP Fraud": {
        "entry": ["OTP obtained on pretext of reward", "SIM swap executed", "fake lottery message"],
        "loot": ["bank account drained", "wallet balance transferred", "card not present transaction"],
        "extra": ["caller spoofed bank IVR", "social engineering used", "multiple small debits"],
    },
    "Assault": {
        "entry": ["sudden quarrel escalated", "old enmity", "argument over money"],
        "loot": ["victim beaten with sticks", "stabbed during scuffle", "hit with blunt object"],
        "extra": ["near liquor shop", "group attack", "alcohol involved"],
    },
    "Murder": {
        "entry": ["premeditated attack", "ambushed victim", "lured to isolated spot"],
        "loot": ["stabbed multiple times", "strangled", "shot at close range", "head injuries inflicted"],
        "extra": ["body found in field", "previous enmity", "property dispute motive"],
    },
    "Attempt to Murder": {
        "entry": ["waylaid victim", "sudden assault", "ambush near residence"],
        "loot": ["stabbed and fled", "fired shot but missed", "attacked with machete"],
        "extra": ["victim survived with injuries", "gang rivalry", "land dispute"],
    },
    "Rioting": {
        "entry": ["mob gathered", "unlawful assembly", "two groups clashed"],
        "loot": ["stones pelted", "shops vandalised", "vehicles set ablaze"],
        "extra": ["communal tension", "after political rally", "curfew imposed"],
    },
    "Kidnapping": {
        "entry": ["abducted in vehicle", "lured with false promise", "forcibly taken"],
        "loot": ["ransom demanded", "held captive", "phone switched off"],
        "extra": ["known to family", "fled across district border", "minor victim"],
    },
    "Domestic Violence": {
        "entry": ["dispute with in-laws", "harassment by husband", "frequent quarrels"],
        "loot": ["physically assaulted", "subjected to cruelty", "thrown out of house"],
        "extra": ["dowry-related", "repeated incidents", "complaint to women's helpline"],
    },
    "Dowry Harassment": {
        "entry": ["demand for additional dowry", "pressure for cash and gold", "taunts by in-laws"],
        "loot": ["mental and physical harassment", "denied food", "confined to room"],
        "extra": ["marriage two years ago", "family approached police", "mediation failed"],
    },
    "Molestation": {
        "entry": ["accosted on road", "followed victim", "outraged modesty"],
        "loot": ["inappropriate touching", "verbal abuse", "blocked path"],
        "extra": ["near bus stop", "workplace incident", "repeat offender"],
    },
    "POCSO": {
        "entry": ["known person", "lured the minor", "inappropriate behaviour"],
        "loot": ["sexual assault on minor", "abuse reported by parents", "grooming alleged"],
        "extra": ["school vicinity", "neighbour accused", "counselling provided"],
    },
    "Missing Person": {
        "entry": ["left home without informing", "last seen near bus stand", "did not return from college"],
        "loot": ["whereabouts unknown", "phone unreachable", "no contact since"],
        "extra": ["possible elopement", "depression suspected", "search underway"],
    },
    "Drug Possession (NDPS)": {
        "entry": ["caught in raid", "intercepted at checkpost", "tip-off acted upon"],
        "loot": ["ganja seized", "MDMA pills recovered", "contraband in vehicle"],
        "extra": ["peddler network", "supplied near college", "weighing scale recovered"],
    },
    "Excise / Illicit Liquor": {
        "entry": ["raid on illegal unit", "vehicle intercepted", "tip-off received"],
        "loot": ["illicit liquor seized", "ID liquor cartons recovered", "distillation setup found"],
        "extra": ["sold without licence", "smuggled across border", "unit destroyed"],
    },
}

DESCRIPTION_PREFIX = [
    "Complainant reports that", "As per the FIR,", "Investigation reveals that",
    "On the date of incident,", "The victim states that",
]

# --- police-station naming ------------------------------------------------------
STATION_TYPES = ["Town", "Rural", "City", "Market", "Industrial Area", "East", "West",
                 "North", "South", "Cantonment", "Lake", "Nagar"]


def make_station(district: str, rng: random.Random) -> str:
    base = district.split()[0]
    return f"{base} {rng.choice(STATION_TYPES)} PS"


# --- name normalization ---------------------------------------------------------
def normalize_name(name: str) -> str:
    """lowercase, strip punctuation, sort tokens -> stable canonical form."""
    cleaned = re.sub(r"[^a-z\s]", " ", name.lower())
    tokens = sorted(t for t in cleaned.split() if t)
    return " ".join(tokens)


# --- name-variant generation for entity resolution ------------------------------
TRANSLIT_SWAPS = [
    ("sh", "s"), ("ee", "i"), ("oo", "u"), ("v", "w"), ("th", "t"),
    ("Mahesh", "Magesh"), ("Suresh", "Sooresh"), ("Reddy", "Reddi"),
    ("Kumar", "Kumaar"), ("Gowda", "Gowdru"), ("ph", "f"),
]


def name_variant(full_name: str, rng: random.Random) -> str:
    """Produce a plausible spelling/format variant of a name."""
    parts = full_name.split()
    style = rng.random()
    if len(parts) >= 2 and style < 0.25:
        # initial for surname:  "Mahesh Kumar" -> "Mahesh K."
        return f"{parts[0]} {parts[-1][0]}."
    if len(parts) >= 2 and style < 0.45:
        # initial for first name: "M. Kumar"
        return f"{parts[0][0]}. {' '.join(parts[1:])}"
    if style < 0.75:
        # transliteration / spelling drift
        out = full_name
        for a, b in rng.sample(TRANSLIT_SWAPS, k=rng.randint(1, 2)):
            if a in out:
                out = out.replace(a, b, 1)
                break
        else:
            out = out.replace(parts[-1], parts[-1] + ("a" if not parts[-1].endswith("a") else ""))
        return out
    # whitespace / casing noise
    return full_name.upper() if rng.random() < 0.5 else full_name.replace(" ", "  ")


# ================================================================================
# IDENTITY POOL — ~150 ground-truth identities for entity-resolution + network demos
# ================================================================================
N_IDENTITIES = 150


def build_identity_pool():
    pool = []
    for i in range(N_IDENTITIES):
        gender = random.choice(["Male", "Male", "Male", "Female"])  # crime skews male
        full_name = fake.name_male() if gender == "Male" else fake.name_female()
        # strip Faker honorifics for cleaner variants
        full_name = re.sub(r"^(Dr\.|Mr\.|Mrs\.|Ms\.|Miss|Smt\.|Shri)\s+", "", full_name).strip()
        pool.append({
            "true_identity_id": f"TID{i:04d}",
            "canonical_name": full_name,
            "gender": gender,
            "phone": f"9{random.randint(100000000, 999999999)}",
            "home_district": np.random.choice(KARNATAKA_DISTRICTS, p=DISTRICT_PROBS),
            "age": random.randint(19, 58),
        })
    return pool


IDENTITY_POOL = build_identity_pool()
# A subset are "serial offenders": they reuse near-identical MO across FIRs/districts.
SERIAL_OFFENDERS = IDENTITY_POOL[:18]
# A subset form gangs (share vehicles + co-occur in FIRs).
GANG_MEMBERS = IDENTITY_POOL[18:60]

# Pre-built signature MO per serial offender (reused with tiny noise across FIRs).
SERIAL_SIGNATURE = {}
for off in SERIAL_OFFENDERS:
    ct = random.choice(["Burglary", "Chain Snatching", "Online Financial Fraud",
                        "Vehicle Theft", "Robbery"])
    frg = MO_FRAGMENTS[ct]
    sig = f"{random.choice(frg['entry'])}, {random.choice(frg['loot'])}, {random.choice(frg['extra'])}"
    SERIAL_SIGNATURE[off["true_identity_id"]] = (ct, sig)

# Recurring vehicle pool (network demo) — some reg numbers recur across many FIRs.
def ka_reg(rng: random.Random) -> str:
    return (f"KA{rng.randint(1, 53):02d}"
            f"{rng.choice(string.ascii_uppercase)}{rng.choice(string.ascii_uppercase)}"
            f"{rng.randint(0, 9999):04d}")


RECURRING_VEHICLES = [ka_reg(random) for _ in range(60)]
VEHICLE_TYPES = ["Motorcycle", "Scooter", "Car", "Auto Rickshaw", "Mini Truck", "SUV", "Tempo"]
VEHICLE_COLORS = ["Black", "White", "Red", "Silver", "Blue", "Grey", "Maroon"]


# --- spatiotemporal clusters ----------------------------------------------------
# Each cluster: a tight area + short time window + a dominant crime type, so hotspot
# and near-repeat / emerging detection fire. Coordinates are near Bengaluru micro-areas.
CLUSTERS = [
    {  # burglary spree, 2-week window, one neighbourhood (near-repeat)
        "name": "Whitefield burglary spree", "crime_type": "Burglary",
        "district": "Bengaluru City", "center": (12.9698, 77.7499),
        "spread": 0.006, "start": datetime(2025, 11, 3), "days": 14, "n": 70,
        "offender": SERIAL_OFFENDERS[0]["true_identity_id"],
    },
    {  # chain-snatching cluster near a market
        "name": "KR Market chain-snatching", "crime_type": "Chain Snatching",
        "district": "Bengaluru City", "center": (12.9607, 77.5754),
        "spread": 0.004, "start": datetime(2026, 2, 10), "days": 21, "n": 55,
        "offender": SERIAL_OFFENDERS[1]["true_identity_id"],
    },
    {  # vehicle-theft cluster near tech park parking
        "name": "Electronic City vehicle thefts", "crime_type": "Vehicle Theft",
        "district": "Bengaluru City", "center": (12.8452, 77.6602),
        "spread": 0.007, "start": datetime(2025, 8, 1), "days": 28, "n": 60,
        "offender": SERIAL_OFFENDERS[2]["true_identity_id"],
    },
    {  # cyber-fraud burst (call-centre ring) — many FIRs same MO, short window
        "name": "OTP fraud ring burst", "crime_type": "Online Financial Fraud",
        "district": "Bengaluru City", "center": (12.9352, 77.6245),
        "spread": 0.02, "start": datetime(2026, 4, 5), "days": 18, "n": 65,
        "offender": SERIAL_OFFENDERS[3]["true_identity_id"],
    },
    {  # robbery cluster on an outer ring road stretch
        "name": "ORR night robberies", "crime_type": "Robbery",
        "district": "Bengaluru City", "center": (12.9100, 77.6800),
        "spread": 0.008, "start": datetime(2025, 12, 20), "days": 16, "n": 45,
        "offender": SERIAL_OFFENDERS[4]["true_identity_id"],
    },
]


# ================================================================================
# CORE GENERATION
# ================================================================================
def pick_hour(crime_type: str, rng: random.Random) -> int:
    """Property/violent skew to night; cyber roughly uniform (slight daytime lean)."""
    if crime_type in CYBER_TYPES:
        return rng.randint(0, 23)
    if crime_type in PROPERTY_NIGHT or crime_type in VIOLENT_NIGHT:
        # bimodal night: 20:00-03:00 mostly
        if rng.random() < 0.7:
            return rng.choice([20, 21, 22, 23, 0, 1, 2, 3])
        return rng.randint(4, 19)
    if crime_type in {"Chain Snatching", "Molestation"}:
        # morning-walk / commute hours
        return rng.choice([6, 7, 8, 9, 17, 18, 19, 20])
    return rng.randint(6, 22)


def reporting_delay(crime_type: str, rng: random.Random) -> timedelta:
    """Realistic gap between occurrence and FIR registration."""
    if crime_type in CYBER_TYPES:
        # victims notice later
        hrs = rng.choice([6, 12, 24, 48, 72, 120, 168])
    elif crime_type == "Missing Person":
        hrs = rng.choice([24, 48, 72])
    elif crime_type in {"Murder", "Robbery", "Dacoity"}:
        hrs = rng.choice([1, 2, 3, 6])
    else:
        hrs = rng.choice([1, 2, 4, 8, 12, 24, 48])
    return timedelta(hours=hrs, minutes=rng.randint(0, 59))


def build_mo(crime_type: str, identity_id: str | None, rng: random.Random) -> str:
    """Templated MO; serial offenders reuse their signature with tiny noise."""
    if identity_id in SERIAL_SIGNATURE and SERIAL_SIGNATURE[identity_id][0] == crime_type:
        sig = SERIAL_SIGNATURE[identity_id][1]
        if rng.random() < 0.4:  # occasional minor mutation
            frg = MO_FRAGMENTS[crime_type]
            sig = sig.rsplit(",", 1)[0] + ", " + rng.choice(frg["extra"])
        return sig
    frg = MO_FRAGMENTS[crime_type]
    return f"{rng.choice(frg['entry'])}, {rng.choice(frg['loot'])}, {rng.choice(frg['extra'])}"


def severity_for(crime_type: str, rng: random.Random) -> int:
    high = {"Murder": 5, "Dacoity": 5, "Attempt to Murder": 4, "POCSO": 5, "Kidnapping": 4,
            "Robbery": 4, "Rioting": 3}
    if crime_type in high:
        return high[crime_type]
    mid = {"Burglary", "House Theft", "Vehicle Theft", "Chain Snatching", "Assault",
           "Online Financial Fraud", "Phishing / OTP Fraud", "Cheating / Fraud",
           "Domestic Violence", "Dowry Harassment", "Drug Possession (NDPS)"}
    if crime_type in mid:
        return rng.choice([2, 3, 3, 4])
    return rng.choice([1, 2, 3])


def jitter_coords(center, spread, rng: random.Random):
    lat = center[0] + rng.gauss(0, spread)
    lng = center[1] + rng.gauss(0, spread)
    return round(lat, 6), round(lng, 6)


def status_for(occurred: datetime, rng: random.Random) -> str:
    """Older cases more likely resolved; recent ones more likely Open."""
    age_days = (END_DATE - occurred).days
    if age_days < 30:
        return np.random.choice(STATUSES, p=[0.55, 0.30, 0.10, 0.05])
    if age_days < 180:
        return np.random.choice(STATUSES, p=[0.25, 0.35, 0.20, 0.20])
    return np.random.choice(STATUSES, p=[0.10, 0.20, 0.25, 0.45])


def generate(n_crimes: int, fir_prefix: str = "FIR", start_idx: int = 0,
             use_clusters: bool = True, rng_seed: int = SEED):
    """Generate linked crimes/persons/vehicles. Returns three lists of dicts."""
    rng = random.Random(rng_seed)
    np_rng = np.random.RandomState(rng_seed)

    crimes, persons, vehicles = [], [], []
    person_counter = 0
    vehicle_counter = 0

    # --- pre-allocate clustered records (each is a fully specified incident) -----
    cluster_specs = []
    if use_clusters:
        for cl in CLUSTERS:
            for _ in range(cl["n"]):
                occ_day = cl["start"] + timedelta(days=rng.randint(0, cl["days"]))
                cluster_specs.append({
                    "district": cl["district"], "crime_type": cl["crime_type"],
                    "center": cl["center"], "spread": cl["spread"],
                    "date": occ_day, "offender": cl["offender"],
                })
    n_random = max(0, n_crimes - len(cluster_specs))

    def make_incident(idx, spec=None):
        nonlocal person_counter, vehicle_counter
        fir = f"{fir_prefix}-{2023 + (idx % 4)}-{start_idx + idx:06d}"

        if spec is not None:
            district = spec["district"]
            crime_type = spec["crime_type"]
            lat, lng = jitter_coords(spec["center"], spec["spread"], rng)
            occ_date = spec["date"]
            forced_offender = spec["offender"]
        else:
            district = np_rng.choice(KARNATAKA_DISTRICTS, p=DISTRICT_PROBS)
            crime_type = CRIME_TYPE_LIST[np_rng.choice(len(CRIME_TYPE_LIST), p=CRIME_TYPE_PROBS)]
            # Cybercrime concentrated in Bengaluru — relocate most cyber FIRs there.
            if crime_type in {"Online Financial Fraud", "Phishing / OTP Fraud"} and rng.random() < 0.7:
                district = "Bengaluru City"
            center = DISTRICT_CENTROIDS[district]
            lat, lng = jitter_coords(center, 0.03, rng)
            # random date across the 3-year window
            occ_date = START_DATE + timedelta(
                days=rng.randint(0, (END_DATE - START_DATE).days))
            forced_offender = None

        category = CRIME_TYPES[crime_type]
        hour = pick_hour(crime_type, rng)
        occurred = occ_date.replace(hour=hour, minute=rng.randint(0, 59),
                                    second=0, microsecond=0)
        if occurred > END_DATE:
            occurred = END_DATE - timedelta(hours=rng.randint(1, 72))
            hour = occurred.hour
        reported = occurred + reporting_delay(crime_type, rng)

        # h3 indices
        h7 = h3.latlng_to_cell(lat, lng, 7)
        h8 = h3.latlng_to_cell(lat, lng, 8)
        h9 = h3.latlng_to_cell(lat, lng, 9)

        # decide accused identity (serial offender / gang / one-off)
        if forced_offender is not None:
            accused_identity = next(o for o in IDENTITY_POOL
                                    if o["true_identity_id"] == forced_offender)
        elif rng.random() < 0.28:
            accused_identity = rng.choice(IDENTITY_POOL)  # recurring pool
        else:
            accused_identity = None  # fresh one-off person

        # MO + description
        mo = build_mo(crime_type,
                      accused_identity["true_identity_id"] if accused_identity else None, rng)
        desc = f"{rng.choice(DESCRIPTION_PREFIX)} {mo}. Reported at {district}."

        # property value (nullable; ~12% deliberately missing)
        prop_value = None
        if crime_type in PROPERTY_VALUE_TYPES and rng.random() > 0.12:
            base = {"Online Financial Fraud": (5_000, 800_000),
                    "Phishing / OTP Fraud": (2_000, 300_000),
                    "Cheating / Fraud": (20_000, 5_000_000),
                    "Dacoity": (100_000, 8_000_000),
                    "Robbery": (5_000, 500_000),
                    "Chain Snatching": (15_000, 200_000)}.get(crime_type, (3_000, 600_000))
            prop_value = float(round(rng.uniform(*base), -2))

        # weapon (nullable; ~8% missing among weapon-relevant types)
        weapon = None
        if crime_type in WEAPON_TYPES and rng.random() > 0.08:
            weapon = rng.choice(["Knife", "Machete", "Country-made pistol", "Wooden stick",
                                 "Iron rod", "Sickle", "Sharp-edged weapon", "Acid", "None"])
            if weapon == "None":
                weapon = None

        victim_count = 1 if rng.random() < 0.8 else rng.randint(2, 5)
        accused_count = (1 if rng.random() < 0.6 else rng.randint(2, 6))
        if crime_type in {"Dacoity", "Rioting"}:
            accused_count = rng.randint(3, 9)

        crimes.append({
            "fir_number": fir, "district": district, "police_station": make_station(district, rng),
            "crime_type": crime_type, "crime_category": category, "severity": severity_for(crime_type, rng),
            "latitude": lat, "longitude": lng, "h3_r7": h7, "h3_r8": h8, "h3_r9": h9,
            "occurred_at": occurred.isoformat(), "reported_at": reported.isoformat(),
            "hour": occurred.hour, "day_of_week": occurred.weekday(),
            "modus_operandi": mo, "description": desc, "status": status_for(occurred, rng),
            "victim_count": victim_count, "accused_count": accused_count,
            "property_value_inr": prop_value, "weapon_used": weapon, "source": "demo-synthetic",
        })

        # ---------- persons linked to this FIR ----------
        # accused/suspect
        n_accused_records = min(accused_count, rng.randint(1, 2))
        for k in range(n_accused_records):
            person_counter += 1
            if accused_identity is not None and k == 0:
                ident = accused_identity
                # name variant for the entity-resolution demo
                name = name_variant(ident["canonical_name"], rng) if rng.random() < 0.75 \
                    else ident["canonical_name"]
                tid = ident["true_identity_id"]
                gender = ident["gender"]
                age = ident["age"] if rng.random() > 0.10 else None  # some ages missing
                phone = ident["phone"] if rng.random() < 0.6 else (
                    f"9{rng.randint(100000000, 999999999)}" if rng.random() < 0.7 else None)
                p_district = ident["home_district"]
            else:
                gender = rng.choice(["Male", "Male", "Female"])
                name = fake.name_male() if gender == "Male" else fake.name_female()
                name = re.sub(r"^(Dr\.|Mr\.|Mrs\.|Ms\.|Miss|Smt\.|Shri)\s+", "", name).strip()
                tid = f"TID-OneOff-{person_counter}"
                age = rng.randint(18, 60) if rng.random() > 0.10 else None
                phone = f"9{rng.randint(100000000, 999999999)}" if rng.random() < 0.7 else None
                p_district = district
            persons.append({
                "person_id": f"P{start_idx + person_counter:07d}", "fir_number": fir,
                "full_name": name, "normalized_name": normalize_name(name),
                "role": "Accused" if k == 0 else rng.choice(["Suspect", "Accused"]),
                "gender": gender, "age": age, "phone": phone,
                "address": (fake.address().replace("\n", ", ") if rng.random() > 0.15 else None),
                "district": p_district,
                "true_identity_id": tid,
            })

        # complainant/victim
        person_counter += 1
        v_gender = rng.choice(["Male", "Female"])
        v_name = fake.name_male() if v_gender == "Male" else fake.name_female()
        v_name = re.sub(r"^(Dr\.|Mr\.|Mrs\.|Ms\.|Miss|Smt\.|Shri)\s+", "", v_name).strip()
        persons.append({
            "person_id": f"P{start_idx + person_counter:07d}", "fir_number": fir,
            "full_name": v_name, "normalized_name": normalize_name(v_name),
            "role": rng.choice(["Complainant", "Victim"]),
            "gender": v_gender,
            "age": rng.randint(18, 75) if rng.random() > 0.12 else None,
            "phone": f"9{rng.randint(100000000, 999999999)}" if rng.random() < 0.85 else None,
            "address": (fake.address().replace("\n", ", ") if rng.random() > 0.15 else None),
            "district": district,
            "true_identity_id": f"TID-Victim-{person_counter}",
        })

        # occasional witness
        if rng.random() < 0.18:
            person_counter += 1
            w_gender = rng.choice(["Male", "Female"])
            w_name = fake.name_male() if w_gender == "Male" else fake.name_female()
            w_name = re.sub(r"^(Dr\.|Mr\.|Mrs\.|Ms\.|Miss|Smt\.|Shri)\s+", "", w_name).strip()
            persons.append({
                "person_id": f"P{start_idx + person_counter:07d}", "fir_number": fir,
                "full_name": w_name, "normalized_name": normalize_name(w_name),
                "role": "Witness", "gender": w_gender,
                "age": rng.randint(18, 70) if rng.random() > 0.2 else None,
                "phone": f"9{rng.randint(100000000, 999999999)}" if rng.random() < 0.5 else None,
                "address": (fake.address().replace("\n", ", ") if rng.random() > 0.3 else None),
                "district": district, "true_identity_id": f"TID-Witness-{person_counter}",
            })

        # ---------- vehicles linked to this FIR ----------
        # Higher attach rate for vehicle-relevant crimes; a smaller chance otherwise
        # (a vehicle merely seen/used). Tuned so the 8k seed yields ~4k vehicles.
        veh_prob = 0.85 if crime_type in VEHICLE_INVOLVED_TYPES else 0.28
        n_veh = 0
        while rng.random() < veh_prob and n_veh < 2:
            n_veh += 1
            vehicle_counter += 1
            # gang vehicles + recurring pool drive network components
            if accused_identity in GANG_MEMBERS or rng.random() < 0.4:
                reg = rng.choice(RECURRING_VEHICLES)
            else:
                reg = ka_reg(rng)
            vehicles.append({
                "vehicle_id": f"V{start_idx + vehicle_counter:07d}", "fir_number": fir,
                "reg_number": reg, "vehicle_type": rng.choice(VEHICLE_TYPES),
                "make_color": (f"{rng.choice(VEHICLE_COLORS)} {rng.choice(['Honda','Bajaj','TVS','Maruti','Hyundai','Hero'])}"
                               if rng.random() > 0.2 else None),  # some make/color missing
            })
            veh_prob *= 0.4  # steep drop-off for a second vehicle

    # interleave clustered + random incidents, shuffle order for realism
    order = list(range(n_crimes))
    rng.shuffle(cluster_specs)
    specs_full = cluster_specs + [None] * n_random
    rng.shuffle(specs_full)
    specs_full = specs_full[:n_crimes]

    for idx in order:
        make_incident(idx, specs_full[idx])

    return crimes, persons, vehicles


# ================================================================================
# WRITE OUTPUTS
# ================================================================================
def to_df(rows, cols):
    return pd.DataFrame(rows, columns=cols)


def write_seed():
    print("Generating SEED set (8,000 crimes)...")
    crimes, persons, vehicles = generate(8000, fir_prefix="FIR", start_idx=0,
                                         use_clusters=True, rng_seed=SEED)
    cdf = to_df(crimes, CRIME_COLUMNS)
    pdf = to_df(persons, PERSON_COLUMNS)
    vdf = to_df(vehicles, VEHICLE_COLUMNS)
    cdf.to_csv(SEED_DIR / "crimes.csv", index=False)
    pdf.to_csv(SEED_DIR / "persons.csv", index=False)
    vdf.to_csv(SEED_DIR / "vehicles.csv", index=False)
    return cdf, pdf, vdf


def write_samples(seed_crimes: pd.DataFrame):
    print("Generating LARGE stress set (50,000 crimes)...")
    big_crimes, _, _ = generate(50000, fir_prefix="FIRX", start_idx=900000,
                                use_clusters=True, rng_seed=SEED + 1)
    big = to_df(big_crimes, CRIME_COLUMNS)
    big.to_csv(SAMPLES_DIR / "crimes_large.csv", index=False)

    # subsets in multiple formats (drawn from the large set)
    sub5k = big.sample(n=5000, random_state=SEED).reset_index(drop=True)
    sub3k = big.sample(n=3000, random_state=SEED + 2).reset_index(drop=True)

    # JSON (records orient)
    sub5k.to_json(SAMPLES_DIR / "crimes.json", orient="records", indent=2)
    # NDJSON
    sub5k.to_json(SAMPLES_DIR / "crimes.ndjson", orient="records", lines=True)
    # Excel
    sub5k.to_excel(SAMPLES_DIR / "crimes.xlsx", index=False, engine="openpyxl")

    # GeoJSON FeatureCollection of Points
    features = []
    for _, r in sub3k.iterrows():
        props = {k: (None if pd.isna(r[k]) else r[k]) for k in CRIME_COLUMNS
                 if k not in ("latitude", "longitude")}
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [float(r["longitude"]), float(r["latitude"])]},
            "properties": props,
        })
    geojson = {"type": "FeatureCollection", "features": features}
    (SAMPLES_DIR / "crimes.geojson").write_text(json.dumps(geojson, indent=1), encoding="utf-8")

    # NEW incidents batch — ~600 recent (June 2026) with a couple of NEW hotspots
    print("Generating new_incidents batch (~600, June 2026)...")
    new_rows, _, _ = generate(600, fir_prefix="FIRNEW", start_idx=990000,
                              use_clusters=False, rng_seed=SEED + 7)
    ndf = to_df(new_rows, CRIME_COLUMNS)
    # force all into June 2026 and inject two NEW hotspot areas (not in seed clusters)
    new_hotspots = [
        ("Bengaluru City", (12.9911, 77.6987)),  # new Marathahalli-area hotspot
        ("Mysuru", (12.3072, 76.6520)),          # new Mysuru hotspot
    ]
    for i in range(len(ndf)):
        june_day = random.randint(1, 13)
        hour = pick_hour(ndf.at[i, "crime_type"], random)
        occ = datetime(2026, 6, june_day, hour, random.randint(0, 59))
        if i % 3 == 0:  # ~1/3 land in the new hotspots
            dist, ctr = new_hotspots[i % len(new_hotspots)]
            lat, lng = jitter_coords(ctr, 0.005, random)
            ndf.at[i, "district"] = dist
            ndf.at[i, "latitude"] = lat
            ndf.at[i, "longitude"] = lng
            ndf.at[i, "h3_r7"] = h3.latlng_to_cell(lat, lng, 7)
            ndf.at[i, "h3_r8"] = h3.latlng_to_cell(lat, lng, 8)
            ndf.at[i, "h3_r9"] = h3.latlng_to_cell(lat, lng, 9)
        ndf.at[i, "occurred_at"] = occ.isoformat()
        ndf.at[i, "reported_at"] = (occ + reporting_delay(ndf.at[i, "crime_type"], random)).isoformat()
        ndf.at[i, "hour"] = occ.hour
        ndf.at[i, "day_of_week"] = occ.weekday()
        ndf.at[i, "status"] = "Open"
    ndf.to_csv(SAMPLES_DIR / "new_incidents.csv", index=False)

    # connect-your-own template (header only) + mapping example
    pd.DataFrame(columns=CRIME_COLUMNS).to_csv(
        SAMPLES_DIR / "connect_your_own_TEMPLATE.csv", index=False)
    mapping_example = {
        "_comment": "Map YOUR arbitrary column names (keys) to DRISHTI canonical fields "
                    "(values). Pass this JSON as the 'mapping' field to POST /ingest. "
                    "Unmapped canonical fields are treated as missing (never fabricated).",
        "mapping": {
            "FIR No": "fir_number",
            "Dist": "district",
            "PS": "police_station",
            "Offence": "crime_type",
            "Category": "crime_category",
            "Lat": "latitude",
            "Long": "longitude",
            "Date of Offence": "occurred_at",
            "Date Reported": "reported_at",
            "MO": "modus_operandi",
            "Remarks": "description",
            "Case Status": "status",
            "Loss Value": "property_value_inr",
            "Weapon": "weapon_used",
        },
        "notes": [
            "Date columns are parsed to ISO8601; hour/day_of_week/h3_* are derived if lat/lng present.",
            "Any canonical column absent from the mapping is reported in missing_report, not invented.",
        ],
    }
    (SAMPLES_DIR / "MAPPING_EXAMPLE.json").write_text(
        json.dumps(mapping_example, indent=2), encoding="utf-8")

    return big, ndf


def summarize(cdf, pdf, vdf):
    print("\n=== SEED summary ===")
    print(f"crimes : {len(cdf):,}")
    print(f"persons: {len(pdf):,}")
    print(f"vehicles:{len(vdf):,}")
    beng = (cdf["district"] == "Bengaluru City").mean() * 100
    print(f"Bengaluru City share: {beng:.1f}%")
    print("Top crime types:")
    print(cdf["crime_type"].value_counts().head(6).to_string())
    print(f"Distinct true identities in persons: "
          f"{pdf['true_identity_id'].str.startswith('TID0').sum()} accused-identity rows "
          f"across {pdf[pdf['true_identity_id'].str.match(r'TID[0-9]')]['true_identity_id'].nunique()} TIDs")
    recur_veh = vdf["reg_number"].value_counts()
    print(f"Vehicles recurring in >=3 FIRs: {(recur_veh >= 3).sum()}")
    # Missingness reported conditional on records that *should* carry the field,
    # so the ~12% / ~8% targets are visible (NULLs are never fabricated back).
    pv_relevant = cdf[cdf["crime_type"].isin(PROPERTY_VALUE_TYPES)]
    wp_relevant = cdf[cdf["crime_type"].isin(WEAPON_TYPES)]
    print(f"Missing property_value_inr (among property/fraud FIRs): "
          f"{pv_relevant['property_value_inr'].isna().mean()*100:.1f}%")
    print(f"Missing weapon_used (among weapon-relevant FIRs): "
          f"{wp_relevant['weapon_used'].isna().mean()*100:.1f}%")
    print(f"Missing age (persons): {pdf['age'].isna().mean()*100:.1f}%  | "
          f"Missing phone: {pdf['phone'].isna().mean()*100:.1f}%  | "
          f"Missing address: {pdf['address'].isna().mean()*100:.1f}%")


def main():
    cdf, pdf, vdf = write_seed()
    big, ndf = write_samples(cdf)
    summarize(cdf, pdf, vdf)

    print("\n=== Files written ===")
    targets = [
        SEED_DIR / "crimes.csv", SEED_DIR / "persons.csv", SEED_DIR / "vehicles.csv",
        SAMPLES_DIR / "crimes_large.csv", SAMPLES_DIR / "crimes.json",
        SAMPLES_DIR / "crimes.ndjson", SAMPLES_DIR / "crimes.geojson",
        SAMPLES_DIR / "crimes.xlsx", SAMPLES_DIR / "new_incidents.csv",
        SAMPLES_DIR / "connect_your_own_TEMPLATE.csv", SAMPLES_DIR / "MAPPING_EXAMPLE.json",
    ]
    for p in targets:
        size_kb = p.stat().st_size / 1024
        print(f"  {p.relative_to(ROOT)}  ({size_kb:,.1f} KB)")
    print("\nDone.")


if __name__ == "__main__":
    main()
