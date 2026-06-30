"""
build_ksp_schema.py — Align DRISHTI's database to the official KSP "Police FIR
System" ER schema (Police_FIR_ER_Diagram.pdf), ADDITIVELY.

What it does
------------
1.  Applies demo/data/schema_ksp.sql (the 24 official tables).
2.  Seeds the reference/lookup/org/legal tables (State -> District -> Unit,
    Employee, Court, CaseCategory, GravityOffence, CaseStatusMaster, CrimeHead,
    CrimeSubHead, Act, Section, CrimeHeadActSection, demographic lookups).
3.  ETL: maps the existing flat tables (crimes / persons) into the normalized
    CaseMaster + ComplainantDetails / Victim / Accused / ArrestSurrender /
    ChargesheetDetails / ActSectionAssociation / Inv_OccuranceTime tables.
4.  Builds verification VIEWS (v_fir_ksp_flat ...) that reconstruct the app's
    flat FIR shape FROM the normalized tables, proving round-trip equivalence.
5.  Prints a row-count + FK-integrity + sample-join report.

This is ADDITIVE: the flat tables (crimes/persons/vehicles/accounts/...) are
left untouched, so all 16 live API endpoints — including the ingest endpoint
that writes to `crimes` — keep working. Re-running is safe (idempotent): the
KSP tables are dropped and rebuilt each run.

Usage:  python demo/scripts/build_ksp_schema.py [path/to/drishti_demo.db]
"""
from __future__ import annotations
import sys, sqlite3, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # demo/
DEFAULT_DB = ROOT / "data" / "drishti_demo.db"
SCHEMA_SQL = ROOT / "data" / "schema_ksp.sql"

# Official KSP tables this script owns (dropped + rebuilt every run, child->parent order)
KSP_TABLES = [
    "Inv_OccuranceTime", "ChargesheetDetails", "ActSectionAssociation",
    "inv_arrestsurrenderaccused", "ArrestSurrender", "Accused", "Victim",
    "ComplainantDetails", "CaseMaster", "CrimeHeadActSection", "Section", "Act",
    "CrimeSubHead", "CrimeHead", "CaseStatusMaster", "GravityOffence",
    "CaseCategory", "Court", "Employee", "Designation", "Rank", "Unit",
    "UnitType", "District", "State", "OccupationMaster", "ReligionMaster",
    "CasteMaster",
]
KSP_VIEWS = ["v_fir_ksp_flat"]

GENDER = {"Male": 1, "Female": 2, "Trans": 3, "Transgender": 3, "M": 1, "F": 2, "T": 3}


def gid(g):
    return GENDER.get((g or "").strip(), None)


# crime_type -> (ActCode, SectionCode)  [primary charge; deterministic, no fabrication of facts]
TYPE_ACT_SECTION = {
    "Murder": ("IPC", "302"),
    "Attempt to Murder": ("IPC", "307"),
    "Assault": ("IPC", "351"),
    "Robbery": ("IPC", "392"),
    "Armed Robbery": ("IPC", "392"),
    "Robbery with Grievous Hurt": ("IPC", "394"),
    "Dacoity": ("IPC", "395"),
    "Burglary": ("IPC", "457"),
    "House Theft": ("IPC", "457"),
    "Vehicle Theft": ("IPC", "379"),
    "Petty Theft": ("IPC", "379"),
    "Chain Snatching": ("IPC", "379"),
    "Cheating / Fraud": ("IPC", "420"),
    "Investment Fraud": ("IPC", "420"),
    "Extortion": ("IPC", "384"),
    "Online Financial Fraud": ("IT_ACT", "66D"),
    "UPI Fraud": ("IT_ACT", "66D"),
    "Phishing / OTP Fraud": ("IT_ACT", "66D"),
    "Domestic Violence": ("IPC", "498A"),
    "Dowry Harassment": ("DOWRY", "4"),
    "Molestation": ("IPC", "354"),
    "POCSO": ("POCSO", "8"),
    "Kidnapping": ("IPC", "363"),
    "Drug Possession (NDPS)": ("NDPS", "20"),
    "Excise / Illicit Liquor": ("EXCISE", "32"),
    "Rioting": ("IPC", "147"),
    # "Missing Person" intentionally has no act-section (registered as UDR-style record).
}

