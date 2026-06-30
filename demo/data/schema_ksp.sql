-- ============================================================================
-- DRISHTI — Official KSP "Police FIR System" schema (CCTNS-aligned)
-- Source of truth: Police_FIR_ER_Diagram.pdf  (Karnataka Police Department)
-- ----------------------------------------------------------------------------
-- This file implements the 24 official tables EXACTLY as named in the ER doc,
-- with the documented PK/FK relationships (see the Relationship Matrix, pp.7-9).
--
-- These tables are ADDITIVE: they live alongside DRISHTI's existing flat
-- analytics tables (crimes / persons / vehicles / accounts / transactions /
-- cdr / missing_persons / audit_log). The build script (build_ksp_schema.py)
-- populates them by ETL from the flat tables + generated reference data, so the
-- database is provably ER-compliant while the 16 live API endpoints stay
-- untouched. See SCHEMA_MAPPING.md for the field-by-field crosswalk.
--
-- Types follow SQLite affinity (INTEGER / TEXT / REAL / NUMERIC). The ER doc's
-- SQL-Server types (INT, VARCHAR, NVARCHAR(MAX), DATETIME, BIT, DECIMAL, CHAR)
-- are noted in comments next to each column for the production Postgres DDL.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. GEO / ORG HIERARCHY  (State -> District -> Unit ; Rank ; Designation ; Employee)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS State (
    StateID        INTEGER PRIMARY KEY,   -- INT
    StateName      TEXT,                  -- VARCHAR
    NationalityID  INTEGER,               -- INT
    Active         INTEGER DEFAULT 1      -- BIT
);

CREATE TABLE IF NOT EXISTS District (
    DistrictID     INTEGER PRIMARY KEY,   -- INT
    DistrictName   TEXT,                  -- VARCHAR
    StateID        INTEGER,               -- INT  FK -> State.StateID
    Active         INTEGER DEFAULT 1,     -- BIT
    FOREIGN KEY (StateID) REFERENCES State(StateID)
);

CREATE TABLE IF NOT EXISTS UnitType (
    UnitTypeID     INTEGER PRIMARY KEY,   -- INT
    UnitTypeName   TEXT,                  -- VARCHAR  (e.g. Police Station, Circle Office)
    CityDistState  TEXT,                  -- VARCHAR  (City / District / State)
    Hierarchy      INTEGER,               -- INT  (lower = higher authority)
    Active         INTEGER DEFAULT 1      -- BIT
);

CREATE TABLE IF NOT EXISTS Unit (
    UnitID         INTEGER PRIMARY KEY,   -- INT
    UnitName       TEXT,                  -- VARCHAR
    TypeID         INTEGER,               -- INT  FK -> UnitType.UnitTypeID
    ParentUnit     INTEGER,               -- INT  self-reference -> Unit.UnitID
    NationalityID  INTEGER,               -- INT
    StateID        INTEGER,               -- INT  FK -> State.StateID
    DistrictID     INTEGER,               -- INT  FK -> District.DistrictID
    Active         INTEGER DEFAULT 1,     -- BIT
    FOREIGN KEY (TypeID)     REFERENCES UnitType(UnitTypeID),
    FOREIGN KEY (StateID)    REFERENCES State(StateID),
    FOREIGN KEY (DistrictID) REFERENCES District(DistrictID),
    FOREIGN KEY (ParentUnit) REFERENCES Unit(UnitID)
);

CREATE TABLE IF NOT EXISTS Rank (
    RankID         INTEGER PRIMARY KEY,   -- INT
    RankName       TEXT,                  -- VARCHAR  (Constable, Inspector, DSP ...)
    Hierarchy      INTEGER,               -- INT  (lower = higher rank)
    Active         INTEGER DEFAULT 1      -- BIT
);

CREATE TABLE IF NOT EXISTS Designation (
    DesignationID    INTEGER PRIMARY KEY, -- INT
    DesignationName  TEXT,                -- VARCHAR  (Investigating Officer, SHO ...)
    Active           INTEGER DEFAULT 1,   -- BIT
    SortOrder        INTEGER              -- INT
);

