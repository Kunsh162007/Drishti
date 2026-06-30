# DRISHTI ↔ KSP Official FIR Schema — Mapping Document

**Source of truth:** `Police_FIR_ER_Diagram.pdf` — *Police FIR System ER Diagram,
Karnataka Police Department* (the official CCTNS-aligned schema, 24 tables).

This document records exactly how DRISHTI's database aligns to that ER diagram.

---

## 1. Design decision — additive alignment (nothing breaks)

The official schema is implemented **additively**:

- `demo/data/schema_ksp.sql` creates the **24 official tables** with the exact
  names, primary keys, and foreign keys from the ER doc.
- `demo/scripts/build_ksp_schema.py` **seeds** the reference/lookup/org/legal
  tables and runs an **ETL** that maps DRISHTI's existing flat tables
  (`crimes`, `persons`) into the normalized tables.
- The flat tables (`crimes`, `persons`, `vehicles`, `accounts`, `transactions`,
  `cdr`, `missing_persons`, `audit_log`) are **left untouched**, so all 16 live
  API endpoints — including the ingest endpoint that *writes* to `crimes` — keep
  working with zero code changes.

> **Why not replace the flat tables with views?** The ingest endpoint executes
> `db.add(Crime(...))`, and SQLite views are read-only. Keeping the flat tables
> as the app's working store (and the normalized tables as the canonical,
> ER-compliant model populated from the same data) is the lowest-risk way to be
> *provably aligned to the document* without breaking the running demo. For the
> sovereign production build, the normalized tables become canonical and the
> flat shape is exposed as updatable Postgres views (`INSTEAD OF` triggers).

A verification view, **`v_fir_ksp_flat`**, reconstructs the app's flat FIR shape
*from* the normalized tables (joining `CaseMaster → Unit → District`,
`CrimeSubHead/CrimeHead`, `GravityOffence`, `CaseStatusMaster`, `Court`,
`Employee`), proving round-trip equivalence.

Build result (8,034 FIRs): **FK integrity ALL CLEAN**, `PRAGMA integrity_check =
ok`, `foreign_key_check = 0 violations`.

To (re)build — idempotent, drops & rebuilds only the KSP objects:

```bash
python demo/scripts/build_ksp_schema.py [path/to/drishti_demo.db]
```

---

## 2. Table-level mapping (flat → official ER)

| Flat source | Official ER table(s) | Notes |
|---|---|---|
| `crimes` (1 row = 1 FIR) | **CaseMaster** (+ **Inv_OccuranceTime** 1:1) | hub table; structured `CrimeNo` generated |
| `persons` where `role='Complainant'` | **ComplainantDetails** | `ComplainantID = persons.id` |
| `persons` where `role='Victim'` | **Victim** | `VictimMasterID = persons.id` |
| `persons` where `role='Accused'` | **Accused** | `AccusedMasterID = persons.id`; `PersonID` = A1, A2 … per case |
| `persons` where `role IN ('Suspect','Witness')` | *(no official table)* | retained only in flat `persons` — the ER schema has no Suspect/Witness entity |
| `crimes` (Charge-Sheeted) × accused | **ArrestSurrender** + **inv_arrestsurrenderaccused** | one arrest event per accused in charge-sheeted cases |
| `crimes` where `status='ChargeSheeted'` | **ChargesheetDetails** | `cstype='A'` (chargesheet) |
| `crimes.crime_type` → charge | **ActSectionAssociation** | one primary Act+Section per case (heuristic, see §4) |

### Reference / lookup / org tables (seeded, not from flat data)

| Official ER table | How it is populated |
|---|---|
| **State** | single row — Karnataka |
| **District** | distinct `crimes.district` (30) → stable IDs by sorted name |
| **Unit** (police station) | distinct `crimes.police_station` (356); district inferred from `crimes` |
| **UnitType** | seeded (Police Station, Circle Office, Sub-Division, District HQ) |
| **Rank** / **Designation** | seeded standard KSP values |
| **Employee** | synthesized 1 SHO + 2 IOs per station (1,068 officers) for `PolicePersonID` / `IOID` |
| **Court** | one District & Sessions Court per district |
| **CaseCategory** | FIR(1), UDR(3), PAR(4), Zero FIR(8) — PK = the 1-digit code embedded in `CrimeNo` |
| **GravityOffence** | Heinous / Non-Heinous (mapped from `crimes.severity`) |
| **CaseStatusMaster** | distinct `crimes.status` (5) |
| **CrimeHead** (major) | distinct `crimes.crime_category` (9) |
| **CrimeSubHead** (minor) | distinct `crimes.crime_type` (27), linked to its major head |
| **Act** / **Section** | seeded standard acts (IPC, IT Act, NDPS, POCSO, Excise, Arms, Dowry) + their sections |
| **CrimeHeadActSection** | each crime head → representative act/section |
| **CasteMaster** / **ReligionMaster** / **OccupationMaster** | seeded standard lists (FKs left **NULL** on complainants — see §3) |

