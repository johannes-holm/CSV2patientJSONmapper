import tkinter as tk
from tkinter import filedialog
import csv
import json
import sys
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

#from  csv column to json value path
COLUMN_MAP = {
    "Exercise specific Case file number (ESCF #)": "identifier",
    "Patient Nationality": "description.nationality",
    "LoAC category":"description.LoAC",
    "EXCON Initial Triage Category": "triage_category",
    "Case Summary: Context, HPI": "description.scenario",
    "Status LOC : AVPU":"signs.AVPUScore",
    "Status Airway":"signs.AirwaysOpen",
    "CBRN Case": "Mechanisms.0",
    "CRESS: Eyes - Pupils": "signs.Pupils",
    "CRESS: Skin": "signs.Skin",
    "Initial  Vitals HR":"signs.PulseRate",
    "Initial Vitals BP": "BP",
    "Initial Vitals O2 Sat":"signs.Saturation%",
    "Initial Vitals Temperature": "signs.Temperature",
    "Initial Vitals GCS": "GCS"
}

#what values the json needs anyway
CONSTANT_FIELDS = {
"status": "inactive"
}

# Skip writing fields whose CSV value is empty/whitespace
SKIP_EMPTY_VALUES = True

Transform = Union[Callable[[Optional[str]], Any], Dict[str, Any]]

#Triage category transform-------------------------------------------------

def triage_to_number(val: Optional[str]) -> Optional[int]:
    if not val:
        return None
    m = re.search(r'^\s*[Tt]\s*([0-9]+)\s*[:(\s]', val)
    return int(m.group(1)) if m else None



#AVPU Score transform-------------------------------------------------------

def avpu_to_valid(avpuScore):
    avpuScore = avpuScore.upper()
    valid_scores = ['A', 'V', 'P', 'U']
    if avpuScore in valid_scores:
        return avpuScore
    else:
        return avpuScore[0]
    
#Airways transform------------------------------------------------------
def airways_to_valid(airwaysStatus):
    if airwaysStatus == "patent":
        return True
    else:
        return False
    
#cbrn to mechanisms------------------------------------------------------
def cbrn_to_mechanism(cbrnStatus):
    if cbrnStatus == "YES":
        return "CBRN"
    else:
        return 
    
#pupils transform------------------------------------------------------
def pupils_to_valid(pupils):
    pupils = pupils.lower()
    if pupils in ["n/a", "normal - perl"]:
        return "normal"
    else:
        return pupils
    

#skin transform------------------------------------------------------
def skin_to_valid(skin):
    skin = skin.lower()
    if skin == "n/a":
        return "normal"
    else:
        return skin
    
#pulserate transform------------------------------------------------------
def pulserate_to_valid(pulserate):
    pulserate = int(pulserate)
    return pulserate

#saturation transform------------------------------------------------------
def saturation_to_valid(saturation):
    saturation = int(saturation)
    return saturation

#temperature transform------------------------------------------------------
def temperature_to_valid(temperature):
    temperature = int(temperature)
    return temperature

#BP transform------------------------------------------------------
def split_bp(bp):
    if not bp:
        return None
    m = re.search(r'^\s*(\d+)\s*/\s*(\d+)\s*$', bp)
    if not m:
        return None
    systolic, diastolic = int(m.group(1)), int(m.group(2))
    return {"signs.SystolicBP": systolic, "signs.DiastolicBP": diastolic}

#GCS trasnform------------------------------------------------------
def split_gcs(gcs):
    gcs = gcs.replace("GCS ","").replace(".","")
    if not gcs:
        return None
    m = re.search(r'^\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*$', gcs)
    if not m:
        return None
    eye, verbal, motor = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return {"signs.eye_opening": eye, "signs.verbal_response": verbal, "signs.motor_response": motor}


    