ACTS = [
    ("IPC", "Indian Penal Code, 1860", "IPC"),
    ("IT_ACT", "Information Technology Act, 2000", "IT Act"),
    ("NDPS", "Narcotic Drugs and Psychotropic Substances Act, 1985", "NDPS"),
    ("POCSO", "Protection of Children from Sexual Offences Act, 2012", "POCSO"),
    ("EXCISE", "Karnataka Excise Act, 1965", "Excise Act"),
    ("ARMS", "Arms Act, 1959", "Arms Act"),
    ("DOWRY", "Dowry Prohibition Act, 1961", "Dowry Act"),
]
SECTION_DESC = {
    ("IPC", "302"): "Punishment for murder",
    ("IPC", "307"): "Attempt to murder",
    ("IPC", "351"): "Assault",
    ("IPC", "354"): "Assault on woman with intent to outrage modesty",
    ("IPC", "363"): "Punishment for kidnapping",
    ("IPC", "379"): "Punishment for theft",
    ("IPC", "384"): "Punishment for extortion",
    ("IPC", "392"): "Punishment for robbery",
    ("IPC", "394"): "Voluntarily causing hurt in committing robbery",
    ("IPC", "395"): "Punishment for dacoity",
    ("IPC", "420"): "Cheating and dishonestly inducing delivery of property",
    ("IPC", "457"): "Lurking house-trespass or house-breaking by night",
    ("IPC", "498A"): "Cruelty by husband or relatives",
    ("IPC", "147"): "Punishment for rioting",
    ("IT_ACT", "66D"): "Cheating by personation by using computer resource",
    ("NDPS", "20"): "Offences relating to cannabis",
    ("POCSO", "8"): "Punishment for sexual assault",
    ("EXCISE", "32"): "Possession of illicit liquor",
    ("DOWRY", "4"): "Penalty for demanding dowry",
}
# crime_category (CrimeHead) -> representative Act for CrimeHeadActSection
CATEGORY_ACT = {
    "Violent": "IPC", "Property": "IPC", "Cybercrime": "IT_ACT",
    "Economic": "IPC", "Crime Against Women": "IPC", "Narcotics": "NDPS",
    "Crime Against Children": "POCSO", "Missing": "IPC", "Vulnerable": "IPC",
}

RANKS = [  # (RankID, name, hierarchy)
    (1, "Director General of Police", 1), (2, "Superintendent of Police", 3),
    (3, "Deputy Superintendent of Police", 4), (4, "Police Inspector", 5),
    (5, "Police Sub-Inspector", 6), (6, "Assistant Sub-Inspector", 7),
    (7, "Head Constable", 8), (8, "Police Constable", 9),
]
DESIGNATIONS = [  # (DesignationID, name, sort)
    (1, "Station House Officer", 1), (2, "Investigating Officer", 2),
    (3, "Writer", 3), (4, "Beat Officer", 4),
]
CASTE = [(1, "General"), (2, "OBC"), (3, "SC"), (4, "ST"), (5, "Not Recorded")]
RELIGION = [(1, "Hindu"), (2, "Muslim"), (3, "Christian"), (4, "Jain"),
            (5, "Sikh"), (6, "Buddhist"), (7, "Other/Not Recorded")]
OCCUPATION = [(1, "Agriculture/Farmer"), (2, "Government Employee"),
              (3, "Private Employee"), (4, "Business/Self-Employed"),
              (5, "Student"), (6, "Homemaker"), (7, "Daily Wage"),
              (8, "Unemployed"), (9, "Not Recorded")]