CREATE TABLE IF NOT EXISTS Employee (
    EmployeeID          INTEGER PRIMARY KEY, -- INT
    DistrictID          INTEGER,             -- INT  FK -> District.DistrictID
    UnitID              INTEGER,             -- INT  FK -> Unit.UnitID
    RankID              INTEGER,             -- INT  FK -> Rank.RankID
    DesignationID       INTEGER,             -- INT  FK -> Designation.DesignationID
    KGID                TEXT,                -- VARCHAR  (Karnataka Govt ID)
    FirstName           TEXT,                -- VARCHAR
    EmployeeDOB         TEXT,                -- DATE
    GenderID            INTEGER,             -- INT  (lookup)
    BloodGroupID        INTEGER,             -- INT  (lookup)
    PhysicallyChallenged INTEGER DEFAULT 0,  -- BIT
    AppointmentDate     TEXT,                -- DATE
    FOREIGN KEY (DistrictID)    REFERENCES District(DistrictID),
    FOREIGN KEY (UnitID)        REFERENCES Unit(UnitID),
    FOREIGN KEY (RankID)        REFERENCES Rank(RankID),
    FOREIGN KEY (DesignationID) REFERENCES Designation(DesignationID)
);

-- ----------------------------------------------------------------------------
-- 2. COURT
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS Court (
    CourtID        INTEGER PRIMARY KEY,   -- INT
    CourtName      TEXT,                  -- VARCHAR
    DistrictID     INTEGER,               -- INT  FK -> District.DistrictID
    StateID        INTEGER,               -- INT  FK -> State.StateID
    Active         INTEGER DEFAULT 1,     -- BIT
    FOREIGN KEY (DistrictID) REFERENCES District(DistrictID),
    FOREIGN KEY (StateID)    REFERENCES State(StateID)
);

-- ----------------------------------------------------------------------------
-- 3. CASE-LEVEL LOOKUPS
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS CaseCategory (
    CaseCategoryID INTEGER PRIMARY KEY,   -- INT
    LookupValue    TEXT                   -- VARCHAR  (FIR, UDR, PAR, Zero FIR ...)
);

CREATE TABLE IF NOT EXISTS GravityOffence (
    GravityOffenceID INTEGER PRIMARY KEY, -- INT
    LookupValue      TEXT                 -- VARCHAR  (Heinous, Non-Heinous ...)
);

CREATE TABLE IF NOT EXISTS CaseStatusMaster (
    CaseStatusID   INTEGER PRIMARY KEY,   -- INT
    CaseStatusName TEXT                   -- VARCHAR  (Under Investigation, Charge Sheeted, Closed ...)
);

-- ----------------------------------------------------------------------------
-- 4. CRIME-HEAD CLASSIFICATION  (CrimeHead -> CrimeSubHead)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS CrimeHead (
    CrimeHeadID    INTEGER PRIMARY KEY,   -- INT  (major head)
    CrimeGroupName TEXT,                  -- VARCHAR  (e.g. Crimes Against Body)
    Active         INTEGER DEFAULT 1      -- BIT
);

CREATE TABLE IF NOT EXISTS CrimeSubHead (
    CrimeSubHeadID INTEGER PRIMARY KEY,   -- INT  (minor head)
    CrimeHeadID    INTEGER,               -- INT  FK -> CrimeHead.CrimeHeadID
    CrimeHeadName  TEXT,                  -- VARCHAR  (Murder, Robbery ...)
    SeqID          INTEGER,               -- INT
    FOREIGN KEY (CrimeHeadID) REFERENCES CrimeHead(CrimeHeadID)
);

-- ----------------------------------------------------------------------------
-- 5. LEGAL: Act / Section / CrimeHeadActSection
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS Act (
    ActCode        TEXT PRIMARY KEY,      -- VARCHAR  (IPC, NDPS, IT Act ...)
    ActDescription TEXT,                  -- VARCHAR
    ShortName      TEXT,                  -- VARCHAR
    Active         INTEGER DEFAULT 1      -- BIT
);

