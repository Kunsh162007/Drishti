"""Shared reference data for the DRISHTI demo (Karnataka-specific)."""

KARNATAKA_DISTRICTS = [
    "Bengaluru City", "Bengaluru Rural", "Mysuru", "Mangaluru", "Hubballi-Dharwad",
    "Belagavi", "Kalaburagi", "Ballari", "Vijayapura", "Davanagere", "Shivamogga",
    "Tumakuru", "Raichur", "Bidar", "Hassan", "Udupi", "Chitradurga", "Kolar",
    "Mandya", "Chikkamagaluru", "Koppal", "Bagalkote", "Haveri", "Gadag",
    "Chamarajanagar", "Yadgir", "Ramanagara", "Chikkaballapura", "Dakshina Kannada", "Uttara Kannada",
]

# crime_type -> category
CRIME_TYPES = {
    "Burglary": "Property",
    "House Theft": "Property",
    "Vehicle Theft": "Property",
    "Chain Snatching": "Property",
    "Robbery": "Property",
    "Dacoity": "Property",
    "Cheating / Fraud": "Economic",
    "Online Financial Fraud": "Cybercrime",
    "Phishing / OTP Fraud": "Cybercrime",
    "Assault": "Violent",
    "Murder": "Violent",
    "Attempt to Murder": "Violent",
    "Rioting": "Violent",
    "Kidnapping": "Violent",
    "Domestic Violence": "Crime Against Women",
    "Dowry Harassment": "Crime Against Women",
    "Molestation": "Crime Against Women",
    "POCSO": "Crime Against Children",
    "Missing Person": "Missing",
    "Drug Possession (NDPS)": "Narcotics",
    "Excise / Illicit Liquor": "Narcotics",
}

CATEGORIES = sorted(set(CRIME_TYPES.values()))

STATUSES = ["Open", "UnderInvestigation", "ChargeSheeted", "Closed"]

CRIME_COLUMNS = [
    "fir_number", "district", "police_station", "crime_type", "crime_category", "severity",
    "latitude", "longitude", "h3_r7", "h3_r8", "h3_r9", "occurred_at", "reported_at",
    "hour", "day_of_week", "modus_operandi", "description", "status",
    "victim_count", "accused_count", "property_value_inr", "weapon_used", "source",
]
PERSON_COLUMNS = [
    "person_id", "fir_number", "full_name", "normalized_name", "role",
    "gender", "age", "phone", "address", "district", "true_identity_id",
]
VEHICLE_COLUMNS = ["vehicle_id", "fir_number", "reg_number", "vehicle_type", "make_color"]
