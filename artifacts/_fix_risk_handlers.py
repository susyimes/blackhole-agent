"""Fix risk outcome handlers: remove from solvency set, use grouped handler."""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "blackhole_agent" / "capability_compounder.py"


def main() -> None:
    text = SRC.read_text(encoding="utf-8")

    # Remove risk kinds wrongly injected into solvency set
    bad = '''        "solvency_root_valid",
        "risk_ok",
        "risked_ok",
        "min_risks",
        "risk_root_valid",
    }:
        plane = (
            context.get("solvency")'''
    good = '''        "solvency_root_valid",
    }:
        plane = (
            context.get("solvency")'''
    if bad in text:
        text = text.replace(bad, good, 1)
        print("removed risk kinds from solvency set")
    else:
        print("solvency set already clean or different shape")

    # Replace the flat risk handlers with a solvency-style grouped block
    old_handler_start = '    if kind == "risk_ok":\n        plane = context.get("risk")'
    if old_handler_start not in text:
        # maybe already fixed
        if 'if kind in {\n        "risk_ok"' in text:
            print("grouped risk handler already present")
            SRC.write_text(text, encoding="utf-8")
            return
        print("WARN: flat risk handler not found")
        SRC.write_text(text, encoding="utf-8")
        return

    # Find start and end of flat handlers (through risk_root_valid return)
    start = text.find(old_handler_start)
    end_marker = 'return ok, f"risk_root_valid={ok}"\n'
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit("risk_root_valid handler end not found")
    end = end + len(end_marker)

    new_handler = '''    if kind in {
        "risk_ok",
        "risked_ok",
        "min_risks",
        "risk_root_valid",
    }:
        plane = (
            context.get("risk")
            or context.get("risk_plane")
            or context.get("assessment")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_risk_disk_evidence(context)
            if disk:
                plane = {**disk, **(plane if isinstance(plane, Mapping) else {})}
        if kind == "risk_ok":
            ok = bool(plane.get("ok"))
            return ok, f"risk_ok={ok}"
        if kind == "risked_ok":
            if "risked" in plane:
                ok = plane.get("risked") is True and bool(plane.get("ok", True))
            elif "risked_ok" in plane:
                ok = plane.get("risked_ok") is True
            else:
                ok = bool(plane.get("ok")) and int(
                    plane.get("risk_count") or plane.get("tip_height") or 0
                ) >= 1
            return ok, f"risked_ok={ok}"
        if kind == "min_risks":
            need = int(float(arg or "0"))
            have = context.get("risk_count")
            if have is None:
                have = context.get("tip_risk_height")
            if have is None:
                have = (
                    plane.get("risk_count")
                    or plane.get("tip_height")
                    or plane.get("entry_count")
                )
            have_i = int(have or 0)
            return have_i >= need, f"risks={have_i} need>={need}"
        if "risk_root_valid" in plane:
            ok = plane.get("risk_root_valid") is True
        elif "certificate_valid" in plane:
            ok = plane.get("certificate_valid") is True
        else:
            cert = (
                plane.get("risk_certificate")
                or plane.get("certificate")
                or context.get("risk_certificate")
                or {}
            )
            if isinstance(cert, Mapping) and cert:
                verify = verify_risk_certificate(cert)
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
            else:
                ok = bool(plane.get("ok")) and bool(
                    plane.get("risk_root") or plane.get("tip_risk_root")
                )
        return ok, f"risk_root_valid={ok}"

'''
    text = text[:start] + new_handler + text[end:]
    SRC.write_text(text, encoding="utf-8")
    print("replaced flat risk handlers with grouped block")


if __name__ == "__main__":
    main()