TRANSFORMS: Dict[str, Transform] = {
    "EXCON Initial Triage Category": triage_to_number,
    "Status LOC : AVPU": avpu_to_valid,
    "Status Airway": airways_to_valid,
    "CBRN Case": cbrn_to_mechanism,
    "CRESS: Eyes - Pupils": pupils_to_valid,
    "CRESS: Skin": skin_to_valid,
    "Initial  Vitals HR": pulserate_to_valid,
    "Initial Vitals BP": split_bp,
    "Initial Vitals O2 Sat": saturation_to_valid,
    "Initial Vitals Temperature": temperature_to_valid,
    "Initial Vitals GCS": split_gcs
}
    

def set_deep(target: dict, path: str, value):
    parts = path.split(".")
    cur = target
    for key in parts[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    cur[parts[-1]] = value



OVERWRITE_CONSTANTS = False  # if False, constants won't be overwritten

def inject_constants(target: dict, constants: dict, overwrite: bool = True):
    for k, v in constants.items():
        # If not overwriting, only set when key is missing
        if not overwrite:
            # Walk to the parent if it's a dotted path
            parts = k.split(".")
            cur = target
            for key in parts[:-1]:
                if key not in cur or not isinstance(cur[key], dict):
                    cur[key] = {}
                cur = cur[key]
            cur.setdefault(parts[-1], v)
        else:
            set_deep(target, k, v)


def apply_transform(val: Optional[str], transform: Transform):
    if callable(transform):
        return transform(val)

    # Config dict mode
    t = transform
    ttype = t.get("type")
    if ttype == "regex":
        pattern = t["pattern"]
        flags = 0
        if str(t.get("flags", "")).lower() == "i":
            flags |= re.IGNORECASE
        m = re.search(pattern, val or "", flags)
        if not m:
            return None
        out = m.group(int(t.get("group", 1)))
        cast = str(t.get("cast", "str")).lower()
        if cast == "int":
            try:
                return int(out)
            except (ValueError, TypeError):
                return None
        elif cast == "float":
            try:
                return float(out)
            except (ValueError, TypeError):
                return None
        elif cast == "none":
            return None
        else:
            return out
    else:
        # Unknown config → return original
        return val



def main():

    root = tk.Tk()
    root.withdraw()

    # pick csv
    csv_path = filedialog.askopenfilename(
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
    )
    if not csv_path:
        print("No file selected. Exiting.")
        sys.exit(0)

    # read csv
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        if not reader.fieldnames:
            print("Couldn't detect headers. Make sure the CSV has a header row.")
            sys.exit(1)

        missing = [c for c in COLUMN_MAP.keys() if c not in reader.fieldnames]
        if missing:
            print("Warning: mapped columns not found in CSV:", missing)

        out = []
        for row in reader:
            obj = {}

            for csv_col, json_path in COLUMN_MAP.items():
                raw_val = row.get(csv_col, "")
                if isinstance(raw_val, str):
                    raw_val = raw_val.strip()

                transform = TRANSFORMS.get(csv_col)
                transformed = apply_transform(raw_val, transform) if transform else raw_val

                if transformed is None or (SKIP_EMPTY_VALUES and transformed == ""):
                    continue

                # 👇 NEW: if transform returns a dict, merge it directly
                if isinstance(transformed, dict):
                    for k, v in transformed.items():
                        set_deep(obj, k, v)
                else:
                    set_deep(obj, json_path, transformed)

                
            inject_constants(obj, CONSTANT_FIELDS, overwrite=OVERWRITE_CONSTANTS)   

            out.append(obj)

    # --- Save JSON ---
    default_name = Path(csv_path).with_suffix(".json").name
    print("\nChoose where to save the JSON output…")
    json_path = filedialog.asksaveasfilename(
        defaultextension=".json",
        initialfile=default_name,
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )
    if not json_path:
        print("No output selected. Exiting.")
        sys.exit(0)

    with open(json_path, "w", encoding="utf-8") as out_f:
        json.dump(out, out_f, ensure_ascii=False, indent=2)

    print(f"Completed. Wrote {len(out)} objects to: {json_path}")


if __name__ == "__main__":
    main()
