import json, pathlib

base = pathlib.Path(r"C:\Users\Markus\source\pontos\testing")
fixtures = {
    "pontos": "pontos.json",
    "trio": "safetech.json",
    "safetech": "safetech.json",
    "safetech_v4": "safetech_v4.json",
    "neosoft": "neosoft.json",
}
candidates = (
    [f"getPA{i}" for i in range(1, 9)]
    + [f"getPW{i}" for i in range(1, 9)]
    + [
        "getSLP",
        "getSLV",
        "getSLT",
        "getSLF",
        "getSLO",
        "getSLE",
        "getSLD",
        "getWFC",
        "getWFL",
        "getWIP",
        "getWGW",
        "getEIP",
        "getEGW",
        "getMAC2",
        "getPRN",
        "getCNO",
        "getALM",
        "getLTV",
        "getFLO",
        "getDBT",
        "getRTC",
        "getTMZ",
        "getDST",
        "getBUZ",
        "getDMA",
        "getTMP",
        "getALA",
        "getVLV",
    ]
)

cache = {
    name: json.loads((base / f).read_text(encoding="utf-8"))
    for name, f in fixtures.items()
}

print(f"{'key':10s}" + "".join(f"{n:13s}" for n in fixtures))
for key in candidates:
    row = "".join(f"{'yes' if key in data else '-':13s}" for data in cache.values())
    if "yes" in row:
        print(f"{key:10s}{row}")