---

## 3. Column-level mapping — CaseMaster (the FIR)

| `CaseMaster` column | Source / rule |
|---|---|
| `CaseMasterID` | `crimes.id` |
| `CrimeNo` | generated: `CaseCategoryCode(1)` + `DistrictID(4)` + `UnitID(4)` + `Year(4)` + `Serial(5)` = 18 digits, per the ER doc format; serial runs per (station, category, year) |
| `CaseNo` | `Year(4)` + `Serial(5)` (last 9 digits of `CrimeNo`) |
| `CrimeRegisteredDate` | `crimes.reported_at` (date) |
| `PolicePersonID` | SHO of the registering `Unit` (→ Employee) |
| `PoliceStationID` | `Unit.UnitID` for `crimes.police_station` |
| `CaseCategoryID` | `1` (all demo records are FIRs) |
| `GravityOffenceID` | `severity ≥ 4` → Heinous(1) else Non-Heinous(2) |
| `CrimeMajorHeadID` | `CrimeHead` for `crimes.crime_category` |
| `CrimeMinorHeadID` | `CrimeSubHead` for `crimes.crime_type` |
| `CaseStatusID` | `CaseStatusMaster` for `crimes.status` |
| `CourtID` | District & Sessions Court of the FIR's district |
| `IncidentFromDate` / `IncidentToDate` | `crimes.occurred_at` |
| `InfoReceivedPSDate` | `crimes.reported_at` |
| `latitude` / `longitude` | `crimes.latitude` / `crimes.longitude` |
| `BriefFacts` | `crimes.description` (fallback `modus_operandi`) |

### Party tables

| Column | Source |
|---|---|
| `ComplainantDetails.ComplainantName/AgeYear/GenderID` | `persons.full_name/age/gender` (gender → 1=M, 2=F, 3=T) |
| `ComplainantDetails.OccupationID/ReligionID/CasteID` | **NULL** — see §3 note |
| `Victim.VictimName/AgeYear/GenderID` | `persons.*`; `VictimPolice` = 0/1 |
| `Accused.AccusedName/AgeYear/GenderID/PersonID` | `persons.*`; `PersonID` = A1, A2 … by case order |

> **§3 note — zero-fabrication:** the flat `persons` table does not record
> caste / religion / occupation, so those complainant FKs are left **NULL**
> rather than invented. This is consistent with DRISHTI's "flag, never fabricate"
> policy. The lookup tables are still seeded so the columns are usable the moment
> real CCTNS data carries those fields.

---

## 4. Act/Section heuristic (ActSectionAssociation)

The flat data has no legal-section field, so a deterministic
`crime_type → (Act, Section)` map assigns the **primary** charge per case
(`ActOrderID = SectionOrderID = 1`). Examples:

| crime_type | Act | Section |
|---|---|---|
| Murder | IPC | 302 |
| Attempt to Murder | IPC | 307 |
| Vehicle Theft / Chain Snatching | IPC | 379 |
| Burglary / House Theft | IPC | 457 |
| Cheating / Fraud | IPC | 420 |
| Online Financial / UPI / Phishing-OTP Fraud | IT Act | 66D |
| Domestic Violence | IPC | 498A |
| Drug Possession (NDPS) | NDPS | 20 |
| POCSO | POCSO | 8 |
| Excise / Illicit Liquor | Excise | 32 |

`Missing Person` cases intentionally carry **no** act-section (registered as a
UDR-style record), which is why `ActSectionAssociation` = 7,839 = 8,034 − 195.

---

## 5. DRISHTI extension tables (NOT in the official ER doc)

These power DRISHTI's analytics modules and have **no equivalent** in the KSP
FIR schema. They are retained as documented extensions, keyed back to FIRs by
`fir_number`:

| Table | Purpose |
|---|---|
| `vehicles` | vehicle entities linked to FIRs (M2 network / entity resolution) |
| `accounts`, `transactions` | mule-account money-flow tracing (cyber module) |
| `cdr` | call-detail-record link analysis |
| `missing_persons` | missing-persons module |
| `audit_log` | hash-chained tamper-evident ledger |

When integrating with live CCTNS/ICJS, these become side-tables joined to
`CaseMaster.CaseMasterID` (replacing the demo's `fir_number` join key).