CREATE TABLE IF NOT EXISTS Section (
    SectionID          INTEGER PRIMARY KEY AUTOINCREMENT, -- surrogate (doc keys on SectionCode within Act)
    ActCode            TEXT,              -- VARCHAR  FK -> Act.ActCode
    SectionCode        TEXT,              -- VARCHAR  (302, 307, 420 ...)
    SectionDescription TEXT,              -- VARCHAR
    Active             INTEGER DEFAULT 1, -- BIT
    FOREIGN KEY (ActCode) REFERENCES Act(ActCode)
);

CREATE TABLE IF NOT EXISTS CrimeHeadActSection (
    CrimeHeadID    INTEGER,               -- INT  FK -> CrimeHead.CrimeHeadID
    ActCode        TEXT,                  -- VARCHAR  FK -> Act.ActCode
    SectionCode    TEXT,                  -- VARCHAR
    FOREIGN KEY (CrimeHeadID) REFERENCES CrimeHead(CrimeHeadID),
    FOREIGN KEY (ActCode)     REFERENCES Act(ActCode)
);

-- ----------------------------------------------------------------------------
-- 6. PERSON-ATTRIBUTE LOOKUPS  (complainant demographics)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS CasteMaster (
    caste_master_id   INTEGER PRIMARY KEY, -- INT
    caste_master_name TEXT                 -- VARCHAR
);

CREATE TABLE IF NOT EXISTS ReligionMaster (
    ReligionID   INTEGER PRIMARY KEY,     -- INT
    ReligionName TEXT                     -- VARCHAR  (Hindu, Muslim, Christian ...)
);

CREATE TABLE IF NOT EXISTS OccupationMaster (
    OccupationID   INTEGER PRIMARY KEY,   -- INT
    OccupationName TEXT                   -- VARCHAR  (Farmer, Government Employee ...)
);

-- ----------------------------------------------------------------------------
-- 7. CASEMASTER  (the FIR / case — the hub of the schema)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS CaseMaster (
    CaseMasterID       INTEGER PRIMARY KEY, -- INT
    CrimeNo            TEXT,                -- VARCHAR  (1+4+4+4+5 = 18-digit structured)
    CaseNo             TEXT,                -- VARCHAR  (YYYY + 5-digit serial)
    CrimeRegisteredDate TEXT,              -- DATE
    PolicePersonID     INTEGER,             -- INT  FK -> Employee.EmployeeID (registering officer)
    PoliceStationID    INTEGER,             -- INT  FK -> Unit.UnitID
    CaseCategoryID     INTEGER,             -- INT  FK -> CaseCategory.CaseCategoryID
    GravityOffenceID   INTEGER,             -- INT  FK -> GravityOffence.GravityOffenceID
    CrimeMajorHeadID   INTEGER,             -- INT  FK -> CrimeHead.CrimeHeadID
    CrimeMinorHeadID   INTEGER,             -- INT  FK -> CrimeSubHead.CrimeSubHeadID
    CaseStatusID       INTEGER,             -- INT  FK -> CaseStatusMaster.CaseStatusID
    CourtID            INTEGER,             -- INT  FK -> Court.CourtID
    IncidentFromDate   TEXT,                -- DATETIME
    IncidentToDate     TEXT,                -- DATETIME
    InfoReceivedPSDate TEXT,                -- DATETIME
    latitude           REAL,                -- DECIMAL
    longitude          REAL,                -- DECIMAL
    BriefFacts         TEXT,                -- NVARCHAR(MAX)
    FOREIGN KEY (PolicePersonID)  REFERENCES Employee(EmployeeID),
    FOREIGN KEY (PoliceStationID) REFERENCES Unit(UnitID),
    FOREIGN KEY (CaseCategoryID)  REFERENCES CaseCategory(CaseCategoryID),
    FOREIGN KEY (GravityOffenceID) REFERENCES GravityOffence(GravityOffenceID),
    FOREIGN KEY (CrimeMajorHeadID) REFERENCES CrimeHead(CrimeHeadID),
    FOREIGN KEY (CrimeMinorHeadID) REFERENCES CrimeSubHead(CrimeSubHeadID),
    FOREIGN KEY (CaseStatusID)    REFERENCES CaseStatusMaster(CaseStatusID),
    FOREIGN KEY (CourtID)         REFERENCES Court(CourtID)
);

