"""
Generate PIN codes for all ISA Member States and write to data/member_states.json.
Also prints a CSV for distribution by the ISA Secretariat.

Usage:
    python3 scripts/generate_pins.py           # generate fresh PINs (overwrites existing)
    python3 scripts/generate_pins.py --print   # just print CSV of existing PINs (plaintext)
    python3 scripts/generate_pins.py --reset GERMANY  # reset one state's PIN
"""

import csv
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
OUT_FILE = DATA_DIR / "member_states.json"

# ── All 169 ISA Member States (as of 2025) ────────────────────────────────────
# Source: https://www.isa.org.jm/members/
MEMBER_STATES = [
    ("Albania", "ALB"), ("Algeria", "DZA"), ("Angola", "AGO"),
    ("Antigua and Barbuda", "ATG"), ("Argentina", "ARG"), ("Armenia", "ARM"),
    ("Australia", "AUS"), ("Austria", "AUT"), ("Bahamas", "BHS"),
    ("Bahrain", "BHR"), ("Bangladesh", "BGD"), ("Barbados", "BRB"),
    ("Belarus", "BLR"), ("Belgium", "BEL"), ("Belize", "BLZ"),
    ("Benin", "BEN"), ("Bolivia (Plurinational State of)", "BOL"),
    ("Bosnia and Herzegovina", "BIH"), ("Botswana", "BWA"), ("Brazil", "BRA"),
    ("Brunei Darussalam", "BRN"), ("Bulgaria", "BGR"), ("Cabo Verde", "CPV"),
    ("Cambodia", "KHM"), ("Cameroon", "CMR"), ("Canada", "CAN"),
    ("Chile", "CHL"), ("China", "CHN"), ("Colombia", "COL"),
    ("Comoros", "COM"), ("Congo", "COG"), ("Cook Islands", "COK"),
    ("Costa Rica", "CRI"), ("Côte d'Ivoire", "CIV"), ("Croatia", "HRV"),
    ("Cuba", "CUB"), ("Cyprus", "CYP"), ("Czechia", "CZE"),
    ("Democratic People's Republic of Korea", "PRK"),
    ("Democratic Republic of the Congo", "COD"),
    ("Denmark", "DNK"), ("Djibouti", "DJI"), ("Dominica", "DMA"),
    ("Dominican Republic", "DOM"), ("Ecuador", "ECU"), ("Egypt", "EGY"),
    ("El Salvador", "SLV"), ("Equatorial Guinea", "GNQ"), ("Eritrea", "ERI"),
    ("Estonia", "EST"), ("Eswatini", "SWZ"), ("Ethiopia", "ETH"),
    ("European Union", "EU0"), ("Fiji", "FJI"), ("Finland", "FIN"),
    ("France", "FRA"), ("Gabon", "GAB"), ("Gambia", "GMB"), ("Georgia", "GEO"),
    ("Germany", "DEU"), ("Ghana", "GHA"), ("Greece", "GRC"),
    ("Grenada", "GRD"), ("Guatemala", "GTM"), ("Guinea", "GIN"),
    ("Guinea-Bissau", "GNB"), ("Guyana", "GUY"), ("Haiti", "HTI"),
    ("Honduras", "HND"), ("Hungary", "HUN"), ("Iceland", "ISL"),
    ("India", "IND"), ("Indonesia", "IDN"), ("Iran (Islamic Republic of)", "IRN"),
    ("Iraq", "IRQ"), ("Ireland", "IRL"), ("Italy", "ITA"), ("Jamaica", "JAM"),
    ("Japan", "JPN"), ("Jordan", "JOR"), ("Kenya", "KEN"), ("Kiribati", "KIR"),
    ("Kuwait", "KWT"), ("Lao People's Democratic Republic", "LAO"),
    ("Latvia", "LVA"), ("Lebanon", "LBN"), ("Lesotho", "LSO"),
    ("Liberia", "LBR"), ("Libya", "LBY"), ("Lithuania", "LTU"),
    ("Luxembourg", "LUX"), ("Madagascar", "MDG"), ("Malawi", "MWI"),
    ("Malaysia", "MYS"), ("Maldives", "MDV"), ("Mali", "MLI"),
    ("Malta", "MLT"), ("Marshall Islands", "MHL"), ("Mauritania", "MRT"),
    ("Mauritius", "MUS"), ("Mexico", "MEX"),
    ("Micronesia (Federated States of)", "FSM"), ("Monaco", "MCO"),
    ("Mongolia", "MNG"), ("Montenegro", "MNE"), ("Morocco", "MAR"),
    ("Mozambique", "MOZ"), ("Myanmar", "MMR"), ("Namibia", "NAM"),
    ("Nauru", "NRU"), ("Nepal", "NPL"), ("Netherlands", "NLD"),
    ("New Zealand", "NZL"), ("Nicaragua", "NIC"), ("Niger", "NER"),
    ("Nigeria", "NGA"), ("Niue", "NIU"), ("Norway", "NOR"), ("Oman", "OMN"),
    ("Pakistan", "PAK"), ("Palau", "PLW"), ("Palestine", "PSE"),
    ("Panama", "PAN"), ("Papua New Guinea", "PNG"), ("Paraguay", "PRY"),
    ("Peru", "PER"), ("Philippines", "PHL"), ("Poland", "POL"),
    ("Portugal", "PRT"), ("Qatar", "QAT"), ("Republic of Korea", "KOR"),
    ("Republic of Moldova", "MDA"), ("Romania", "ROU"),
    ("Russian Federation", "RUS"), ("Saint Kitts and Nevis", "KNA"),
    ("Saint Lucia", "LCA"), ("Saint Vincent and the Grenadines", "VCT"),
    ("Samoa", "WSM"), ("Sao Tome and Principe", "STP"), ("Saudi Arabia", "SAU"),
    ("Senegal", "SEN"), ("Serbia", "SRB"), ("Seychelles", "SYC"),
    ("Sierra Leone", "SLE"), ("Singapore", "SGP"), ("Slovakia", "SVK"),
    ("Slovenia", "SVN"), ("Solomon Islands", "SLB"), ("Somalia", "SOM"),
    ("South Africa", "ZAF"), ("Spain", "ESP"), ("Sri Lanka", "LKA"),
    ("Sudan", "SDN"), ("Suriname", "SUR"), ("Sweden", "SWE"),
    ("Switzerland", "CHE"), ("Tanzania (United Republic of)", "TZA"),
    ("Thailand", "THA"), ("Timor-Leste", "TLS"), ("Togo", "TGO"),
    ("Tonga", "TON"), ("Trinidad and Tobago", "TTO"), ("Tunisia", "TUN"),
    ("Tuvalu", "TUV"), ("Uganda", "UGA"), ("Ukraine", "UKR"),
    ("United Arab Emirates", "ARE"), ("United Kingdom", "GBR"),
    ("United States of America", "USA"), ("Uruguay", "URY"), ("Vanuatu", "VUT"),
    ("Venezuela (Bolivarian Republic of)", "VEN"), ("Viet Nam", "VNM"),
    ("Yemen", "YEM"), ("Zambia", "ZMB"), ("Zimbabwe", "ZWE"),
]