# CaseCategory PK = the 1-digit Case Category Code embedded in CrimeNo (see ER doc)
CASE_CATEGORY = [(1, "FIR"), (3, "UDR"), (4, "PAR"), (8, "Zero FIR")]
GRAVITY = [(1, "Heinous"), (2, "Non-Heinous")]


def year_of(s, default=2025):
    try:
        return int(str(s)[:4])
    except Exception:
        return default


def main(db_path: Path):
    print(f"DB: {db_path}")
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = OFF")  # off during bulk load; integrity checked at end
    cur = con.cursor()

    # --- 0. clean rebuild of KSP objects ---
    for v in KSP_VIEWS:
        cur.execute(f"DROP VIEW IF EXISTS {v}")
    for t in KSP_TABLES:
        cur.execute(f"DROP TABLE IF EXISTS {t}")
    cur.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))

    # ============================================================ reference seeds
    cur.execute("INSERT INTO State VALUES (1,'Karnataka',1,1)")
    cur.executemany("INSERT INTO UnitType VALUES (?,?,?,?,1)",
                    [(1, "Police Station", "City/District", 5, ),
                     (2, "Circle Office", "District", 4),
                     (3, "Sub-Division", "District", 3),
                     (4, "District HQ", "District", 2)])
    cur.executemany("INSERT INTO Rank VALUES (?,?,?,1)", RANKS)
    cur.executemany("INSERT INTO Designation VALUES (?,?,1,?)", DESIGNATIONS)
    cur.executemany("INSERT INTO CasteMaster VALUES (?,?)", CASTE)
    cur.executemany("INSERT INTO ReligionMaster VALUES (?,?)", RELIGION)
    cur.executemany("INSERT INTO OccupationMaster VALUES (?,?)", OCCUPATION)
    cur.executemany("INSERT INTO CaseCategory VALUES (?,?)", CASE_CATEGORY)
    cur.executemany("INSERT INTO GravityOffence VALUES (?,?)", GRAVITY)

    # Districts (stable IDs by sorted name)
    districts = [r[0] for r in cur.execute(
        "SELECT DISTINCT district FROM crimes WHERE district IS NOT NULL ORDER BY district")]
    dist_id = {d: i for i, d in enumerate(districts, start=1)}
    cur.executemany("INSERT INTO District VALUES (?,?,1,1)",
                    [(i, d) for d, i in dist_id.items()])

    # Courts: one District & Sessions Court per district
    court_id = {d: 1000 + i for d, i in dist_id.items()}
    cur.executemany("INSERT INTO Court VALUES (?,?,?,1,1)",
                    [(court_id[d], f"District & Sessions Court, {d}", dist_id[d]) for d in districts])

    # Units (police stations) — district inferred from the crimes table
    ps_rows = cur.execute(
        "SELECT police_station, district, COUNT(*) FROM crimes "
        "WHERE police_station IS NOT NULL GROUP BY police_station, district").fetchall()
    unit_id, ps_district = {}, {}
    uid = 2000
    for ps, d, _ in ps_rows:
        if ps in unit_id:
            continue
        uid += 1
        unit_id[ps] = uid
        ps_district[ps] = d
    cur.executemany(
        "INSERT INTO Unit (UnitID,UnitName,TypeID,ParentUnit,NationalityID,StateID,DistrictID,Active) "
        "VALUES (?,?,1,NULL,1,1,?,1)",
        [(unit_id[ps], ps, dist_id.get(ps_district[ps])) for ps in unit_id])

    # Employees: 1 SHO + 2 IOs per station
    emp_rows, emp_by_unit = [], {}
    eid = 5000
    for ps, u in unit_id.items():
        d = dist_id.get(ps_district[ps])
        sho = eid + 1
        io1, io2 = eid + 2, eid + 3
        eid += 3
        emp_by_unit[u] = {"sho": sho, "ios": [io1, io2]}
        emp_rows += [
            (sho, d, u, 4, 1, f"KA{sho:06d}", f"SHO-{u}", "1980-01-01", 1, None, 0, "2010-06-01"),
            (io1, d, u, 5, 2, f"KA{io1:06d}", f"IO-{u}-A", "1988-01-01", 1, None, 0, "2014-06-01"),
            (io2, d, u, 5, 2, f"KA{io2:06d}", f"IO-{u}-B", "1990-01-01", 2, None, 0, "2016-06-01"),
        ]
    cur.executemany("INSERT INTO Employee (EmployeeID,DistrictID,UnitID,RankID,DesignationID,KGID,"
                    "FirstName,EmployeeDOB,GenderID,BloodGroupID,PhysicallyChallenged,AppointmentDate) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", emp_rows)

    # CaseStatusMaster (friendly names)
    status_name = {"ChargeSheeted": "Charge Sheeted", "Closed": "Closed", "Open": "Open",
                   "Traced": "Traced", "UnderInvestigation": "Under Investigation"}
    statuses = [r[0] for r in cur.execute(
        "SELECT DISTINCT status FROM crimes WHERE status IS NOT NULL ORDER BY status")]
    status_id = {s: i for i, s in enumerate(statuses, start=1)}
    cur.executemany("INSERT INTO CaseStatusMaster VALUES (?,?)",
                    [(i, status_name.get(s, s)) for s, i in status_id.items()])

    # CrimeHead (major) from crime_category; CrimeSubHead (minor) from crime_type
    cats = [r[0] for r in cur.execute(
        "SELECT DISTINCT crime_category FROM crimes WHERE crime_category IS NOT NULL ORDER BY crime_category")]
    head_id = {c: i for i, c in enumerate(cats, start=1)}
    cur.executemany("INSERT INTO CrimeHead VALUES (?,?,1)", [(i, c) for c, i in head_id.items()])

    type_cat = cur.execute(
        "SELECT crime_type, crime_category, COUNT(*) c FROM crimes "
        "WHERE crime_type IS NOT NULL GROUP BY crime_type, crime_category ORDER BY crime_type").fetchall()
    subhead_id, seen_type = {}, set()
    shid = 0
    for t, c, _ in type_cat:
        if t in seen_type:
            continue
        seen_type.add(t)
        shid += 1
        subhead_id[t] = shid
        cur.execute("INSERT INTO CrimeSubHead VALUES (?,?,?,?)", (shid, head_id.get(c), t, shid))

    # Act / Section / CrimeHeadActSection
    cur.executemany("INSERT INTO Act VALUES (?,?,?,1)", ACTS)
    for (act, sec), desc in SECTION_DESC.items():
        cur.execute("INSERT INTO Section (ActCode,SectionCode,SectionDescription,Active) VALUES (?,?,?,1)",
                    (act, sec, desc))
    for cat, hid in head_id.items():
        act = CATEGORY_ACT.get(cat, "IPC")
        # representative section for that act = the first section we have for it
        sec = next((s for (a, s) in SECTION_DESC if a == act), None)
        cur.execute("INSERT INTO CrimeHeadActSection VALUES (?,?,?)", (hid, act, sec))

    # ============================================================ core ETL
    crimes = cur.execute(
        "SELECT id, fir_number, district, police_station, crime_type, crime_category, severity, "
        "latitude, longitude, occurred_at, reported_at, status, description, modus_operandi, "
        "victim_count, accused_count FROM crimes").fetchall()

    fir_to_case = {}            # fir_number -> CaseMasterID
    serial = {}                 # (UnitID, CaseCategoryID, year) -> running serial
    case_rows, occ_rows = [], []
    case_meta = {}              # CaseMasterID -> (UnitID, DistrictID, status, reported_at)

    for (cid, fir, district, ps, ctype, cat, sev, lat, lng, occ, rep, status,
         desc, mo, vc, ac) in crimes:
        fir_to_case[fir] = cid
        u = unit_id.get(ps)
        d = dist_id.get(district)
        cc = 1                                            # all demo records are FIRs
        yr = year_of(rep or occ)
        key = (u, cc, yr)
        serial[key] = serial.get(key, 0) + 1
        sn = serial[key]
        crime_no = f"{cc:1d}{(d or 0):04d}{(u or 0) % 10000:04d}{yr:04d}{sn:05d}"
        case_no = f"{yr:04d}{sn:05d}"
        gravity = 1 if (sev or 0) >= 4 else 2
        officer = (emp_by_unit.get(u) or {}).get("sho")
        case_rows.append((
            cid, crime_no, case_no, (rep or occ or "")[:10], officer, u, cc, gravity,
            head_id.get(cat), subhead_id.get(ctype), status_id.get(status), court_id.get(district),
            occ, occ, rep, lat, lng, (desc or mo)))
        occ_rows.append((cid, occ, occ, lat, lng))
        case_meta[cid] = (u, d, status, rep)

    cur.executemany(
        "INSERT INTO CaseMaster (CaseMasterID,CrimeNo,CaseNo,CrimeRegisteredDate,PolicePersonID,"
        "PoliceStationID,CaseCategoryID,GravityOffenceID,CrimeMajorHeadID,CrimeMinorHeadID,"
        "CaseStatusID,CourtID,IncidentFromDate,IncidentToDate,InfoReceivedPSDate,latitude,longitude,"
        "BriefFacts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", case_rows)
    cur.executemany("INSERT INTO Inv_OccuranceTime VALUES (?,?,?,?,?)", occ_rows)

    # ActSectionAssociation: one primary charge per case (by crime_type)
    asa = []
    for cid, fir, district, ps, ctype, cat, *_ in crimes:
        hit = TYPE_ACT_SECTION.get(ctype)
        if hit:
            asa.append((cid, hit[0], hit[1], 1, 1))
    cur.executemany("INSERT INTO ActSectionAssociation VALUES (?,?,?,?,?)", asa)

    # Parties: persons -> ComplainantDetails / Victim / Accused
    persons = cur.execute(
        "SELECT id, fir_number, full_name, role, gender, age FROM persons").fetchall()
    comp, vic, acc = [], [], []
    acc_seq = {}                # CaseMasterID -> running A-number
    accused_by_case = {}        # CaseMasterID -> [AccusedMasterID]
    for pid, fir, name, role, gender, age in persons:
        cid = fir_to_case.get(fir)
        if cid is None:
            continue
        r = (role or "").strip().lower()
        if r == "complainant":
            comp.append((pid, cid, name, age, None, None, None, gid(gender)))
        elif r == "victim":
            vp = "1" if (name or "").lower().startswith("police") else "0"
            vic.append((pid, cid, name, age, gid(gender), vp))
        elif r == "accused":
            acc_seq[cid] = acc_seq.get(cid, 0) + 1
            acc.append((pid, cid, name, age, gid(gender), f"A{acc_seq[cid]}"))
            accused_by_case.setdefault(cid, []).append(pid)
        # 'Suspect' / 'Witness' have no table in the official ER schema -> kept only in flat `persons`

    cur.executemany("INSERT INTO ComplainantDetails (ComplainantID,CaseMasterID,ComplainantName,"
                    "AgeYear,OccupationID,ReligionID,CasteID,GenderID) VALUES (?,?,?,?,?,?,?,?)", comp)
    cur.executemany("INSERT INTO Victim VALUES (?,?,?,?,?,?)", vic)
    cur.executemany("INSERT INTO Accused VALUES (?,?,?,?,?,?)", acc)

    # ArrestSurrender + junction + ChargesheetDetails for Charge-Sheeted cases
    arr, junc, cs = [], [], []
    arr_id, cs_id = 0, 0
    for cid, (u, d, status, rep) in case_meta.items():
        if status != "ChargeSheeted":
            continue
        io = ((emp_by_unit.get(u) or {}).get("ios") or [None])[0]
        court = None
        # CourtID for the case (reuse CaseMaster.CourtID via court_id lookup by district name)
        dname = next((dn for dn, di in dist_id.items() if di == d), None)
        court = court_id.get(dname)
        arr_date = (rep or "")[:10]
        for am in accused_by_case.get(cid, []):
            arr_id += 1
            arr.append((arr_id, cid, 1, arr_date, 1, d, u, io, court, am, 1, 0))
            junc.append((arr_id, am))
        cs_id += 1
        cs.append((cs_id, cid, rep, "A", io))
    cur.executemany("INSERT INTO ArrestSurrender VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", arr)
    cur.executemany("INSERT INTO inv_arrestsurrenderaccused VALUES (?,?)", junc)
    cur.executemany("INSERT INTO ChargesheetDetails VALUES (?,?,?,?,?)", cs)

    # ============================================================ verification view
    # Reconstructs the app's flat FIR shape FROM the normalized tables (district
    # resolved via Unit.DistrictID), proving round-trip equivalence.
    cur.execute("""
        CREATE VIEW v_fir_ksp_flat AS
        SELECT cm.CaseMasterID            AS id,
               cm.CrimeNo                 AS crime_no,
               cm.CaseNo                  AS case_no,
               d.DistrictName             AS district,
               u.UnitName                 AS police_station,
               sh.CrimeHeadName           AS crime_type,
               ch.CrimeGroupName          AS crime_category,
               go.LookupValue             AS gravity,
               st.CaseStatusName          AS status,
               cm.IncidentFromDate        AS occurred_at,
               cm.CrimeRegisteredDate     AS registered_at,
               cm.latitude, cm.longitude,
               co.CourtName               AS court,
               e.FirstName                AS registering_officer
        FROM CaseMaster cm
        LEFT JOIN Unit u             ON u.UnitID = cm.PoliceStationID
        LEFT JOIN District d         ON d.DistrictID = u.DistrictID
        LEFT JOIN CrimeSubHead sh    ON sh.CrimeSubHeadID = cm.CrimeMinorHeadID
        LEFT JOIN CrimeHead ch       ON ch.CrimeHeadID = cm.CrimeMajorHeadID
        LEFT JOIN GravityOffence go  ON go.GravityOffenceID = cm.GravityOffenceID
        LEFT JOIN CaseStatusMaster st ON st.CaseStatusID = cm.CaseStatusID
        LEFT JOIN Court co           ON co.CourtID = cm.CourtID
        LEFT JOIN Employee e         ON e.EmployeeID = cm.PolicePersonID
    """)

    con.commit()
    report(con)
    con.close()