-- ----------------------------------------------------------------------------
-- 8. CASE PARTIES & RELATED CHILD TABLES
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ComplainantDetails (
    ComplainantID  INTEGER PRIMARY KEY,   -- INT
    CaseMasterID   INTEGER,               -- INT  FK -> CaseMaster.CaseMasterID
    ComplainantName TEXT,                 -- VARCHAR
    AgeYear        INTEGER,               -- INT
    OccupationID   INTEGER,               -- INT  FK -> OccupationMaster.OccupationID
    ReligionID     INTEGER,               -- INT  FK -> ReligionMaster.ReligionID
    CasteID        INTEGER,               -- INT  FK -> CasteMaster.caste_master_id
    GenderID       INTEGER,               -- INT  (lookup)
    FOREIGN KEY (CaseMasterID) REFERENCES CaseMaster(CaseMasterID),
    FOREIGN KEY (OccupationID) REFERENCES OccupationMaster(OccupationID),
    FOREIGN KEY (ReligionID)   REFERENCES ReligionMaster(ReligionID),
    FOREIGN KEY (CasteID)      REFERENCES CasteMaster(caste_master_id)
);

CREATE TABLE IF NOT EXISTS Victim (
    VictimMasterID INTEGER PRIMARY KEY,   -- INT
    CaseMasterID   INTEGER,               -- INT  FK -> CaseMaster.CaseMasterID
    VictimName     TEXT,                  -- VARCHAR
    AgeYear        INTEGER,               -- INT
    GenderID       INTEGER,               -- INT  (m/f/t lookup)
    VictimPolice   TEXT,                  -- VARCHAR  (1 if victim is police else 0)
    FOREIGN KEY (CaseMasterID) REFERENCES CaseMaster(CaseMasterID)
);

CREATE TABLE IF NOT EXISTS Accused (
    AccusedMasterID INTEGER PRIMARY KEY,  -- INT
    CaseMasterID    INTEGER,              -- INT  FK -> CaseMaster.CaseMasterID
    AccusedName     TEXT,                 -- VARCHAR
    AgeYear         INTEGER,              -- INT
    GenderID        INTEGER,              -- INT  (M/F/T)
    PersonID        TEXT,                 -- VARCHAR  (sort key A1, A2, A3 ...)
    FOREIGN KEY (CaseMasterID) REFERENCES CaseMaster(CaseMasterID)
);

CREATE TABLE IF NOT EXISTS ArrestSurrender (
    ArrestSurrenderID       INTEGER PRIMARY KEY, -- INT
    CaseMasterID            INTEGER,             -- INT  FK -> CaseMaster.CaseMasterID
    ArrestSurrenderTypeID   INTEGER,             -- INT  (arrest / surrender lookup)
    ArrestSurrenderDate     TEXT,                -- DATE
    ArrestSurrenderStateId  INTEGER,             -- INT  FK -> State.StateID
    ArrestSurrenderDistrictId INTEGER,           -- INT  FK -> District.DistrictID
    PoliceStationID         INTEGER,             -- INT  FK -> Unit.UnitID
    IOID                    INTEGER,             -- INT  FK -> Employee.EmployeeID (Investigating Officer)
    CourtID                 INTEGER,             -- INT  FK -> Court.CourtID
    AccusedMasterID         INTEGER,             -- INT  FK -> Accused.AccusedMasterID
    IsAccused               INTEGER,             -- BIT
    IsComplainantAccused    INTEGER,             -- BIT
    FOREIGN KEY (CaseMasterID)             REFERENCES CaseMaster(CaseMasterID),
    FOREIGN KEY (ArrestSurrenderStateId)   REFERENCES State(StateID),
    FOREIGN KEY (ArrestSurrenderDistrictId) REFERENCES District(DistrictID),
    FOREIGN KEY (PoliceStationID)          REFERENCES Unit(UnitID),
    FOREIGN KEY (IOID)                     REFERENCES Employee(EmployeeID),
    FOREIGN KEY (CourtID)                  REFERENCES Court(CourtID),
    FOREIGN KEY (AccusedMasterID)          REFERENCES Accused(AccusedMasterID)
);

