"""DRISHTI Demo Showcase Seeder.

Run once to inject carefully crafted records that demonstrate every feature
with specific known names and FIR numbers you can call out in a video.

Usage (from repo root):
    cd demo
    python seed_demo_data.py

Or from repo root:
    python demo/seed_demo_data.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from backend.db import SessionLocal, engine
from backend.models import Base, Crime, Person, Vehicle, CDR, Account, Transaction, MissingPerson

Base.metadata.create_all(bind=engine)
db = SessionLocal()

def skip_if_exists(model, **kwargs):
    if db.query(model).filter_by(**kwargs).first():
        return True
    return False

inserted = {"crimes": 0, "persons": 0, "vehicles": 0, "cdr": 0,
            "accounts": 0, "transactions": 0, "missing": 0}

# ════════════════════════════════════════════════════════════════════════════
# BLOCK 1 — THE NAIK CRIME RING (for Network, Motif Detection, Correlation)
#
# Three brothers — Suresh Naik, Ramesh Naik, Ganesh Naik — operating in
# Bengaluru's Koramangala area. They appear as a triangle in the network
# graph and are the top motif in the motif-detection view.
# ════════════════════════════════════════════════════════════════════════════
ring_crimes = [
    dict(fir_number="DEMO-FIR-001", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Robbery",
         crime_category="Violent", severity=4,
         latitude=12.9352, longitude=77.6245,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2025-11-10T21:30:00", reported_at="2025-11-11T08:00:00",
         hour=21, day_of_week=0,
         modus_operandi="three accused approached victim on motorcycle, threatened with knife, gold chain and mobile phone snatched, fled towards Sony Signal",
         description="Victim Priya Reddy was returning home when three accused accosted her near Koramangala 4th Block. Knife brandished, gold chain (28g) and iPhone stolen. CCTV footage obtained.",
         status="UnderInvestigation", victim_count=1, accused_count=3,
         property_value_inr=195000, weapon_used="knife", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-002", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Vehicle Theft",
         crime_category="Property", severity=4,
         latitude=12.9360, longitude=77.6255,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2025-11-24T02:15:00", reported_at="2025-11-24T09:30:00",
         hour=2, day_of_week=0,
         modus_operandi="master key used to start motorcycle, stolen from apartment basement parking, two accused on foot, CCTV footage obtained from parking",
         description="Bajaj Pulsar motorcycle (KA-05-MA-1234) stolen from basement parking of Koramangala apartment complex. Master key method. Two accused identified on CCTV.",
         status="UnderInvestigation", victim_count=1, accused_count=2,
         property_value_inr=85000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-003", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Chain Snatching",
         crime_category="Violent", severity=3,
         latitude=12.9340, longitude=77.6235,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2025-12-05T07:45:00", reported_at="2025-12-05T10:00:00",
         hour=7, day_of_week=4,
         modus_operandi="pillion rider snatched chain while victim was walking, motorcycle sped away, similar method to previous incidents near 5th Block",
         description="Elderly victim's gold chain snatched by pillion rider of motorcycle near Koramangala 5th Block junction. Pattern consistent with earlier incidents. Same motorcycle description as DEMO-FIR-001.",
         status="Open", victim_count=1, accused_count=2,
         property_value_inr=72000, weapon_used="knife", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-004", district="Bengaluru City",
         police_station="BTM Layout PS", crime_type="House Theft",
         crime_category="Property", severity=3,
         latitude=12.9145, longitude=77.6140,
         h3_r7="876014580ffffff", h3_r8="886014585bfffff", h3_r9="896014585abffff",
         occurred_at="2025-12-15T14:00:00", reported_at="2025-12-15T19:30:00",
         hour=14, day_of_week=0,
         modus_operandi="window grills bent with iron rod, gang of three entered while family was away, laptops, gold, and cash stolen, neighbours heard noise",
         description="House broken into while family was away. Three masked men bent window grills and entered. Laptops (2), gold jewellery and cash stolen. Neighbours identified one suspect.",
         status="UnderInvestigation", victim_count=1, accused_count=3,
         property_value_inr=285000, weapon_used="iron rod", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-005", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Extortion",
         crime_category="Violent", severity=4,
         latitude=12.9355, longitude=77.6240,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2026-01-08T20:00:00", reported_at="2026-01-09T09:00:00",
         hour=20, day_of_week=2,
         modus_operandi="victim called on unknown number, threatened to harm family unless 2 lakh paid, knife shown during in-person meeting, victim paid 50000 cash",
         description="Shop owner threatened by three callers. Demanded Rs 2 lakh. Victim paid Rs 50,000 at Koramangala 7th Block. Suspects spoke in local dialect — believed to be same gang as prior robberies.",
         status="Open", victim_count=1, accused_count=3,
         property_value_inr=50000, weapon_used="knife", source="demo-showcase"),
]
for c in ring_crimes:
    if not skip_if_exists(Crime, fir_number=c["fir_number"]):
        db.add(Crime(**c)); inserted["crimes"] += 1

# Persons for the Naik Crime Ring
ring_persons = [
    # DEMO-FIR-001 (robbery) — all three brothers
    dict(person_id="PD0001", fir_number="DEMO-FIR-001", full_name="Suresh D. Naik",
         normalized_name="suresh d naik", role="Accused", gender="Male", age=32,
         phone="9900001111", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-SURESH"),
    dict(person_id="PD0002", fir_number="DEMO-FIR-001", full_name="Ramesh D. Naik",
         normalized_name="ramesh d naik", role="Accused", gender="Male", age=28,
         phone="9900002222", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-RAMESH"),
    dict(person_id="PD0003", fir_number="DEMO-FIR-001", full_name="Ganesh D. Naik",
         normalized_name="ganesh d naik", role="Accused", gender="Male", age=25,
         phone="9900003333", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-GANESH"),
    dict(person_id="PD0004", fir_number="DEMO-FIR-001", full_name="Priya Reddy",
         normalized_name="priya reddy", role="Victim", gender="Female", age=29,
         phone="9876500001", address="Koramangala 4th Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-VICTIM1"),
    # DEMO-FIR-002 (vehicle theft) — Suresh + Ramesh
    dict(person_id="PD0005", fir_number="DEMO-FIR-002", full_name="Suresh D. Naik",
         normalized_name="suresh d naik", role="Accused", gender="Male", age=32,
         phone="9900001111", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-SURESH"),
    dict(person_id="PD0006", fir_number="DEMO-FIR-002", full_name="Ramesh D. Naik",
         normalized_name="ramesh d naik", role="Accused", gender="Male", age=28,
         phone="9900002222", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-RAMESH"),
    # DEMO-FIR-003 (chain snatching) — Suresh + Ganesh
    dict(person_id="PD0007", fir_number="DEMO-FIR-003", full_name="Suresh D. Naik",
         normalized_name="suresh d naik", role="Accused", gender="Male", age=32,
         phone="9900001111", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-SURESH"),
    dict(person_id="PD0008", fir_number="DEMO-FIR-003", full_name="Ganesh D. Naik",
         normalized_name="ganesh d naik", role="Accused", gender="Male", age=25,
         phone="9900003333", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-GANESH"),
    # DEMO-FIR-004 (house theft) — Ramesh + Ganesh + Suresh
    dict(person_id="PD0009", fir_number="DEMO-FIR-004", full_name="Ramesh D. Naik",
         normalized_name="ramesh d naik", role="Accused", gender="Male", age=28,
         phone="9900002222", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-RAMESH"),
    dict(person_id="PD0010", fir_number="DEMO-FIR-004", full_name="Ganesh D. Naik",
         normalized_name="ganesh d naik", role="Accused", gender="Male", age=25,
         phone="9900003333", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-GANESH"),
    dict(person_id="PD0011", fir_number="DEMO-FIR-004", full_name="Suresh D. Naik",
         normalized_name="suresh d naik", role="Accused", gender="Male", age=32,
         phone="9900001111", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-SURESH"),
    # DEMO-FIR-005 (extortion) — all three
    dict(person_id="PD0012", fir_number="DEMO-FIR-005", full_name="Suresh D. Naik",
         normalized_name="suresh d naik", role="Accused", gender="Male", age=32,
         phone="9900001111", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-SURESH"),
    dict(person_id="PD0013", fir_number="DEMO-FIR-005", full_name="Ramesh D. Naik",
         normalized_name="ramesh d naik", role="Accused", gender="Male", age=28,
         phone="9900002222", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-RAMESH"),
    dict(person_id="PD0014", fir_number="DEMO-FIR-005", full_name="Ganesh D. Naik",
         normalized_name="ganesh d naik", role="Accused", gender="Male", age=25,
         phone="9900003333", address="14/B, 4th Cross, Koramangala 3rd Block, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-GANESH"),
]
for p in ring_persons:
    if not skip_if_exists(Person, person_id=p["person_id"]):
        db.add(Person(**p)); inserted["persons"] += 1

# Vehicles for the Naik Ring
ring_vehicles = [
    dict(vehicle_id="VD0001", fir_number="DEMO-FIR-001", reg_number="KA-05-NX-7891",
         vehicle_type="Motorcycle", make_color="Black Honda Activa"),
    dict(vehicle_id="VD0002", fir_number="DEMO-FIR-002", reg_number="KA-05-MA-1234",
         vehicle_type="Motorcycle", make_color="Red Bajaj Pulsar"),
    dict(vehicle_id="VD0003", fir_number="DEMO-FIR-003", reg_number="KA-05-NX-7891",
         vehicle_type="Motorcycle", make_color="Black Honda Activa"),
]
for v in ring_vehicles:
    if not skip_if_exists(Vehicle, vehicle_id=v["vehicle_id"]):
        db.add(Vehicle(**v)); inserted["vehicles"] += 1

# ════════════════════════════════════════════════════════════════════════════
# BLOCK 2 — CDR EGO NETWORK (for CDR Analysis view)
#
# Search for phone 9900001111 (Suresh Naik) to see a 3-clique of the ring.
# The three brothers call each other and a 4th "unknown" contact (handler).
# ════════════════════════════════════════════════════════════════════════════
cdr_records = [
    # Suresh ↔ Ramesh (frequent calls before each crime)
    dict(cdr_id="CDR-DEMO-001", caller_msisdn="9900001111", callee_msisdn="9900002222",
         start_time="2025-11-09T19:30:00", duration_sec=245, cell_tower_id="TWR-BLR-KRM-01",
         tower_lat=12.9352, tower_lng=77.6245, call_type="voice"),
    dict(cdr_id="CDR-DEMO-002", caller_msisdn="9900002222", callee_msisdn="9900001111",
         start_time="2025-11-10T20:45:00", duration_sec=183, cell_tower_id="TWR-BLR-KRM-01",
         tower_lat=12.9352, tower_lng=77.6245, call_type="voice"),
    dict(cdr_id="CDR-DEMO-003", caller_msisdn="9900001111", callee_msisdn="9900002222",
         start_time="2025-11-23T23:00:00", duration_sec=312, cell_tower_id="TWR-BLR-KRM-02",
         tower_lat=12.9360, tower_lng=77.6255, call_type="voice"),
    # Suresh ↔ Ganesh
    dict(cdr_id="CDR-DEMO-004", caller_msisdn="9900001111", callee_msisdn="9900003333",
         start_time="2025-11-09T20:00:00", duration_sec=198, cell_tower_id="TWR-BLR-KRM-01",
         tower_lat=12.9352, tower_lng=77.6245, call_type="voice"),
    dict(cdr_id="CDR-DEMO-005", caller_msisdn="9900003333", callee_msisdn="9900001111",
         start_time="2025-12-04T22:30:00", duration_sec=276, cell_tower_id="TWR-BLR-KRM-01",
         tower_lat=12.9352, tower_lng=77.6245, call_type="voice"),
    # Ramesh ↔ Ganesh
    dict(cdr_id="CDR-DEMO-006", caller_msisdn="9900002222", callee_msisdn="9900003333",
         start_time="2025-11-09T20:15:00", duration_sec=124, cell_tower_id="TWR-BLR-KRM-01",
         tower_lat=12.9352, tower_lng=77.6245, call_type="voice"),
    dict(cdr_id="CDR-DEMO-007", caller_msisdn="9900003333", callee_msisdn="9900002222",
         start_time="2025-12-14T13:00:00", duration_sec=89, cell_tower_id="TWR-BLR-BTM-01",
         tower_lat=12.9145, tower_lng=77.6140, call_type="voice"),
    # All three contact Handler (unknown 4th party)
    dict(cdr_id="CDR-DEMO-008", caller_msisdn="9900001111", callee_msisdn="9900004444",
         start_time="2025-11-10T22:00:00", duration_sec=67, cell_tower_id="TWR-BLR-KRM-01",
         tower_lat=12.9352, tower_lng=77.6245, call_type="voice"),
    dict(cdr_id="CDR-DEMO-009", caller_msisdn="9900002222", callee_msisdn="9900004444",
         start_time="2025-11-25T08:00:00", duration_sec=55, cell_tower_id="TWR-BLR-KRM-02",
         tower_lat=12.9360, tower_lng=77.6255, call_type="voice"),
    dict(cdr_id="CDR-DEMO-010", caller_msisdn="9900003333", callee_msisdn="9900004444",
         start_time="2025-12-06T09:15:00", duration_sec=44, cell_tower_id="TWR-BLR-KRM-01",
         tower_lat=12.9340, tower_lng=77.6235, call_type="voice"),
    # Handler calls back Suresh (confirms command structure)
    dict(cdr_id="CDR-DEMO-011", caller_msisdn="9900004444", callee_msisdn="9900001111",
         start_time="2025-11-11T07:00:00", duration_sec=302, cell_tower_id="TWR-BLR-HBL-01",
         tower_lat=13.0450, tower_lng=77.5973, call_type="voice"),
    dict(cdr_id="CDR-DEMO-012", caller_msisdn="9900004444", callee_msisdn="9900001111",
         start_time="2025-12-16T10:00:00", duration_sec=185, cell_tower_id="TWR-BLR-HBL-01",
         tower_lat=13.0450, tower_lng=77.5973, call_type="voice"),
]
for r in cdr_records:
    if not skip_if_exists(CDR, cdr_id=r["cdr_id"]):
        db.add(CDR(**r)); inserted["cdr"] += 1

# ════════════════════════════════════════════════════════════════════════════
# BLOCK 3 — ARJUN SHARMA: ESCALATING CAREER (for Behavioral Analytics)
#
# Search "Arjun Sharma" in Behavioral tab to see career timeline,
# escalating severity 1->5, risk score ~75 (High), knife -> firearm.
# ════════════════════════════════════════════════════════════════════════════
career_crimes = [
    dict(fir_number="DEMO-FIR-010", district="Bengaluru City",
         police_station="Shivajinagar PS", crime_type="Petty Theft",
         crime_category="Property", severity=1,
         latitude=12.9779, longitude=77.5988,
         h3_r7="8760145b4ffffff", h3_r8="8860145b41fffff", h3_r9="8960145b403ffff",
         occurred_at="2023-03-14T11:00:00", reported_at="2023-03-14T14:30:00",
         hour=11, day_of_week=1,
         modus_operandi="wallet lifted from victim's pocket in crowded bus, accused blended into crowd",
         description="Victim's wallet with Rs 3,200 cash and debit card stolen in BMTC bus. Accused not identified at time of report.",
         status="Closed", victim_count=1, accused_count=1,
         property_value_inr=3200, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-011", district="Bengaluru City",
         police_station="Shivajinagar PS", crime_type="Petty Theft",
         crime_category="Property", severity=2,
         latitude=12.9785, longitude=77.5994,
         h3_r7="8760145b4ffffff", h3_r8="8860145b41fffff", h3_r9="8960145b403ffff",
         occurred_at="2023-08-20T16:30:00", reported_at="2023-08-20T18:00:00",
         hour=16, day_of_week=6,
         modus_operandi="mobile phone snatched from victim's hand in market area, suspect fled on foot, caught and identified",
         description="Victim's mobile (OnePlus Nord) snatched in Commercial Street market. Accused caught by public and handed to police. First arrest — accused identified as Arjun Sharma.",
         status="Closed", victim_count=1, accused_count=1,
         property_value_inr=22000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-012", district="Bengaluru City",
         police_station="Shivajinagar PS", crime_type="House Theft",
         crime_category="Property", severity=3,
         latitude=12.9769, longitude=77.5978,
         h3_r7="8760145b4ffffff", h3_r8="8860145b41fffff", h3_r9="8960145b403ffff",
         occurred_at="2024-02-10T03:00:00", reported_at="2024-02-10T07:00:00",
         hour=3, day_of_week=5,
         modus_operandi="door lock broken with iron rod, entered while family asleep, cash and jewellery stolen, left quietly",
         description="Ground-floor apartment broken into at 3AM while family slept. Rs 45,000 cash and gold chain stolen. Fingerprints matched Arjun Sharma from prior arrest.",
         status="ChargeSheeted", victim_count=1, accused_count=1,
         property_value_inr=48000, weapon_used="iron rod", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-013", district="Bengaluru City",
         police_station="Shivajinagar PS", crime_type="Chain Snatching",
         crime_category="Violent", severity=3,
         latitude=12.9775, longitude=77.5991,
         h3_r7="8760145b4ffffff", h3_r8="8860145b41fffff", h3_r9="8960145b403ffff",
         occurred_at="2024-07-18T08:00:00", reported_at="2024-07-18T09:30:00",
         hour=8, day_of_week=3,
         modus_operandi="victim walking near temple, chain snatched and victim pushed to ground, knife used to threaten when victim resisted",
         description="Victim's gold chain snatched near Shivajinagar temple. Victim who resisted was threatened with knife. Witness identified Arjun Sharma from previous FIR photograph.",
         status="ChargeSheeted", victim_count=1, accused_count=1,
         property_value_inr=55000, weapon_used="knife", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-014", district="Bengaluru City",
         police_station="Shivajinagar PS", crime_type="Robbery",
         crime_category="Violent", severity=4,
         latitude=12.9780, longitude=77.5986,
         h3_r7="8760145b4ffffff", h3_r8="8860145b41fffff", h3_r9="8960145b403ffff",
         occurred_at="2025-01-22T22:00:00", reported_at="2025-01-23T08:00:00",
         hour=22, day_of_week=2,
         modus_operandi="grocery shop looted at knife-point after closing time, two staff members tied up, cash and stock stolen, CCTV cameras disabled",
         description="Shivajinagar grocery shop looted. Two employees tied and gagged. Cash drawer (Rs 1.2L) and cigarette stock stolen. CCTV disabled beforehand. Arjun Sharma prime suspect.",
         status="UnderInvestigation", victim_count=2, accused_count=1,
         property_value_inr=145000, weapon_used="knife", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-015", district="Bengaluru City",
         police_station="Shivajinagar PS", crime_type="Robbery with Grievous Hurt",
         crime_category="Violent", severity=5,
         latitude=12.9783, longitude=77.5992,
         h3_r7="8760145b4ffffff", h3_r8="8860145b41fffff", h3_r9="8960145b403ffff",
         occurred_at="2025-09-04T23:30:00", reported_at="2025-09-05T01:00:00",
         hour=23, day_of_week=3,
         modus_operandi="victim assaulted with knife causing deep lacerations, cash and watch stolen, victim required 12 stitches, witness called ambulance",
         description="Victim stabbed and robbed near Shivajinagar bus stand. 12 stitches on arm. Accused fled. Victim identified Arjun Sharma by photograph. Escalation noted — first use of knife to injure.",
         status="UnderInvestigation", victim_count=1, accused_count=1,
         property_value_inr=92000, weapon_used="knife", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-016", district="Bengaluru City",
         police_station="Shivajinagar PS", crime_type="Armed Robbery",
         crime_category="Violent", severity=5,
         latitude=12.9771, longitude=77.5981,
         h3_r7="8760145b4ffffff", h3_r8="8860145b41fffff", h3_r9="8960145b403ffff",
         occurred_at="2026-02-15T21:00:00", reported_at="2026-02-15T22:30:00",
         hour=21, day_of_week=6,
         modus_operandi="firearm brandished near ATM, two victims forced to withdraw cash, getaway bike used, country-made pistol recovered later",
         description="Two ATM users robbed at gunpoint outside Shivajinagar SBI ATM. Rs 2L withdrawn at gunpoint. Getaway motorcycle. CCTV identified Arjun Sharma. Significant escalation: firearm first use.",
         status="Open", victim_count=2, accused_count=1,
         property_value_inr=200000, weapon_used="firearm", source="demo-showcase"),
]
for c in career_crimes:
    if not skip_if_exists(Crime, fir_number=c["fir_number"]):
        db.add(Crime(**c)); inserted["crimes"] += 1

career_persons = [
    dict(person_id="PD0020", fir_number="DEMO-FIR-010", full_name="Arjun R. Sharma",
         normalized_name="arjun r sharma", role="Suspect", gender="Male", age=22,
         phone="9711112345", address="Room 4, Vinayaka Lodge, Shivajinagar, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-ARJUN"),
    dict(person_id="PD0021", fir_number="DEMO-FIR-011", full_name="Arjun R. Sharma",
         normalized_name="arjun r sharma", role="Accused", gender="Male", age=22,
         phone="9711112345", address="Room 4, Vinayaka Lodge, Shivajinagar, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-ARJUN"),
    dict(person_id="PD0022", fir_number="DEMO-FIR-012", full_name="Arjun Sharma",
         normalized_name="arjun sharma", role="Accused", gender="Male", age=23,
         phone="9711112345", address="Shivajinagar, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-ARJUN"),
    dict(person_id="PD0023", fir_number="DEMO-FIR-013", full_name="Arjun Sharma",
         normalized_name="arjun sharma", role="Accused", gender="Male", age=23,
         phone="9711112345", address="Shivajinagar, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-ARJUN"),
    dict(person_id="PD0024", fir_number="DEMO-FIR-014", full_name="Arjun R. Sharma",
         normalized_name="arjun r sharma", role="Accused", gender="Male", age=24,
         phone="9711112345", address="Shivajinagar, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-ARJUN"),
    dict(person_id="PD0025", fir_number="DEMO-FIR-015", full_name="A. R. Sharma",
         normalized_name="a r sharma", role="Accused", gender="Male", age=24,
         phone="9711112346", address="Shivajinagar, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-ARJUN"),
    dict(person_id="PD0026", fir_number="DEMO-FIR-016", full_name="Arjun Sharma",
         normalized_name="arjun sharma", role="Accused", gender="Male", age=25,
         phone="9711112346", address="Shivajinagar, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-ARJUN"),
]
for p in career_persons:
    if not skip_if_exists(Person, person_id=p["person_id"]):
        db.add(Person(**p)); inserted["persons"] += 1

# ════════════════════════════════════════════════════════════════════════════
# BLOCK 4 — ENTITY RESOLUTION ALIASES (for Investigations -> Entity Resolution)
#
# "Ravi Kumar" / "R. Kumar" / "Ravindra K." are the same person.
# Entity resolution should merge them and flag as HIGH confidence.
# ════════════════════════════════════════════════════════════════════════════
alias_crimes = [
    dict(fir_number="DEMO-FIR-020", district="Mysuru",
         police_station="Mysuru City PS", crime_type="Vehicle Theft",
         crime_category="Property", severity=3,
         latitude=12.2958, longitude=76.6394,
         h3_r7="876012a93ffffff", h3_r8="886012a939fffff", h3_r9="896012a9383ffff",
         occurred_at="2025-04-11T01:30:00", reported_at="2025-04-11T09:00:00",
         hour=1, day_of_week=4,
         modus_operandi="motorcycle stolen from market parking, master key used, partial plate captured on CCTV",
         description="Honda Activa stolen from Mysuru Devaraj Market parking. Partial plate KA-09-** visible on CCTV. Suspect identified as Ravi Kumar.",
         status="ChargeSheeted", victim_count=1, accused_count=1,
         property_value_inr=68000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-021", district="Mysuru",
         police_station="Mysuru Rural PS", crime_type="House Theft",
         crime_category="Property", severity=3,
         latitude=12.2940, longitude=76.6410,
         h3_r7="876012a93ffffff", h3_r8="886012a939fffff", h3_r9="896012a9383ffff",
         occurred_at="2025-06-18T15:00:00", reported_at="2025-06-18T20:00:00",
         hour=15, day_of_week=2,
         modus_operandi="gold jewellery stolen while family at wedding, suspect seen entering on CCTV, identified by neighbour as R. Kumar",
         description="Gold jewellery worth Rs 1.6L stolen from residence while family attended wedding. Neighbour identified suspect as R. Kumar, previously seen loitering.",
         status="UnderInvestigation", victim_count=1, accused_count=1,
         property_value_inr=162000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-022", district="Mysuru",
         police_station="Mysuru City PS", crime_type="Robbery",
         crime_category="Violent", severity=4,
         latitude=12.2970, longitude=76.6380,
         h3_r7="876012a93ffffff", h3_r8="886012a939fffff", h3_r9="896012a9383ffff",
         occurred_at="2025-10-02T20:30:00", reported_at="2025-10-02T22:00:00",
         hour=20, day_of_week=3,
         modus_operandi="shopkeeper robbed at knifepoint, cash from drawer taken, accused identified by shopkeeper as Ravindra K. who frequents area",
         description="Provision store robbed at knifepoint. Rs 30,000 from cash drawer. Shopkeeper identified accused as Ravindra K., a regular customer.",
         status="Open", victim_count=1, accused_count=1,
         property_value_inr=30000, weapon_used="knife", source="demo-showcase"),
]
for c in alias_crimes:
    if not skip_if_exists(Crime, fir_number=c["fir_number"]):
        db.add(Crime(**c)); inserted["crimes"] += 1

alias_persons = [
    dict(person_id="PD0030", fir_number="DEMO-FIR-020", full_name="Ravi Kumar",
         normalized_name="ravi kumar", role="Accused", gender="Male", age=35,
         phone="9845001111", address="15, Gandhi Nagar, Mysuru",
         district="Mysuru", true_identity_id="TID-DEMO-RAVI"),
    dict(person_id="PD0031", fir_number="DEMO-FIR-021", full_name="R. Kumar",
         normalized_name="r kumar", role="Suspect", gender="Male", age=35,
         phone="9845001111", address="Gandhi Nagar, Mysuru",
         district="Mysuru", true_identity_id="TID-DEMO-RAVI"),
    dict(person_id="PD0032", fir_number="DEMO-FIR-022", full_name="Ravindra K.",
         normalized_name="ravindra k", role="Accused", gender="Male", age=36,
         phone="9845001112", address="Mysuru",
         district="Mysuru", true_identity_id="TID-DEMO-RAVI"),
]
for p in alias_persons:
    if not skip_if_exists(Person, person_id=p["person_id"]):
        db.add(Person(**p)); inserted["persons"] += 1

# ════════════════════════════════════════════════════════════════════════════
# BLOCK 5 — CYBER FRAUD MONEY CHAIN (for Cyber -> Money Flow Explorer)
#
# Victim Meera Iyer defrauded via fake KYC call.
# Money flows: Meera -> Mule1 -> Mule2 -> Cash-out
# Search account ACC-DEMO-VICTIM in Money Flow Explorer.
# ════════════════════════════════════════════════════════════════════════════
cyber_crimes = [
    dict(fir_number="DEMO-FIR-030", district="Bengaluru City",
         police_station="Cyber Crime PS", crime_type="Phishing / OTP Fraud",
         crime_category="Cybercrime", severity=3,
         latitude=12.9716, longitude=77.5946,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2025-10-15T11:00:00", reported_at="2025-10-16T09:00:00",
         hour=11, day_of_week=2,
         modus_operandi="fake SBI KYC call, OTP compromised, multiple IMPS transfers, funds routed through mule accounts",
         description="Victim Meera Iyer received call claiming to be from SBI KYC team. Caller extracted OTP. Rs 4,85,000 transferred in multiple IMPS transactions to mule accounts. Account: ACC-DEMO-VICTIM.",
         status="UnderInvestigation", victim_count=1, accused_count=1,
         property_value_inr=485000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-031", district="Bengaluru City",
         police_station="Cyber Crime PS", crime_type="UPI Fraud",
         crime_category="Cybercrime", severity=3,
         latitude=12.9720, longitude=77.5950,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2025-10-22T15:30:00", reported_at="2025-10-23T10:00:00",
         hour=15, day_of_week=2,
         modus_operandi="fake collect request via UPI, victim scanned QR thinking it was payment receipt, UPI PIN shared, Rs 1.25L deducted",
         description="Second victim defrauded via UPI collect scam. Same mule account (ACC-DEMO-MULE1) used as first fraud. Pattern links DEMO-FIR-030 and DEMO-FIR-031.",
         status="UnderInvestigation", victim_count=1, accused_count=1,
         property_value_inr=125000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-032", district="Bengaluru City",
         police_station="Cyber Crime PS", crime_type="Investment Fraud",
         crime_category="Cybercrime", severity=4,
         latitude=12.9725, longitude=77.5955,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2025-11-05T09:00:00", reported_at="2025-11-06T10:30:00",
         hour=9, day_of_week=2,
         modus_operandi="Telegram investment group, fake stock tips, victim deposited 8 lakh expecting returns, funds routed through mule chain, group deleted",
         description="Victim lured into fake Telegram investment group promising 40% monthly returns. Rs 8L deposited in instalments. Same ACC-DEMO-MULE2 used. Group admin disappeared.",
         status="Open", victim_count=1, accused_count=1,
         property_value_inr=800000, weapon_used=None, source="demo-showcase"),
]
for c in cyber_crimes:
    if not skip_if_exists(Crime, fir_number=c["fir_number"]):
        db.add(Crime(**c)); inserted["crimes"] += 1

cyber_accounts = [
    dict(account_id="ACC-DEMO-VICTIM", holder_name="Meera Iyer",
         bank="SBI", district="Bengaluru City", is_mule=False),
    dict(account_id="ACC-DEMO-MULE1", holder_name="Farhan A. Khan",
         bank="Paytm Payments Bank", district="Bengaluru City", is_mule=True),
    dict(account_id="ACC-DEMO-MULE2", holder_name="Sonu Prasad",
         bank="Airtel Payments Bank", district="Davanagere", is_mule=True),
    dict(account_id="ACC-DEMO-CASHOUT", holder_name="Rajesh T.",
         bank="Bank of Baroda", district="Hubballi-Dharwad", is_mule=True),
    dict(account_id="ACC-DEMO-VIC2", holder_name="Sundar Krishnamurthy",
         bank="HDFC Bank", district="Bengaluru City", is_mule=False),
    dict(account_id="ACC-DEMO-VIC3", holder_name="Anita Mehta",
         bank="ICICI Bank", district="Bengaluru City", is_mule=False),
]
for a in cyber_accounts:
    if not skip_if_exists(Account, account_id=a["account_id"]):
        db.add(Account(**a)); inserted["accounts"] += 1

cyber_transactions = [
    # Victim -> Mule1 (two rapid transfers, DEMO-FIR-030)
    dict(txn_id="TXN-DEMO-001", from_account="ACC-DEMO-VICTIM",
         to_account="ACC-DEMO-MULE1", amount_inr=250000,
         timestamp="2025-10-15T11:23:00", channel="IMPS",
         fir_number="DEMO-FIR-030", is_flagged=True),
    dict(txn_id="TXN-DEMO-002", from_account="ACC-DEMO-VICTIM",
         to_account="ACC-DEMO-MULE1", amount_inr=235000,
         timestamp="2025-10-15T11:41:00", channel="IMPS",
         fir_number="DEMO-FIR-030", is_flagged=True),
    # Mule1 -> Mule2 (immediate layering)
    dict(txn_id="TXN-DEMO-003", from_account="ACC-DEMO-MULE1",
         to_account="ACC-DEMO-MULE2", amount_inr=460000,
         timestamp="2025-10-15T12:05:00", channel="IMPS",
         fir_number="DEMO-FIR-030", is_flagged=True),
    # Mule2 -> Cash-out
    dict(txn_id="TXN-DEMO-004", from_account="ACC-DEMO-MULE2",
         to_account="ACC-DEMO-CASHOUT", amount_inr=450000,
         timestamp="2025-10-15T14:30:00", channel="NEFT",
         fir_number="DEMO-FIR-030", is_flagged=True),
    # Second victim (DEMO-FIR-031)
    dict(txn_id="TXN-DEMO-005", from_account="ACC-DEMO-VIC2",
         to_account="ACC-DEMO-MULE1", amount_inr=125000,
         timestamp="2025-10-22T15:45:00", channel="UPI",
         fir_number="DEMO-FIR-031", is_flagged=True),
    dict(txn_id="TXN-DEMO-006", from_account="ACC-DEMO-MULE1",
         to_account="ACC-DEMO-MULE2", amount_inr=120000,
         timestamp="2025-10-22T16:30:00", channel="IMPS",
         fir_number="DEMO-FIR-031", is_flagged=True),
    # Third victim investment fraud (DEMO-FIR-032)
    dict(txn_id="TXN-DEMO-007", from_account="ACC-DEMO-VIC3",
         to_account="ACC-DEMO-MULE2", amount_inr=400000,
         timestamp="2025-11-05T09:30:00", channel="NEFT",
         fir_number="DEMO-FIR-032", is_flagged=True),
    dict(txn_id="TXN-DEMO-008", from_account="ACC-DEMO-VIC3",
         to_account="ACC-DEMO-MULE2", amount_inr=400000,
         timestamp="2025-11-05T14:00:00", channel="NEFT",
         fir_number="DEMO-FIR-032", is_flagged=True),
    dict(txn_id="TXN-DEMO-009", from_account="ACC-DEMO-MULE2",
         to_account="ACC-DEMO-CASHOUT", amount_inr=790000,
         timestamp="2025-11-06T10:00:00", channel="RTGS",
         fir_number="DEMO-FIR-032", is_flagged=True),
]
for t in cyber_transactions:
    if not skip_if_exists(Transaction, txn_id=t["txn_id"]):
        db.add(Transaction(**t)); inserted["transactions"] += 1

cyber_persons = [
    dict(person_id="PD0040", fir_number="DEMO-FIR-030", full_name="Meera Iyer",
         normalized_name="meera iyer", role="Victim", gender="Female", age=44,
         phone="9845002222", address="Indiranagar, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-MEERA"),
    dict(person_id="PD0041", fir_number="DEMO-FIR-030", full_name="Farhan A. Khan",
         normalized_name="farhan a khan", role="Accused", gender="Male", age=29,
         phone="9900009999", address="Unknown — Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-FARHAN"),
    dict(person_id="PD0042", fir_number="DEMO-FIR-031", full_name="Sundar Krishnamurthy",
         normalized_name="sundar krishnamurthy", role="Victim", gender="Male", age=52,
         phone="9845003333", address="Jayanagar, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-SUNDAR"),
    dict(person_id="PD0043", fir_number="DEMO-FIR-032", full_name="Anita Mehta",
         normalized_name="anita mehta", role="Victim", gender="Female", age=38,
         phone="9845004444", address="HSR Layout, Bengaluru",
         district="Bengaluru City", true_identity_id="TID-DEMO-ANITA"),
]
for p in cyber_persons:
    if not skip_if_exists(Person, person_id=p["person_id"]):
        db.add(Person(**p)); inserted["persons"] += 1

# ════════════════════════════════════════════════════════════════════════════
# BLOCK 6 — NEAR-REPEAT HOTSPOT CLUSTER (Hotspots, Near-Repeat, Forecast)
#
# 8 vehicle thefts in same Koramangala hex over 30 days.
# The near-repeat view should flag all of these.
# ════════════════════════════════════════════════════════════════════════════
hotspot_crimes = [
    dict(fir_number="DEMO-FIR-040", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Vehicle Theft",
         crime_category="Property", severity=4,
         latitude=12.9348, longitude=77.6248,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2026-04-01T01:00:00", reported_at="2026-04-01T08:00:00",
         hour=1, day_of_week=1,
         modus_operandi="two-wheeler stolen from open parking, master key used",
         description="Motorcycle stolen from Koramangala 3rd Block open parking. Pattern: master key.",
         status="Open", victim_count=1, accused_count=1,
         property_value_inr=75000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-041", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Vehicle Theft",
         crime_category="Property", severity=4,
         latitude=12.9355, longitude=77.6243,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2026-04-05T02:30:00", reported_at="2026-04-05T09:00:00",
         hour=2, day_of_week=6,
         modus_operandi="two-wheeler stolen from apartment basement, master key used, similar to 1st April incident",
         description="Scooter stolen from apartment basement. Same master-key MO as DEMO-FIR-040. Near-repeat within 0.3 km, 4 days.",
         status="Open", victim_count=1, accused_count=1,
         property_value_inr=62000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-042", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Vehicle Theft",
         crime_category="Property", severity=4,
         latitude=12.9343, longitude=77.6252,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2026-04-09T00:45:00", reported_at="2026-04-09T07:30:00",
         hour=0, day_of_week=3,
         modus_operandi="motorcycle stolen from roadside, third incident in same area within fortnight",
         description="Third vehicle theft in same hex cell within 14 days. Clear near-repeat pattern. Patrol increased per request.",
         status="Open", victim_count=1, accused_count=1,
         property_value_inr=55000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-043", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Vehicle Theft",
         crime_category="Property", severity=4,
         latitude=12.9350, longitude=77.6250,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2026-04-14T03:15:00", reported_at="2026-04-14T08:00:00",
         hour=3, day_of_week=1,
         modus_operandi="two-wheeler stolen, same location, continuing series",
         description="Fourth incident in 2 weeks. Patrol deployment from DEMO-FIR-042 not yet effective.",
         status="Open", victim_count=1, accused_count=1,
         property_value_inr=80000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-044", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Vehicle Theft",
         crime_category="Property", severity=4,
         latitude=12.9352, longitude=77.6246,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2026-04-18T01:30:00", reported_at="2026-04-18T07:00:00",
         hour=1, day_of_week=5,
         modus_operandi="fifth incident, two-wheeler taken from residential compound",
         description="Continuing hotspot series. Five incidents in 18 days. Same micro-location cluster.",
         status="Open", victim_count=1, accused_count=1,
         property_value_inr=68000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-045", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Vehicle Theft",
         crime_category="Property", severity=4,
         latitude=12.9345, longitude=77.6255,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2026-04-22T02:00:00", reported_at="2026-04-22T09:30:00",
         hour=2, day_of_week=2,
         modus_operandi="sixth theft, master key, roadside parking, late night pattern confirmed",
         description="Sixth in cluster. Time pattern: all between 00:00–03:30. Master key consistent.",
         status="Open", victim_count=1, accused_count=1,
         property_value_inr=72000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-046", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Vehicle Theft",
         crime_category="Property", severity=4,
         latitude=12.9358, longitude=77.6241,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2026-04-27T01:15:00", reported_at="2026-04-27T08:00:00",
         hour=1, day_of_week=0,
         modus_operandi="seventh theft, same cluster, nighttime pattern",
         description="Seventh vehicle theft in same hex cluster in April 2026.",
         status="Open", victim_count=1, accused_count=1,
         property_value_inr=65000, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-047", district="Bengaluru City",
         police_station="Koramangala PS", crime_type="Vehicle Theft",
         crime_category="Property", severity=4,
         latitude=12.9353, longitude=77.6249,
         h3_r7="876014580ffffff", h3_r8="886014582bfffff", h3_r9="8960145806bffff",
         occurred_at="2026-04-30T00:30:00", reported_at="2026-04-30T07:00:00",
         hour=0, day_of_week=3,
         modus_operandi="eighth theft in one month — all identical master-key method, same hex cell",
         description="Eighth incident. All 8 within same 500m radius and 30-day window. Clear near-repeat victimisation cluster — textbook case.",
         status="Open", victim_count=1, accused_count=1,
         property_value_inr=78000, weapon_used=None, source="demo-showcase"),
]
for c in hotspot_crimes:
    if not skip_if_exists(Crime, fir_number=c["fir_number"]):
        db.add(Crime(**c)); inserted["crimes"] += 1

# ════════════════════════════════════════════════════════════════════════════
# BLOCK 7 — MISSING PERSONS (for Missing Persons view)
#
# High-risk missing person case + one repeat disappearance.
# ════════════════════════════════════════════════════════════════════════════
missing_crimes = [
    dict(fir_number="DEMO-FIR-050", district="Bengaluru City",
         police_station="Ulsoor PS", crime_type="Missing Person",
         crime_category="Vulnerable", severity=5,
         latitude=12.9840, longitude=77.6108,
         h3_r7="8760145b4ffffff", h3_r8="8860145b41fffff", h3_r9="8960145b403ffff",
         occurred_at="2026-05-10T18:00:00", reported_at="2026-05-10T22:00:00",
         hour=18, day_of_week=6,
         modus_operandi="minor did not return from school, last seen at Ulsoor bus stop, did not board usual bus, phone switched off",
         description="16-year-old Kavya Sharma did not return from St. Joseph's School. Last seen at Ulsoor bus stop at 6PM. Phone switched off. Parents filed FIR same evening.",
         status="Open", victim_count=1, accused_count=0,
         property_value_inr=None, weapon_used=None, source="demo-showcase"),
    dict(fir_number="DEMO-FIR-051", district="Bengaluru City",
         police_station="Shivajinagar PS", crime_type="Missing Person",
         crime_category="Vulnerable", severity=3,
         latitude=12.9779, longitude=77.5988,
         h3_r7="8760145b4ffffff", h3_r8="8860145b41fffff", h3_r9="8960145b403ffff",
         occurred_at="2026-04-15T08:00:00", reported_at="2026-04-15T20:00:00",
         hour=8, day_of_week=2,
         modus_operandi="elderly patient with dementia left care home, previously went missing twice in 2025, found near railway station both times",
         description="Elderly man (72) with dementia walked out of care home at 8AM. Third disappearance. Previously found near Shivajinagar railway station both times.",
         status="Traced", victim_count=1, accused_count=0,
         property_value_inr=None, weapon_used=None, source="demo-showcase"),
]
for c in missing_crimes:
    if not skip_if_exists(Crime, fir_number=c["fir_number"]):
        db.add(Crime(**c)); inserted["crimes"] += 1

missing_persons_records = [
    dict(mp_id="MP-DEMO-001", fir_number="DEMO-FIR-050",
         name="Kavya Sharma", age=16, gender="Female",
         last_seen_date="2026-05-10", last_seen_location="Ulsoor Bus Stop, Bengaluru",
         district="Bengaluru City", risk_tier="High", status="Open", repeat_count=0),
    dict(mp_id="MP-DEMO-002", fir_number="DEMO-FIR-051",
         name="Gopal Iyengar", age=72, gender="Male",
         last_seen_date="2026-04-15", last_seen_location="Shivajinagar Care Home, Bengaluru",
         district="Bengaluru City", risk_tier="Medium", status="Traced", repeat_count=2),
]
for m in missing_persons_records:
    if not skip_if_exists(MissingPerson, mp_id=m["mp_id"]):
        db.add(MissingPerson(**m)); inserted["missing"] += 1

# ════════════════════════════════════════════════════════════════════════════
# BLOCK 8 — GEOGRAPHIC PROFILING CLUSTER (for Geo Profile / Rossmo CGT)
#
# 6 serious crimes (dacoity/murder) spread across North Bengaluru.
# The Rossmo anchor point should land near Hebbal area.
# Crime type = "Dacoity" — filter by this in Geo Profile tab.
# ════════════════════════════════════════════════════════════════════════════
geo_crimes = [
    dict(fir_number="DEMO-FIR-060", district="Bengaluru City",
         police_station="Hebbal PS", crime_type="Dacoity",
         crime_category="Violent", severity=5,
         latitude=13.0468, longitude=77.5872,
         h3_r7="876014593ffffff", h3_r8="886014593bfffff", h3_r9="8960145933bffff",
         occurred_at="2025-08-12T23:00:00", reported_at="2025-08-13T07:00:00",
         hour=23, day_of_week=1,
         modus_operandi="gang of five attacked truck driver, cargo looted, driver tied up, truck abandoned",
         description="Truck carrying electronics looted on Bellary Road near Hebbal flyover. Driver tied and abandoned. Gang of five used two vehicles.",
         status="UnderInvestigation", victim_count=1, accused_count=5,
         property_value_inr=2200000, weapon_used="firearm", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-061", district="Bengaluru City",
         police_station="Yelahanka PS", crime_type="Dacoity",
         crime_category="Violent", severity=5,
         latitude=13.1007, longitude=77.5963,
         h3_r7="876014593ffffff", h3_r8="886014593bfffff", h3_r9="8960145933bffff",
         occurred_at="2025-09-03T02:00:00", reported_at="2025-09-03T06:30:00",
         hour=2, day_of_week=2,
         modus_operandi="petrol station robbed at gunpoint, safe broken, staff tied, CCTV disabled",
         description="Petrol bunk on Doddaballapur Road robbed at gunpoint. Rs 3.8L from safe. Four accused. CCTV disabled.",
         status="UnderInvestigation", victim_count=3, accused_count=4,
         property_value_inr=380000, weapon_used="firearm", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-062", district="Bengaluru City",
         police_station="Hebbal PS", crime_type="Dacoity",
         crime_category="Violent", severity=5,
         latitude=13.0312, longitude=77.5801,
         h3_r7="876014593ffffff", h3_r8="886014593bfffff", h3_r9="8960145933bffff",
         occurred_at="2025-10-18T01:30:00", reported_at="2025-10-18T05:00:00",
         hour=1, day_of_week=5,
         modus_operandi="residential villa dacoity, family tied, jewellery and cash looted, similar MO to prior incidents",
         description="Gated community villa dacoity. Family of four tied. Jewellery + Rs 5L cash. Same gang suspected as earlier incidents.",
         status="Open", victim_count=4, accused_count=5,
         property_value_inr=1400000, weapon_used="firearm", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-063", district="Bengaluru City",
         police_station="Bagalur PS", crime_type="Dacoity",
         crime_category="Violent", severity=5,
         latitude=13.1180, longitude=77.6452,
         h3_r7="876014593ffffff", h3_r8="886014593bfffff", h3_r9="8960145933bffff",
         occurred_at="2025-11-22T00:00:00", reported_at="2025-11-22T07:00:00",
         hour=0, day_of_week=5,
         modus_operandi="factory payroll robbery, armed gang intercepted cash van, driver and guard threatened",
         description="Payroll cash van intercepted near Bagalur industrial area. Rs 12L seized. Gang used modified getaway vehicle.",
         status="Open", victim_count=2, accused_count=6,
         property_value_inr=1200000, weapon_used="firearm", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-064", district="Bengaluru City",
         police_station="Hebbal PS", crime_type="Dacoity",
         crime_category="Violent", severity=5,
         latitude=13.0550, longitude=77.5650,
         h3_r7="876014593ffffff", h3_r8="886014593bfffff", h3_r9="8960145933bffff",
         occurred_at="2025-12-30T22:30:00", reported_at="2025-12-31T06:00:00",
         hour=22, day_of_week=1,
         modus_operandi="textile warehouse looted, night watchman assaulted, fabric worth 25 lakh taken",
         description="Textile warehouse near Hebbal lake area looted. Night watchman assaulted with blunt object. Rs 25L fabric stolen.",
         status="Open", victim_count=2, accused_count=4,
         property_value_inr=2500000, weapon_used="blunt object", source="demo-showcase"),
    dict(fir_number="DEMO-FIR-065", district="Bengaluru City",
         police_station="Yelahanka PS", crime_type="Dacoity",
         crime_category="Violent", severity=5,
         latitude=13.0880, longitude=77.5810,
         h3_r7="876014593ffffff", h3_r8="886014593bfffff", h3_r9="8960145933bffff",
         occurred_at="2026-01-15T01:00:00", reported_at="2026-01-15T05:30:00",
         hour=1, day_of_week=3,
         modus_operandi="supermarket looted after hours, safe cracked, CCTV disabled beforehand, systematic entry via roof",
         description="Supermarket systematically looted. Entry via roof. Safe cracked (Rs 8L). Professional gang. Similar to Hebbal series.",
         status="Open", victim_count=1, accused_count=5,
         property_value_inr=900000, weapon_used="firearm", source="demo-showcase"),
]
for c in geo_crimes:
    if not skip_if_exists(Crime, fir_number=c["fir_number"]):
        db.add(Crime(**c)); inserted["crimes"] += 1

# ════════════════════════════════════════════════════════════════════════════
# COMMIT ALL
# ════════════════════════════════════════════════════════════════════════════
db.commit()
db.close()

print("\nDRISHTI Demo Showcase Seeder complete")
print("-" * 48)
for k, v in inserted.items():
    print(f"  {k:14s}: {v} new records added")
print("-" * 48)
print("\nDemo personas:")
print("  Naik Crime Ring  -> Network: search 'Suresh Naik'")
print("                     CDR: search phone 9900001111")
print("                     Motif Detection -> Advanced tab")
print("  Arjun R. Sharma  -> Behavioral tab: search 'Arjun Sharma'")
print("                     Suspect tab: search 'Arjun'")
print("  Ravi Kumar       -> Investigations: Entity Resolution")
print("  Meera Iyer       -> Cyber: Money Flow, account ACC-DEMO-VICTIM")
print("  Koramangala      -> Hotspots, Near-Repeat, Forecast (Vehicle Theft)")
print("  Kavya Sharma     -> Missing Persons (High risk)")
print("  Dacoity cluster  -> Geo Profile tab: filter crime type = Dacoity")
print()