# ISA Secretariat admin account
ADMIN = ("ISA Secretariat", "ISA", True)


def make_pin() -> str:
    """Generate a random 6-digit PIN."""
    return f"{random.randint(100000, 999999)}"


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def generate_all() -> list[dict]:
    states = []
    # Admin first
    name, code, is_admin = ADMIN
    pin = make_pin()
    states.append({
        "name":     name,
        "code":     code,
        "is_admin": True,
        "pin_hash": hash_pin(pin),
        "_pin_plaintext": pin,   # REMOVE before sharing
    })

    for name, code in MEMBER_STATES:
        pin = make_pin()
        states.append({
            "name":     name,
            "code":     code,
            "is_admin": False,
            "pin_hash": hash_pin(pin),
            "_pin_plaintext": pin,
        })

    return states


def save(states: list[dict]):
    # Save with plaintext PINs for initial distribution; secretariat should
    # delete _pin_plaintext fields after noting them down
    OUT_FILE.write_text(json.dumps(states, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(states)} states to {OUT_FILE.name}")


def print_csv(states: list[dict]):
    writer = csv.writer(sys.stdout)
    writer.writerow(["State", "Code", "PIN"])
    for s in states:
        pin = s.get("_pin_plaintext", "(hidden)")
        writer.writerow([s["name"], s["code"], pin])


def main():
    args = sys.argv[1:]

    if "--print" in args:
        if not OUT_FILE.exists():
            print("ERROR: member_states.json not found. Run without --print first.")
            sys.exit(1)
        states = json.loads(OUT_FILE.read_text())
        print_csv(states)
        return

    if "--reset" in args:
        idx = args.index("--reset")
        target = args[idx + 1].upper() if idx + 1 < len(args) else ""
        if not OUT_FILE.exists():
            print("ERROR: member_states.json not found.")
            sys.exit(1)
        states = json.loads(OUT_FILE.read_text())
        for s in states:
            if s["code"].upper() == target or s["name"].upper() == target:
                pin = make_pin()
                s["pin_hash"] = hash_pin(pin)
                s["_pin_plaintext"] = pin
                print(f"Reset PIN for {s['name']}: {pin}")
                save(states)
                return
        print(f"State '{target}' not found.")
        sys.exit(1)

    # Default: generate fresh PINs
    if OUT_FILE.exists():
        print(f"WARNING: {OUT_FILE.name} already exists. Overwriting with fresh PINs.")
    states = generate_all()
    save(states)
    print("\nCSV for distribution:")
    print_csv(states)
    print(f"\nNOTE: _pin_plaintext fields are included for initial distribution.")
    print("Delete them from member_states.json once you've noted the PINs.")


if __name__ == "__main__":
    main()