def report(con):
    cur = con.cursor()
    print("\n=== KSP table row counts ===")
    for t in reversed(KSP_TABLES):
        try:
            n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t:<28} {n:>8,}")
        except Exception as e:
            print(f"  {t:<28} ERROR {e}")

    print("\n=== FK integrity checks (orphans should be 0) ===")
    checks = [
        ("CaseMaster.PoliceStationID -> Unit",
         "SELECT COUNT(*) FROM CaseMaster c LEFT JOIN Unit u ON u.UnitID=c.PoliceStationID WHERE c.PoliceStationID IS NOT NULL AND u.UnitID IS NULL"),
        ("CaseMaster.CrimeMajorHeadID -> CrimeHead",
         "SELECT COUNT(*) FROM CaseMaster c LEFT JOIN CrimeHead h ON h.CrimeHeadID=c.CrimeMajorHeadID WHERE c.CrimeMajorHeadID IS NOT NULL AND h.CrimeHeadID IS NULL"),
        ("CaseMaster.CrimeMinorHeadID -> CrimeSubHead",
         "SELECT COUNT(*) FROM CaseMaster c LEFT JOIN CrimeSubHead s ON s.CrimeSubHeadID=c.CrimeMinorHeadID WHERE c.CrimeMinorHeadID IS NOT NULL AND s.CrimeSubHeadID IS NULL"),
        ("CaseMaster.PolicePersonID -> Employee",
         "SELECT COUNT(*) FROM CaseMaster c LEFT JOIN Employee e ON e.EmployeeID=c.PolicePersonID WHERE c.PolicePersonID IS NOT NULL AND e.EmployeeID IS NULL"),
        ("ComplainantDetails.CaseMasterID -> CaseMaster",
         "SELECT COUNT(*) FROM ComplainantDetails x LEFT JOIN CaseMaster c ON c.CaseMasterID=x.CaseMasterID WHERE c.CaseMasterID IS NULL"),
        ("Victim.CaseMasterID -> CaseMaster",
         "SELECT COUNT(*) FROM Victim x LEFT JOIN CaseMaster c ON c.CaseMasterID=x.CaseMasterID WHERE c.CaseMasterID IS NULL"),
        ("Accused.CaseMasterID -> CaseMaster",
         "SELECT COUNT(*) FROM Accused x LEFT JOIN CaseMaster c ON c.CaseMasterID=x.CaseMasterID WHERE c.CaseMasterID IS NULL"),
        ("ArrestSurrender.AccusedMasterID -> Accused",
         "SELECT COUNT(*) FROM ArrestSurrender a LEFT JOIN Accused x ON x.AccusedMasterID=a.AccusedMasterID WHERE a.AccusedMasterID IS NOT NULL AND x.AccusedMasterID IS NULL"),
        ("ActSectionAssociation.ActID -> Act",
         "SELECT COUNT(*) FROM ActSectionAssociation a LEFT JOIN Act k ON k.ActCode=a.ActID WHERE a.ActID IS NOT NULL AND k.ActCode IS NULL"),
        ("Unit.DistrictID -> District",
         "SELECT COUNT(*) FROM Unit u LEFT JOIN District d ON d.DistrictID=u.DistrictID WHERE u.DistrictID IS NOT NULL AND d.DistrictID IS NULL"),
    ]
    ok = True
    for label, sql in checks:
        n = cur.execute(sql).fetchone()[0]
        flag = "OK" if n == 0 else "!! ORPHANS"
        if n: ok = False
        print(f"  [{flag}] {label}: {n}")
    print(f"\nFK integrity: {'ALL CLEAN' if ok else 'PROBLEMS FOUND'}")

    print("\n=== sample reconstructed FIR (from normalized tables, via v_fir_ksp_flat) ===")
    row = cur.execute("SELECT id,crime_no,district,police_station,crime_type,crime_category,"
                      "gravity,status,registering_officer FROM v_fir_ksp_flat LIMIT 1").fetchone()
    print("  ", row)
    cid = row[0]
    print("   complainants:", cur.execute("SELECT ComplainantName,AgeYear,GenderID FROM ComplainantDetails WHERE CaseMasterID=?", (cid,)).fetchall())
    print("   victims:     ", cur.execute("SELECT VictimName,AgeYear FROM Victim WHERE CaseMasterID=?", (cid,)).fetchall())
    print("   accused:     ", cur.execute("SELECT AccusedName,PersonID FROM Accused WHERE CaseMasterID=?", (cid,)).fetchall())
    print("   act-sections:", cur.execute("SELECT ActID,SectionID FROM ActSectionAssociation WHERE CaseMasterID=?", (cid,)).fetchall())

    print("\n=== flat tables still intact (app unaffected) ===")
    for t in ("crimes", "persons", "vehicles", "accounts", "transactions", "cdr", "missing_persons", "audit_log"):
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<16} {n:>8,}")


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    main(db)
