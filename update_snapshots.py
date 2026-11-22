#!/usr/bin/env python3
"""Fetch the latest weapon data from Krome's Google Sheet. If the sheet reports
a NEW version, make it the inlined LATEST in index.html, extend the VERSIONS
manifest, and save a copy under snapshots/. Also warns when no new version has
arrived for STALE_DAYS (stale-data detection). Prints 'changed=yes'/'no'.

Usage:
  * Local:   python update_snapshots.py          (updates files; push done separately)
  * Actions: run inside the gh-pages checkout with GITHUB_TOKEN set;
             the workflow then commits and pushes.
"""
import csv, datetime, io, json, os, re, urllib.request

SHEET_URL = ("https://docs.google.com/spreadsheets/d/1CAlLb9ebPWtXdsRKocSeIddDGa4xy5Hn3pzz4poGpD0"
             "/gviz/tq?tqx=out:csv&gid=276374354")


def parse_csv(text):
    rows, i, n = [], 0, len(text)
    while i < n:
        while i < n and text[i] in ("\r", "\n"):
            i += 1
        if i >= n:
            break
        row = []
        while True:
            if i < n and text[i] == '"':
                j, buf = i + 1, ""
                while True:
                    if j >= n:
                        break
                    c = text[j]
                    if c == '"':
                        if j + 1 < n and text[j + 1] == '"':
                            buf += '"'
                            j += 2
                        else:
                            j += 1
                            break
                    else:
                        buf += c
                        j += 1
                row.append(buf)
                i = j
                if i < n and text[i] == ",":
                    i += 1
            else:
                j = i
                while j < n and text[j] != "," and text[j] != "\n" and text[j] != "\r":
                    j += 1
                row.append(text[i:j])
                i = j
                if i >= n or text[i] in ("\r", "\n"):
                    break
                i += 1
        rows.append(row)
    return rows



def num(v):
    v = (v or "").strip()
    if v == "" or v == "-":
        return None
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


def parse_weapons(rows):
    out, cls = [], "light"
    for r in rows[1:]:
        c0 = (r[0] if len(r) > 0 else "").strip()
        if c0 == "MEDIUM":
            cls = "medium"; continue
        if c0 == "HEAVY":
            cls = "heavy"; continue
        if c0 == "LEGEND":
            break
        name = (r[1] if len(r) > 1 else "").strip()
        typ = (r[2] if len(r) > 2 else "").strip()
        if not name or typ in ("Primary Stats", "Special Stats"):
            continue
        out.append({
            "cls": cls, "name": name.lstrip("\u2b50"),
            "meta": name.startswith("\u2b50"), "type": typ,
            "firing_mode": (r[3] if len(r) > 3 else "").strip(),
            "dmg_body": num(r[4]), "dmg_head": num(r[5]), "dmg_env": num(r[6]),
            "rpm": num(r[7]), "mag": num(r[8]),
            "rt_tactical": num(r[9]), "rt_empty": num(r[10]),
            "dd_min": num(r[11]), "dd_max": num(r[12]), "dd_mod": num(r[13]),
            "burst_shots": num(r[14]), "burst_delay": num(r[15]),
            "dpm_body": num(r[16]), "dpm_head": num(r[17]),
            "dps_body": num(r[18]), "dps_head": num(r[19]),
            "ttk_b_light": num(r[20]), "stk_b_light": num(r[21]), "acc_b_light": num(r[22]),
            "ttk_h_light": num(r[23]), "stk_h_light": num(r[24]), "acc_h_light": num(r[25]),
            "ttk_b_med": num(r[26]), "stk_b_med": num(r[27]), "acc_b_med": num(r[28]),
            "ttk_h_med": num(r[29]), "stk_h_med": num(r[30]), "acc_h_med": num(r[31]),
            "ttk_b_heavy": num(r[32]), "stk_b_heavy": num(r[33]), "acc_b_heavy": num(r[34]),
            "ttk_h_heavy": num(r[35]), "stk_h_heavy": num(r[36]), "acc_h_heavy": num(r[37]),
            "last_update": (r[38] if len(r) > 38 else "").strip(),
            "status": (r[39] if len(r) > 39 else "").strip(),
            "notes": (r[40] if len(r) > 40 else "").strip(),
        })
    return out


STALE_DAYS = 30

def read_state(snap_dir):
    p = os.path.join(snap_dir, ".last_change.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def write_state(snap_dir, version, date):
    p = os.path.join(snap_dir, ".last_change.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"version": version, "date": date}, f)

def main():
    raw = urllib.request.urlopen(SHEET_URL, timeout=60).read().decode("utf-8")
    rows = parse_csv(raw)
    header = rows[0][0] if rows and rows[0] else ""
    m = re.search(r"ver\.\s*([\d.]+)", header)
    if not m:
        print("WARNING: could not parse a version from the sheet header - no update")
        print("changed=no")
        return
    ver = m.group(1)
    weapons = parse_weapons(rows)
    if not weapons:
        print("WARNING: parsed zero weapons - no update")
        print("changed=no")
        return

    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    html = open(html_path, encoding="utf-8").read()
    m_ver = re.search(r"const VERSIONS = (\[[^\]]*\]);", html, re.S)
    if not m_ver:
        print("ERROR: VERSIONS manifest not found in index.html")
        print("changed=no")
        return
    vers = json.loads(m_ver.group(1))
    changed = False
    if ver not in vers:
        # New version becomes the latest: extend the manifest and replace LATEST.
        html = html[:m_ver.start(1)] + json.dumps(vers + [ver]) + html[m_ver.end(1):]
        m_lat = re.search(r"const LATEST = (\[.*?\]);", html, re.S)
        if not m_lat:
            print("ERROR: LATEST block not found in index.html")
            print("changed=no")
            return
        html = html[:m_lat.start(1)] + json.dumps(weapons) + html[m_lat.end(1):]
        open(html_path, "w", encoding="utf-8").write(html)
        changed = True

    snap_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    with open(os.path.join(snap_dir, "ver-" + ver + ".json"), "w", encoding="utf-8") as f:
        json.dump(weapons, f)

    # Stale-data detection: record when we last saw a NEW version.
    today = datetime.date.today().isoformat()
    if changed:
        write_state(snap_dir, ver, today)
    else:
        state = read_state(snap_dir)
        last_date = state.get("date")
        if last_date:
            try:
                days = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(last_date)).days
                if days > STALE_DAYS:
                    print(f"STALE: no new version for {days} days (threshold {STALE_DAYS})")
            except Exception:
                pass

    print(f"version={ver} weapons={len(weapons)} changed={'yes' if changed else 'no'}")


if __name__ == "__main__":
    main()