-- Junction: one arrest event <-> many accused (ER doc: inv_arrestsurrenderaccused)
CREATE TABLE IF NOT EXISTS inv_arrestsurrenderaccused (
    ArrestSurrenderID INTEGER,            -- INT  FK -> ArrestSurrender.ArrestSurrenderID
    AccusedMasterID   INTEGER,            -- INT  FK -> Accused.AccusedMasterID
    FOREIGN KEY (ArrestSurrenderID) REFERENCES ArrestSurrender(ArrestSurrenderID),
    FOREIGN KEY (AccusedMasterID)   REFERENCES Accused(AccusedMasterID)
);

CREATE TABLE IF NOT EXISTS ActSectionAssociation (
    CaseMasterID   INTEGER,               -- INT  FK -> CaseMaster.CaseMasterID
    ActID          TEXT,                  -- VARCHAR  FK -> Act.ActCode
    SectionID      TEXT,                  -- VARCHAR  FK -> Section.SectionCode
    ActOrderID     INTEGER,               -- INT
    SectionOrderID INTEGER,               -- INT
    FOREIGN KEY (CaseMasterID) REFERENCES CaseMaster(CaseMasterID),
    FOREIGN KEY (ActID)        REFERENCES Act(ActCode)
);

CREATE TABLE IF NOT EXISTS ChargesheetDetails (
    CSID           INTEGER PRIMARY KEY,   -- INT
    CaseMasterID   INTEGER,               -- INT  FK -> CaseMaster.CaseMasterID
    csdate         TEXT,                  -- DATETIME (chargesheeted date)
    cstype         TEXT,                  -- CHAR  (A=Chargesheet, B=False Case, C=Undetected)
    PolicePersonID INTEGER,               -- INT  FK -> Employee.EmployeeID
    FOREIGN KEY (CaseMasterID)   REFERENCES CaseMaster(CaseMasterID),
    FOREIGN KEY (PolicePersonID) REFERENCES Employee(EmployeeID)
);

-- Inv_OccuranceTime: one-to-one occurrence time/location record per FIR
-- (named in the Relationship Matrix; columns mirror the incident time/geo fields).
CREATE TABLE IF NOT EXISTS Inv_OccuranceTime (
    CaseMasterID     INTEGER PRIMARY KEY, -- INT  FK -> CaseMaster.CaseMasterID (1:1)
    IncidentFromDate TEXT,                -- DATETIME
    IncidentToDate   TEXT,                -- DATETIME
    latitude         REAL,                -- DECIMAL
    longitude        REAL,                -- DECIMAL
    FOREIGN KEY (CaseMasterID) REFERENCES CaseMaster(CaseMasterID)
);

-- ----------------------------------------------------------------------------
-- Helpful indexes (mirror the natural join keys)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_casemaster_crimeno     ON CaseMaster(CrimeNo);
CREATE INDEX IF NOT EXISTS ix_casemaster_station     ON CaseMaster(PoliceStationID);
CREATE INDEX IF NOT EXISTS ix_casemaster_majorhead   ON CaseMaster(CrimeMajorHeadID);
CREATE INDEX IF NOT EXISTS ix_complainant_case       ON ComplainantDetails(CaseMasterID);
CREATE INDEX IF NOT EXISTS ix_victim_case            ON Victim(CaseMasterID);
CREATE INDEX IF NOT EXISTS ix_accused_case           ON Accused(CaseMasterID);
CREATE INDEX IF NOT EXISTS ix_arrest_case            ON ArrestSurrender(CaseMasterID);
CREATE INDEX IF NOT EXISTS ix_actsection_case        ON ActSectionAssociation(CaseMasterID);
CREATE INDEX IF NOT EXISTS ix_section_act            ON Section(ActCode, SectionCode);
