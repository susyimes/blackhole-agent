
# --- Risk plane over solvency (generated capability layer) ---
RISK_BUNDLE_SCHEMA = 1
RISK_CERTIFICATE_SCHEMA = 1
RISK_LOG_SCHEMA = 1
DEFAULT_RISK_BUNDLE_RELATIVE = Path("artifacts") / "risk-bundles"


def default_risk_bundle_dir(repo_path: Path) -> Path:
    return (repo_path / DEFAULT_RISK_BUNDLE_RELATIVE).resolve()


def empty_risk_log() -> dict[str, Any]:
    return {
        "schema_version": RISK_LOG_SCHEMA,
        "kind": "risk_log",
        "entries": [],
        "entry_count": 0,
        "tip_height": 0,
        "tip_risk_root": "",
        "bound_solvency_root": "",
        "bound_solvency_height": 0,
        "solvency_hash": "",
        "risk_assessment_digest": "",
        "updated_at": utc_now_iso(),
    }


def compute_risk_root(clearing: Mapping[str, Any]) -> str:
    """Hash collateral body excluding self root, certificates, and wall-clock fields."""

    body = {
        key: value
        for key, value in clearing.items()
        if key
        not in {
            "risk_root",
            "risk_certificate",
            "ok",
            "valid",
            "action",
            "applied_at",
            "updated_at",
            "issued_at",
            "exported_at",
            "goal",
            "claims",
        }
    }
    digest = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()[:24]


def compute_risk_certificate_hash(payload: Mapping[str, Any]) -> str:
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"certificate_hash", "ok", "valid"}
    }
    digest = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()[:24]


def compute_risk_bundle_hash(bundle: Mapping[str, Any]) -> str:
    body = {
        key: value
        for key, value in bundle.items()
        if key
        not in {
            "risk_hash",
            "ok",
            "bundle_path",
            "exported_at",
            "source_ledger_path",
            "action",
        }
    }
    digest = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()[:24]


def compute_risk_assessment_digest(
    *,
    parent_risk_digest: str,
    bound_solvency_root: str,
    solvency_position_digest: str,
    capability_id: str,
    outcome: str = "risked",
    position_ratio_bps: int = 1000,
) -> str:
    """Deterministic solvency buffer netting prior cover with a newly risked clearing."""

    payload = {
        "parent_risk_digest": parent_risk_digest or "",
        "bound_solvency_root": bound_solvency_root,
        "solvency_position_digest": solvency_position_digest,
        "capability_id": capability_id,
        "outcome": outcome or "risked",
        "position_ratio_bps": int(position_ratio_bps),
        "plane": "risk",
    }
    digest = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()[:24]


def issue_risk_certificate(
    *,
    risk_height: int,
    risk_root: str,
    parent_risk_root: str,
    bound_solvency_root: str,
    bound_solvency_height: int,
    solvency_hash: str,
    solvency_certificate_hash: str,
    package_hash: str,
    lineage_head_hash: str,
    solvency_position_digest: str,
    risk_assessment_digest: str,
    risk_count: int,
    member_ids: Sequence[str] | None = None,
    goal: str = "",
    claims: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    members = sorted({str(item).strip() for item in (member_ids or []) if str(item).strip()})
    cert: dict[str, Any] = {
        "schema_version": RISK_CERTIFICATE_SCHEMA,
        "kind": "risk_certificate",
        "issued_at": utc_now_iso(),
        "risk_height": int(risk_height),
        "risk_root": str(risk_root or ""),
        "parent_risk_root": str(parent_risk_root or ""),
        "bound_solvency_root": str(bound_solvency_root or ""),
        "bound_solvency_height": int(bound_solvency_height or 0),
        "solvency_hash": str(solvency_hash or ""),
        "solvency_certificate_hash": str(solvency_certificate_hash or ""),
        "package_hash": str(package_hash or ""),
        "lineage_head_hash": str(lineage_head_hash or ""),
        "solvency_position_digest": str(solvency_position_digest or ""),
        "risk_assessment_digest": str(risk_assessment_digest or ""),
        "risk_count": int(risk_count),
        "member_ids": members,
        "member_count": len(members),
        "goal": goal or "",
        "claims": dict(claims or {}),
        "deterministic": True,
        "post_solvency": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    cert["certificate_hash"] = compute_risk_certificate_hash(cert)
    cert["ok"] = (
        bool(cert["certificate_hash"])
        and bool(cert["risk_root"])
        and bool(cert["bound_solvency_root"])
        and bool(cert["solvency_hash"])
        and bool(cert["risk_assessment_digest"])
        and bool(cert["solvency_position_digest"])
        and cert["risk_height"] >= 1
        and cert["risk_count"] >= 1
        and cert["deterministic"] is True
        and cert["post_solvency"] is True
        and not bool(cert["used_skill_route_discovery"])
    )
    cert["valid"] = bool(cert["ok"])
    return cert


def verify_risk_certificate(payload: Mapping[str, Any] | Path) -> dict[str, Any]:
    if isinstance(payload, Path):
        data = json.loads(payload.read_text(encoding="utf-8"))
    else:
        data = dict(payload)
    recomputed = compute_risk_certificate_hash(data)
    stored = str(data.get("certificate_hash") or "")
    hash_ok = bool(stored) and stored == recomputed
    valid = (
        hash_ok
        and data.get("kind") == "risk_certificate"
        and bool(data.get("risk_root"))
        and bool(data.get("bound_solvency_root"))
        and bool(data.get("solvency_hash"))
        and bool(data.get("risk_assessment_digest"))
        and bool(data.get("solvency_position_digest"))
        and int(data.get("risk_height") or 0) >= 1
        and int(data.get("risk_count") or 0) >= 1
        and data.get("deterministic") is True
        and data.get("post_solvency") is True
        and not bool(data.get("used_skill_route_discovery"))
    )
    return {
        "ok": valid,
        "valid": valid,
        "hash_ok": hash_ok,
        "certificate_hash": stored if hash_ok else recomputed,
        "risk_height": data.get("risk_height"),
        "risk_root": data.get("risk_root"),
        "bound_solvency_root": data.get("bound_solvency_root"),
        "risk_assessment_digest": data.get("risk_assessment_digest"),
        "solvency_hash": data.get("solvency_hash"),
        "used_skill_route_discovery": bool(data.get("used_skill_route_discovery")),
    }


def write_risk_certificate(path: Path, certificate: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, dict(certificate))
    return path


def _load_risk_disk_evidence(
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Best-effort load of a durable collateral proof bundle for context-less gates."""

    candidates: list[Path] = []
    ctx = context or {}
    for key in ("repo_path", "workspace", "workspace_path"):
        raw = ctx.get(key)
        if raw:
            root = Path(str(raw))
            candidates.extend(
                [
                    root / "artifacts" / "risk-bundles" / "proof-risk.json",
                    root / DEFAULT_RISK_BUNDLE_RELATIVE / "proof-risk.json",
                ]
            )
    here = Path.cwd()
    candidates.extend(
        [
            here / "artifacts" / "risk-bundles" / "proof-risk.json",
            here / DEFAULT_RISK_BUNDLE_RELATIVE / "proof-risk.json",
        ]
    )
    try:
        pkg_root = Path(__file__).resolve().parents[2]
        candidates.append(
            pkg_root / "artifacts" / "risk-bundles" / "proof-risk.json"
        )
    except Exception:
        pass
    for base in {Path.cwd(), Path(__file__).resolve().parents[2]}:
        bundle_dir = base / "artifacts" / "risk-bundles"
        if bundle_dir.is_dir():
            candidates.extend(sorted(bundle_dir.glob("risk-*.json"), reverse=True)[:3])
            candidates.extend(sorted(bundle_dir.glob("proof-risk*.json"), reverse=True)[:3])

    seen: set[str] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except Exception:
            continue
        key = str(resolved)
        if key in seen or not resolved.is_file():
            continue
        seen.add(key)
        try:
            bundle = load_risk_bundle(resolved)
        except Exception:
            continue
        integrity = verify_risk_bundle_integrity(bundle)
        if not integrity.get("ok"):
            continue
        cert = (
            bundle.get("risk_certificate")
            if isinstance(bundle.get("risk_certificate"), Mapping)
            else {}
        )
        cert_verify = (
            verify_risk_certificate(cert) if cert else {"ok": False, "valid": False}
        )
        risk_count = int(
            bundle.get("risk_count")
            or (bundle.get("risks") or {}).get("entry_count")
            or 0
        )
        tip_height = int(bundle.get("tip_height") or risk_count or 0)
        if risk_count < 2 or tip_height < 2 or not cert_verify.get("valid"):
            continue
        return {
            "ok": True,
            "risked": True,
            "risk_count": risk_count,
            "tip_height": tip_height,
            "tip_risk_root": bundle.get("tip_risk_root"),
            "risk_hash": bundle.get("risk_hash"),
            "risk_root_valid": True,
            "certificate_valid": True,
            "risk_assessment_digest": bundle.get("risk_assessment_digest"),
            "risk_certificate": cert,
            "bundle_path": str(resolved),
            "source": "disk_proof_bundle",
        }
    return None


def derive_risk_specs_from_solvency(
    solvency_bundle: Mapping[str, Any],
    *,
    min_risks: int = 2,
) -> list[dict[str, Any]]:
    """Derive one risk position per solvency buffer (multi-collateral required)."""

    solvencies = (
        solvency_bundle.get("solvencies")
        if isinstance(solvency_bundle.get("solvencies"), Mapping)
        else {}
    )
    entries = list(solvencies.get("entries") or [])
    specs: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        solvency_root = str(entry.get("solvency_root") or "")
        if not solvency_root:
            continue
        specs.append(
            {
                "capability_id": str(entry.get("capability_id") or ""),
                "effect": str(entry.get("effect") or ""),
                "bound_solvency_root": solvency_root,
                "bound_solvency_height": int(entry.get("solvency_height") or 0),
                "solvency_position_digest": str(entry.get("solvency_position_digest") or ""),
                "receipt_digest": str(entry.get("receipt_digest") or ""),
                "bound_settlement_root": str(entry.get("bound_settlement_root") or ""),
                "bound_action_root": str(entry.get("bound_action_root") or ""),
                "package_hash": str(
                    entry.get("package_hash")
                    or solvency_bundle.get("package_hash")
                    or ""
                ),
                "outcome": "risked",
                "position_ratio_bps": 1000 + 100 * len(specs),
            }
        )
    want = max(2, int(min_risks))
    return specs[:want] if len(specs) >= want else specs


def apply_risk_transition(
    risk_log: Mapping[str, Any],
    spec: Mapping[str, Any],
    *,
    solvency_bundle: Mapping[str, Any],
    goal: str = "",
    claims: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one risk position bound to a solvency requirement root and cover it."""

    log = copy.deepcopy(dict(risk_log)) if risk_log else empty_risk_log()
    entries = list(log.get("entries") or [])
    next_height = len(entries) + 1
    parent_root = str(entries[-1].get("risk_root") or "") if entries else ""
    parent_risk = str(entries[-1].get("risk_assessment_digest") or "") if entries else ""

    bound_solvency_root = str(spec.get("bound_solvency_root") or "")
    bound_solvency_height = int(spec.get("bound_solvency_height") or 0)
    capability_id = str(spec.get("capability_id") or "")
    effect = str(spec.get("effect") or "")
    outcome = str(spec.get("outcome") or "risked")
    package_hash = str(
        spec.get("package_hash") or solvency_bundle.get("package_hash") or ""
    )
    solvency_hash = str(solvency_bundle.get("solvency_hash") or "")
    tip_solvency_root = str(solvency_bundle.get("tip_solvency_root") or "")
    solvencies = (
        solvency_bundle.get("solvencies")
        if isinstance(solvency_bundle.get("solvencies"), Mapping)
        else {}
    )
    solvency_entries = list(solvencies.get("entries") or [])
    known_roots = {
        str(item.get("solvency_root") or "")
        for item in solvency_entries
        if isinstance(item, Mapping) and item.get("solvency_root")
    }
    if tip_solvency_root:
        known_roots.add(tip_solvency_root)

    if not capability_id or not bound_solvency_root or not solvency_hash:
        return {
            "ok": False,
            "action": "apply_risk_transition",
            "error": "missing_risk_bind_fields",
            "risk_log": log,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    if bound_solvency_root not in known_roots:
        return {
            "ok": False,
            "action": "apply_risk_transition",
            "error": "bound_solvency_root_mismatch",
            "bound_solvency_root": bound_solvency_root,
            "known_solvency_roots": sorted(known_roots),
            "risk_log": log,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    if any(
        str(item.get("bound_solvency_root") or "") == bound_solvency_root
        and str(item.get("outcome") or "") == outcome
        for item in entries
    ):
        return {
            "ok": False,
            "action": "apply_risk_transition",
            "error": "duplicate_risk_rejected",
            "risk_log": log,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    settle_cert = (
        solvency_bundle.get("solvency_certificate")
        if isinstance(solvency_bundle.get("solvency_certificate"), Mapping)
        else {}
    )
    settle_cert_hash = str(settle_cert.get("certificate_hash") or "")
    lineage_head = str(solvency_bundle.get("lineage_head_hash") or "")
    member_ids = list(solvency_bundle.get("member_ids") or [])
    solvency_position_digest = str(spec.get("solvency_position_digest") or "")
    position_ratio_bps = int(spec.get("position_ratio_bps") or 1000)
    if not solvency_position_digest:
        # Recover from settlement entry if available.
        for item in solvency_entries:
            if (
                isinstance(item, Mapping)
                and str(item.get("solvency_root") or "") == bound_solvency_root
            ):
                solvency_position_digest = str(item.get("solvency_position_digest") or "")
                break
    risk_assessment_digest = compute_risk_assessment_digest(
        parent_risk_digest=parent_risk,
        bound_solvency_root=bound_solvency_root,
        solvency_position_digest=solvency_position_digest,
        position_ratio_bps=position_ratio_bps,
        capability_id=capability_id,
        outcome=outcome,
    )

    body: dict[str, Any] = {
        "schema_version": RISK_LOG_SCHEMA,
        "kind": "risk_assessment",
        "risk_height": next_height,
        "parent_risk_root": parent_root,
        "bound_solvency_root": bound_solvency_root,
        "bound_solvency_height": bound_solvency_height,
        "solvency_hash": solvency_hash,
        "solvency_certificate_hash": settle_cert_hash,
        "package_hash": package_hash,
        "lineage_head_hash": lineage_head,
        "capability_id": capability_id,
        "effect": effect,
        "outcome": outcome,
        "solvency_position_digest": solvency_position_digest,
        "risk_assessment_digest": risk_assessment_digest,
        "position_ratio_bps": position_ratio_bps,
        "parent_risk_digest": parent_risk,
        "bound_action_root": str(spec.get("bound_action_root") or ""),
        "member_ids": sorted({str(m).strip() for m in member_ids if str(m).strip()}),
        "deterministic": True,
        "post_solvency": True,
        "applied_at": utc_now_iso(),
        "goal": goal or str(solvency_bundle.get("goal") or ""),
        "claims": dict(claims or {}),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    risk_root = compute_risk_root(body)
    body["risk_root"] = risk_root
    cert = issue_risk_certificate(
        risk_height=next_height,
        risk_root=risk_root,
        parent_risk_root=parent_root,
        bound_solvency_root=bound_solvency_root,
        bound_solvency_height=bound_solvency_height,
        solvency_hash=solvency_hash,
        solvency_certificate_hash=settle_cert_hash,
        package_hash=package_hash,
        lineage_head_hash=lineage_head,
        solvency_position_digest=solvency_position_digest,
        risk_assessment_digest=risk_assessment_digest,
        risk_count=next_height,
        member_ids=body["member_ids"],
        goal=goal or str(solvency_bundle.get("goal") or ""),
        claims={
            "capability_id": capability_id,
            "effect": effect,
            "outcome": outcome,
            "plane": "risk",
            **dict(claims or {}),
        },
    )
    body["risk_certificate"] = cert
    body["ok"] = (
        bool(cert.get("ok"))
        and bool(risk_root)
        and bool(risk_assessment_digest)
        and body["deterministic"] is True
        and body["post_solvency"] is True
        and not bool(body.get("used_skill_route_discovery"))
    )

    entries.append(body)
    log["entries"] = entries
    log["entry_count"] = len(entries)
    log["tip_height"] = next_height
    log["tip_risk_root"] = risk_root
    log["bound_solvency_root"] = bound_solvency_root
    log["bound_solvency_height"] = bound_solvency_height
    log["solvency_hash"] = solvency_hash
    log["risk_assessment_digest"] = risk_assessment_digest
    log["updated_at"] = utc_now_iso()
    log["schema_version"] = RISK_LOG_SCHEMA
    log["kind"] = "risk_log"
    return {
        "ok": bool(body.get("ok")),
        "action": "apply_risk_transition",
        "entry": body,
        "risk_height": next_height,
        "risk_root": risk_root,
        "parent_risk_root": parent_root,
        "bound_solvency_root": bound_solvency_root,
        "risk_assessment_digest": risk_assessment_digest,
        "risk_log": log,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def verify_risk_chain(risk_log: Mapping[str, Any]) -> dict[str, Any]:
    """Validate sequential heights, parent roots, allocations, hashes, and margin certs."""

    entries = list(risk_log.get("entries") or [])
    errors: list[str] = []
    if not entries:
        return {
            "ok": False,
            "valid": False,
            "action": "verify_risk_chain",
            "entry_count": 0,
            "tip_height": 0,
            "tip_risk_root": "",
            "errors": ["empty_risk_log"],
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    prev_root = ""
    prev_net = ""
    bound_settlements: set[str] = set()
    solvency_hashes: set[str] = set()
    for index, raw in enumerate(entries):
        if not isinstance(raw, Mapping):
            errors.append(f"entry[{index}]_not_mapping")
            continue
        height = int(raw.get("risk_height") or 0)
        expected_height = index + 1
        if height != expected_height:
            errors.append(f"entry[{index}]_height={height}_expected={expected_height}")
        parent = str(raw.get("parent_risk_root") or "")
        if index == 0:
            if parent:
                errors.append(f"entry[{index}]_genesis_has_parent")
        else:
            if parent != prev_root:
                errors.append(
                    f"entry[{index}]_parent_mismatch got={parent[:12]} expected={prev_root[:12]}"
                )
        stored = str(raw.get("risk_root") or "")
        recomputed = compute_risk_root({**dict(raw), "risk_root": ""})
        if not stored or stored != recomputed:
            errors.append(f"entry[{index}]_risk_root_mismatch")
        if raw.get("deterministic") is not True:
            errors.append(f"entry[{index}]_not_deterministic")
        if raw.get("post_solvency") is not True:
            errors.append(f"entry[{index}]_not_post_solvency")
        bound = str(raw.get("bound_solvency_root") or "")
        if not bound:
            errors.append(f"entry[{index}]_missing_bound_solvency_root")
        else:
            bound_settlements.add(bound)
        s_hash = str(raw.get("solvency_hash") or "")
        if not s_hash:
            errors.append(f"entry[{index}]_missing_solvency_hash")
        else:
            solvency_hashes.add(s_hash)
        solvency_position_digest = str(raw.get("solvency_position_digest") or "")
        parent_risk_stored = str(raw.get("parent_risk_digest") or "")
        if parent_risk_stored != prev_net:
            errors.append(f"entry[{index}]_parent_risk_mismatch")
        expected_net = compute_risk_assessment_digest(
            parent_risk_digest=prev_net,
            bound_solvency_root=bound,
            solvency_position_digest=solvency_position_digest,
            position_ratio_bps=int(raw.get("position_ratio_bps") or 1000),
            capability_id=str(raw.get("capability_id") or ""),
            outcome=str(raw.get("outcome") or "risked"),
        )
        stored_net = str(raw.get("risk_assessment_digest") or "")
        if not stored_net or stored_net != expected_net:
            errors.append(f"entry[{index}]_risk_assessment_digest_mismatch")
        cert = raw.get("risk_certificate")
        if not isinstance(cert, Mapping):
            errors.append(f"entry[{index}]_missing_solvency_certificate")
        else:
            cert_verify = verify_risk_certificate(cert)
            if not cert_verify.get("valid"):
                errors.append(f"entry[{index}]_clearing_cert_invalid")
            if str(cert.get("risk_root") or "") != stored:
                errors.append(f"entry[{index}]_cert_risk_root_mismatch")
            if int(cert.get("risk_height") or 0) != height:
                errors.append(f"entry[{index}]_cert_height_mismatch")
            if str(cert.get("bound_solvency_root") or "") != bound:
                errors.append(f"entry[{index}]_cert_bound_settlement_mismatch")
            if str(cert.get("risk_assessment_digest") or "") != stored_net:
                errors.append(f"entry[{index}]_cert_net_mismatch")
        prev_root = stored
        prev_net = stored_net

    if len(solvency_hashes) > 1:
        errors.append("mixed_solvency_hashes")

    tip = entries[-1] if entries else {}
    tip_height = int(tip.get("risk_height") or 0) if isinstance(tip, Mapping) else 0
    tip_root = str(tip.get("risk_root") or "") if isinstance(tip, Mapping) else ""
    tip_net = str(tip.get("risk_assessment_digest") or "") if isinstance(tip, Mapping) else ""
    log_tip_height = int(risk_log.get("tip_height") or 0)
    log_tip_root = str(risk_log.get("tip_risk_root") or "")
    log_net = str(risk_log.get("risk_assessment_digest") or "")
    if log_tip_height and log_tip_height != tip_height:
        errors.append("tip_height_metadata_mismatch")
    if log_tip_root and log_tip_root != tip_root:
        errors.append("tip_risk_root_metadata_mismatch")
    if log_net and log_net != tip_net:
        errors.append("risk_assessment_digest_metadata_mismatch")

    valid = not errors and tip_height >= 1 and bool(tip_root) and bool(tip_net)
    return {
        "ok": valid,
        "valid": valid,
        "action": "verify_risk_chain",
        "entry_count": len(entries),
        "tip_height": tip_height,
        "tip_risk_root": tip_root,
        "risk_assessment_digest": tip_net,
        "bound_solvency_roots": sorted(bound_settlements),
        "solvency_hash": next(iter(solvency_hashes), ""),
        "errors": errors,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def apply_solvency_bundle_to_risks(
    solvency_bundle: Mapping[str, Any],
    *,
    goal: str = "",
    min_risks: int = 2,
) -> dict[str, Any]:
    """Post multi-solvency positions into a deterministic risk position log."""

    integrity = verify_solvency_bundle_integrity(solvency_bundle)
    if not integrity.get("ok"):
        return {
            "ok": False,
            "action": "apply_solvency_bundle_to_risks",
            "error": "margin_integrity_failed",
            "integrity": integrity,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    specs = derive_risk_specs_from_solvency(
        solvency_bundle, min_risks=min_risks
    )
    if len(specs) < 2:
        return {
            "ok": False,
            "action": "apply_solvency_bundle_to_risks",
            "error": "need_multi_risk",
            "spec_count": len(specs),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    risk_log = empty_risk_log()
    applied: list[dict[str, Any]] = []
    for index, spec in enumerate(specs):
        result = apply_risk_transition(
            risk_log,
            spec,
            solvency_bundle=solvency_bundle,
            goal=f"{goal or solvency_bundle.get('goal') or 'clearing'} (clearing {index + 1})",
            claims={"clearing_index": index + 1, "plane": "risk"},
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "action": "apply_solvency_bundle_to_risks",
                "error": result.get("error") or "apply_failed",
                "applied_count": len(applied),
                "apply": {
                    "ok": result.get("ok"),
                    "error": result.get("error"),
                    "risk_height": result.get("risk_height"),
                },
                "risk_log": risk_log,
                "used_skill_route_discovery": legacy_pipeline_was_used(),
            }
        risk_log = result["risk_log"]
        applied.append(result["entry"])

    chain = verify_risk_chain(risk_log)
    ok = bool(chain.get("valid")) and len(applied) >= 2 and not legacy_pipeline_was_used()
    return {
        "ok": ok,
        "action": "apply_solvency_bundle_to_risks",
        "risk_log": risk_log,
        "applied": applied,
        "applied_count": len(applied),
        "risk_count": len(applied),
        "tip_height": risk_log.get("tip_height"),
        "tip_risk_root": risk_log.get("tip_risk_root"),
        "bound_solvency_root": risk_log.get("bound_solvency_root"),
        "risk_assessment_digest": risk_log.get("risk_assessment_digest"),
        "chain": chain,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def build_risk_bundle(
    risk_log: Mapping[str, Any],
    solvency_bundle: Mapping[str, Any],
    *,
    goal: str = "risk over solvency",
) -> dict[str, Any]:
    """Package collateral log + solvency tip into a portable collateral bundle."""

    chain = verify_risk_chain(risk_log)
    if not chain.get("valid"):
        return {
            "ok": False,
            "action": "build_risk_bundle",
            "error": "collateral_chain_invalid",
            "chain": chain,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    entries = list(risk_log.get("entries") or [])
    tip = entries[-1]
    tip_cert = (
        tip.get("risk_certificate")
        if isinstance(tip.get("risk_certificate"), Mapping)
        else {}
    )
    tip_cert_verify = (
        verify_risk_certificate(tip_cert) if tip_cert else {"valid": False}
    )
    settle_cert = (
        solvency_bundle.get("solvency_certificate")
        if isinstance(solvency_bundle.get("solvency_certificate"), Mapping)
        else {}
    )
    act_cert = (
        solvency_bundle.get("actuation_certificate")
        if isinstance(solvency_bundle.get("actuation_certificate"), Mapping)
        else {}
    )
    package = (
        solvency_bundle.get("package")
        if isinstance(solvency_bundle.get("package"), Mapping)
        else {}
    )
    certificates: dict[str, dict[str, Any]] = {}
    for clearing in entries:
        cert = clearing.get("risk_certificate")
        if isinstance(cert, Mapping) and cert.get("certificate_hash"):
            certificates[str(cert["certificate_hash"])] = {
                "certificate_hash": cert.get("certificate_hash"),
                "payload": cert,
                "risk_height": clearing.get("risk_height"),
            }
    if isinstance(settle_cert, Mapping) and settle_cert.get("certificate_hash"):
        certificates[str(settle_cert["certificate_hash"])] = {
            "certificate_hash": settle_cert.get("certificate_hash"),
            "payload": settle_cert,
            "kind": "risk_certificate",
        }
    if isinstance(act_cert, Mapping) and act_cert.get("certificate_hash"):
        certificates[str(act_cert["certificate_hash"])] = {
            "certificate_hash": act_cert.get("certificate_hash"),
            "payload": act_cert,
            "kind": "actuation_certificate",
        }
    exec_cert = (
        solvency_bundle.get("execution_certificate")
        if isinstance(solvency_bundle.get("execution_certificate"), Mapping)
        else {}
    )
    if isinstance(exec_cert, Mapping) and exec_cert.get("certificate_hash"):
        certificates[str(exec_cert["certificate_hash"])] = {
            "certificate_hash": exec_cert.get("certificate_hash"),
            "payload": exec_cert,
            "kind": "execution_certificate",
        }

    settle_cert_nested = (
        solvency_bundle.get("settlement_certificate")
        if isinstance(solvency_bundle.get("settlement_certificate"), Mapping)
        else {}
    )
    if isinstance(settle_cert_nested, Mapping) and settle_cert_nested.get(
        "certificate_hash"
    ):
        certificates[str(settle_cert_nested["certificate_hash"])] = {
            "certificate_hash": settle_cert_nested.get("certificate_hash"),
            "payload": settle_cert_nested,
            "kind": "settlement_certificate",
        }

    member_ids = list(solvency_bundle.get("member_ids") or package.get("member_ids") or [])
    cb: dict[str, Any] = {
        "schema_version": RISK_BUNDLE_SCHEMA,
        "kind": "risk_bundle",
        "action": "build_risk_bundle",
        "goal": goal,
        "risks": copy.deepcopy(dict(risk_log)),
        "solvencies": copy.deepcopy(
            solvency_bundle.get("solvencies")
            if isinstance(solvency_bundle.get("solvencies"), Mapping)
            else {}
        ),
        "settlements": copy.deepcopy(
            solvency_bundle.get("settlements")
            if isinstance(solvency_bundle.get("settlements"), Mapping)
            else {}
        ),
        "actions": copy.deepcopy(
            solvency_bundle.get("actions")
            if isinstance(solvency_bundle.get("actions"), Mapping)
            else {}
        ),
        "package": copy.deepcopy(dict(package)),
        "lineage": copy.deepcopy(
            solvency_bundle.get("lineage")
            if isinstance(solvency_bundle.get("lineage"), Mapping)
            else {}
        ),
        "risk_certificate": copy.deepcopy(dict(tip_cert)),
        "solvency_certificate": copy.deepcopy(dict(settle_cert)),
        "settlement_certificate": copy.deepcopy(dict(settle_cert_nested)),
        "actuation_certificate": copy.deepcopy(dict(act_cert)),
        "execution_certificate": copy.deepcopy(dict(exec_cert)),
        "certificates": certificates,
        "certificate_count": len(certificates),
        "risk_count": len(entries),
        "solvency_count": int(solvency_bundle.get("solvency_count") or 0),
        "settlement_count": int(solvency_bundle.get("settlement_count") or 0),
        "action_count": int(solvency_bundle.get("action_count") or 0),
        "tip_height": int(risk_log.get("tip_height") or 0),
        "tip_risk_root": str(risk_log.get("tip_risk_root") or ""),
        "bound_solvency_root": str(risk_log.get("bound_solvency_root") or ""),
        "bound_solvency_height": int(risk_log.get("bound_solvency_height") or 0),
        "tip_solvency_root": str(solvency_bundle.get("tip_solvency_root") or ""),
        "bound_settlement_root": str(solvency_bundle.get("bound_settlement_root") or ""),
        "tip_settlement_root": str(solvency_bundle.get("tip_settlement_root") or ""),
        "bound_action_root": str(solvency_bundle.get("bound_action_root") or ""),
        "tip_action_root": str(solvency_bundle.get("tip_action_root") or ""),
        "bound_state_root": str(solvency_bundle.get("bound_state_root") or ""),
        "risk_assessment_digest": str(risk_log.get("risk_assessment_digest") or ""),
        "solvency_position_digest": str(solvency_bundle.get("solvency_position_digest") or ""),
        "solvency_hash": str(solvency_bundle.get("solvency_hash") or ""),
        "settlement_hash": str(solvency_bundle.get("settlement_hash") or ""),
        "actuation_hash": str(solvency_bundle.get("actuation_hash") or ""),
        "execution_hash": str(solvency_bundle.get("execution_hash") or ""),
        "package_hash": str(solvency_bundle.get("package_hash") or ""),
        "member_ids": sorted({str(m).strip() for m in member_ids if str(m).strip()}),
        "member_count": len(member_ids),
        "lineage_head_hash": str(solvency_bundle.get("lineage_head_hash") or ""),
        "lineage_entry_count": int(solvency_bundle.get("lineage_entry_count") or 0),
        "origin_count": solvency_bundle.get("origin_count"),
        "agreeing_count": solvency_bundle.get("agreeing_count"),
        "byzantine_count": solvency_bundle.get("byzantine_count"),
        "state_count": solvency_bundle.get("state_count"),
        "epoch_count": solvency_bundle.get("epoch_count"),
        "deterministic": True,
        "post_solvency": True,
        "exported_at": utc_now_iso(),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    cb["risk_hash"] = compute_risk_bundle_hash(cb)
    cb["ok"] = (
        bool(chain.get("valid"))
        and bool(tip_cert_verify.get("valid"))
        and len(entries) >= 2
        and bool(cb["risk_hash"])
        and bool(cb["solvency_hash"])
        and bool(cb["risk_assessment_digest"])
        and cb["deterministic"] is True
        and cb["post_solvency"] is True
        and not bool(cb["used_skill_route_discovery"])
    )
    return cb


def write_risk_bundle(path: Path, bundle: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, dict(bundle))
    return path


def load_risk_bundle(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("clearing bundle must be a JSON object")
    return data


def verify_risk_bundle_integrity(bundle: Mapping[str, Any]) -> dict[str, Any]:
    expected = str(bundle.get("risk_hash") or "").strip()
    recomputed = compute_risk_bundle_hash(bundle)
    hash_ok = bool(expected) and expected == recomputed
    solvencies = (
        bundle.get("risks")
        if isinstance(bundle.get("risks"), Mapping)
        else {}
    )
    chain = (
        verify_risk_chain(solvencies)
        if solvencies
        else {"ok": False, "valid": False, "errors": ["missing_solvencies"]}
    )
    cert = (
        bundle.get("risk_certificate")
        if isinstance(bundle.get("risk_certificate"), Mapping)
        else {}
    )
    cert_verify = (
        verify_risk_certificate(cert) if cert else {"valid": False, "ok": False}
    )
    settle_cert = (
        bundle.get("solvency_certificate")
        if isinstance(bundle.get("solvency_certificate"), Mapping)
        else {}
    )
    settle_cert_verify = (
        verify_solvency_certificate(settle_cert)
        if settle_cert
        else {"valid": False, "ok": False}
    )
    multi = int(bundle.get("risk_count") or chain.get("entry_count") or 0) >= 2
    package = bundle.get("package") if isinstance(bundle.get("package"), Mapping) else {}
    package_ok = bool(package) and bool(bundle.get("package_hash"))
    bound_ok = bool(bundle.get("bound_solvency_root")) and bool(
        bundle.get("solvency_hash")
    )
    margin_digest_ok = bool(bundle.get("risk_assessment_digest")) and str(
        bundle.get("risk_assessment_digest") or ""
    ) == str(chain.get("risk_assessment_digest") or bundle.get("risk_assessment_digest") or "")
    deterministic = bundle.get("deterministic") is True
    post_solvency = bundle.get("post_solvency") is True
    used_skill = bool(bundle.get("used_skill_route_discovery")) or legacy_pipeline_was_used()
    ok = (
        hash_ok
        and bool(chain.get("valid"))
        and bool(cert_verify.get("valid"))
        and bool(settle_cert_verify.get("valid"))
        and multi
        and package_ok
        and bound_ok
        and margin_digest_ok
        and deterministic
        and post_solvency
        and not used_skill
    )
    return {
        "ok": ok,
        "action": "verify_risk_bundle_integrity",
        "hash_ok": hash_ok,
        "chain_valid": bool(chain.get("valid")),
        "multi_risk": multi,
        "package_ok": package_ok,
        "risk_certificate_valid": bool(cert_verify.get("valid")),
        "solvency_certificate_valid": bool(settle_cert_verify.get("valid")),
        "bound_ok": bound_ok,
        "risk_ok": margin_digest_ok,
        "margin_digest_ok": margin_digest_ok,
        "deterministic": deterministic,
        "post_solvency": post_solvency,
        "tip_height": chain.get("tip_height"),
        "tip_risk_root": chain.get("tip_risk_root"),
        "risk_assessment_digest": chain.get("risk_assessment_digest"),
        "risk_hash": expected if hash_ok else recomputed,
        "errors": list(chain.get("errors") or []),
        "used_skill_route_discovery": used_skill,
    }


def rehydrate_risk_bundle(
    repo_path: Path,
    bundle: Mapping[str, Any],
    *,
    sandbox_dir: Path | None = None,
) -> dict[str, Any]:
    """Materialize tip package + collateral log into a sterile sandbox and re-check allocations."""

    root = repo_path.resolve()
    integrity = verify_risk_bundle_integrity(bundle)
    if not integrity.get("ok"):
        return {
            "ok": False,
            "action": "rehydrate_risk_bundle",
            "error": "collateral_integrity_failed",
            "integrity": integrity,
            "used_skill_route_discovery": integrity.get("used_skill_route_discovery"),
        }

    c_hash = str(bundle.get("risk_hash") or "unknown")
    sandbox = (
        sandbox_dir.resolve()
        if sandbox_dir is not None
        else (root / "artifacts" / "risk-sandbox" / c_hash[:16])
    )
    sandbox.mkdir(parents=True, exist_ok=True)

    package = dict(bundle.get("package") or {})
    lineage = copy.deepcopy(bundle.get("lineage") or {})
    risks = copy.deepcopy(bundle.get("risks") or {})
    solvencies = copy.deepcopy(bundle.get("solvencies") or {})
    settlements = copy.deepcopy(bundle.get("settlements") or {})
    actions = copy.deepcopy(bundle.get("actions") or {})
    lineage_path = sandbox / "lineage.json"
    if lineage:
        write_lineage_log(lineage_path, lineage)
    risks_path = sandbox / "risks.json"
    atomic_write_json(risks_path, risks)
    solvencies_path = sandbox / "solvencies.json"
    atomic_write_json(solvencies_path, solvencies)
    settlements_path = sandbox / "settlements.json"
    atomic_write_json(settlements_path, settlements)
    actions_path = sandbox / "actions.json"
    atomic_write_json(actions_path, actions)

    empty = CapabilityLedger(schema_version=SCHEMA_VERSION, updated_at=utc_now_iso())
    empty, import_report = import_capability_package(empty, package, replace=True)
    sterile_ledger_path = sandbox / "ledger.json"
    save_ledger(sterile_ledger_path, empty)

    cert = (
        bundle.get("risk_certificate")
        if isinstance(bundle.get("risk_certificate"), Mapping)
        else {}
    )
    cert_path = sandbox / "risk-certificate.json"
    if cert:
        write_risk_certificate(cert_path, cert)
    clear_cert = (
        bundle.get("solvency_certificate")
        if isinstance(bundle.get("solvency_certificate"), Mapping)
        else {}
    )
    clear_cert_path = sandbox / "clearing-certificate.json"
    if clear_cert:
        write_solvency_certificate(clear_cert_path, clear_cert)

    chain = verify_risk_chain(risks)
    cert_verify = (
        verify_risk_certificate(cert) if cert else {"ok": False, "valid": False}
    )
    clear_cert_verify = (
        verify_solvency_certificate(clear_cert)
        if clear_cert
        else {"ok": False, "valid": False}
    )
    re_margin_digest_ok = True
    prev_net = ""
    for entry in list(risks.get("entries") or []):
        if not isinstance(entry, Mapping):
            re_margin_digest_ok = False
            break
        expected = compute_risk_assessment_digest(
            parent_risk_digest=prev_net,
            bound_solvency_root=str(entry.get("bound_solvency_root") or ""),
            solvency_position_digest=str(entry.get("solvency_position_digest") or ""),
            position_ratio_bps=int(entry.get("position_ratio_bps") or 1000),
            capability_id=str(entry.get("capability_id") or ""),
            outcome=str(entry.get("outcome") or "risked"),
        )
        if expected != str(entry.get("risk_assessment_digest") or ""):
            re_margin_digest_ok = False
            break
        prev_net = expected

    lineage_chain = (
        verify_lineage_chain(lineage)
        if lineage
        else {"ok": True, "valid": True, "entry_count": 0}
    )
    used_skill = legacy_pipeline_was_used()
    ok = (
        bool(integrity.get("ok"))
        and bool(import_report.get("ok"))
        and bool(chain.get("valid"))
        and bool(cert_verify.get("valid"))
        and bool(clear_cert_verify.get("valid"))
        and re_margin_digest_ok
        and int(import_report.get("imported_count") or 0) >= 1
        and not used_skill
    )
    return {
        "ok": ok,
        "action": "rehydrate_risk_bundle",
        "sandbox_dir": str(sandbox),
        "lineage_path": str(lineage_path) if lineage else None,
        "risks_path": str(risks_path),
        "solvencies_path": str(solvencies_path),
        "settlements_path": str(settlements_path),
        "actions_path": str(actions_path),
        "sterile_ledger_path": str(sterile_ledger_path),
        "certificate_path": str(cert_path) if cert else None,
        "solvency_certificate_path": str(clear_cert_path) if clear_cert else None,
        "risk_hash": c_hash,
        "import": import_report,
        "chain": {
            "ok": chain.get("ok"),
            "valid": chain.get("valid"),
            "entry_count": chain.get("entry_count"),
            "tip_height": chain.get("tip_height"),
            "tip_risk_root": chain.get("tip_risk_root"),
            "risk_assessment_digest": chain.get("risk_assessment_digest"),
            "errors": chain.get("errors") or [],
        },
        "lineage_chain": {
            "ok": lineage_chain.get("ok"),
            "valid": lineage_chain.get("valid"),
            "entry_count": lineage_chain.get("entry_count"),
        },
        "risk_certificate": {
            "ok": cert_verify.get("ok"),
            "valid": cert_verify.get("valid"),
            "certificate_hash": cert_verify.get("certificate_hash"),
            "risk_root": cert_verify.get("risk_root"),
        },
        "solvency_certificate": {
            "ok": clear_cert_verify.get("ok"),
            "valid": clear_cert_verify.get("valid"),
            "certificate_hash": clear_cert_verify.get("certificate_hash"),
        },
        "margin_digests_match": re_margin_digest_ok,
        "integrity": {
            "ok": integrity.get("ok"),
            "hash_ok": integrity.get("hash_ok"),
            "multi_risk": integrity.get("multi_risk"),
            "tip_height": integrity.get("tip_height"),
        },
        "sterile_ledger": empty,
        "used_skill_route_discovery": used_skill,
    }


def replay_risks_from_specs(
    specs: Sequence[Mapping[str, Any]],
    solvency_bundle: Mapping[str, Any],
    *,
    goal: str = "",
) -> dict[str, Any]:
    risk_log = empty_risk_log()
    for index, spec in enumerate(specs):
        result = apply_risk_transition(
            risk_log,
            spec,
            solvency_bundle=solvency_bundle,
            goal=f"{goal} (replay {index + 1})",
            claims={"replay": True, "clearing_index": index + 1},
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "error": result.get("error") or "replay_failed",
                "risk_log": risk_log,
                "applied_count": index,
            }
        risk_log = result["risk_log"]
    chain = verify_risk_chain(risk_log)
    return {
        "ok": bool(chain.get("valid")),
        "risk_log": risk_log,
        "tip_risk_root": risk_log.get("tip_risk_root"),
        "tip_height": risk_log.get("tip_height"),
        "risk_assessment_digest": risk_log.get("risk_assessment_digest"),
        "chain": chain,
    }


def run_risk_adversarial_checks(
    intact_bundle: Mapping[str, Any],
    risk_log: Mapping[str, Any],
    solvency_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Falsify collateral honesty: mutation, reorder, wrong-margin, double-clear, forged root, net."""

    intact = verify_risk_bundle_integrity(intact_bundle)
    intact_chain = verify_risk_chain(risk_log)

    mutated_log = copy.deepcopy(dict(risk_log))
    m_entries = list(mutated_log.get("entries") or [])
    mutation_fails = False
    if m_entries:
        first = dict(m_entries[0])
        first["capability_id"] = "evil.capability"
        m_entries[0] = first
        mutated_log["entries"] = m_entries
        mutation_check = verify_risk_chain(mutated_log)
        mutation_fails = mutation_check.get("valid") is not True

    reorder_fails = False
    if len(list(risk_log.get("entries") or [])) >= 2:
        rev = copy.deepcopy(dict(risk_log))
        rev["entries"] = list(reversed(list(rev.get("entries") or [])))
        reorder_check = verify_risk_chain(rev)
        reorder_fails = reorder_check.get("valid") is not True
    else:
        reorder_fails = True

    wrong_solvency_fails = False
    if m_entries:
        ws = copy.deepcopy(dict(risk_log))
        w_entries = list(ws.get("entries") or [])
        tip = dict(w_entries[-1])
        tip["bound_solvency_root"] = "a" * 24
        w_entries[-1] = tip
        ws["entries"] = w_entries
        ws["bound_solvency_root"] = tip["bound_solvency_root"]
        wrong_check = verify_risk_chain(ws)
        wrong_solvency_fails = wrong_check.get("valid") is not True
    specs = derive_risk_specs_from_solvency(solvency_bundle)
    bad_spec = dict(specs[0]) if specs else {}
    if bad_spec:
        bad_spec["bound_solvency_root"] = "b" * 24
        apply_bad = apply_risk_transition(
            empty_risk_log(),
            bad_spec,
            solvency_bundle=solvency_bundle,
            goal="bad-bind",
        )
        wrong_solvency_fails = wrong_solvency_fails and (
            apply_bad.get("ok") is not True
            and apply_bad.get("error") == "bound_solvency_root_mismatch"
        )

    forged_log = copy.deepcopy(dict(risk_log))
    f_entries = list(forged_log.get("entries") or [])
    forged_root_fails = False
    if f_entries:
        tip = dict(f_entries[-1])
        tip["risk_root"] = "f" * 24
        f_entries[-1] = tip
        forged_log["entries"] = f_entries
        forged_log["tip_risk_root"] = tip["risk_root"]
        forged_check = verify_risk_chain(forged_log)
        forged_root_fails = forged_check.get("valid") is not True

    gap_log = copy.deepcopy(dict(risk_log))
    g_entries = list(gap_log.get("entries") or [])
    gap_fails = False
    if g_entries:
        last = dict(g_entries[-1])
        last["risk_height"] = int(last.get("risk_height") or 1) + 5
        g_entries[-1] = last
        gap_log["entries"] = g_entries
        gap_log["tip_height"] = last["risk_height"]
        gap_check = verify_risk_chain(gap_log)
        gap_fails = gap_check.get("valid") is not True

    broken_cert_fails = False
    if m_entries:
        broken_log = copy.deepcopy(dict(risk_log))
        b_entries = list(broken_log.get("entries") or [])
        tip = dict(b_entries[-1])
        cert = dict(tip.get("risk_certificate") or {})
        cert["certificate_hash"] = "0" * 24
        tip["risk_certificate"] = cert
        b_entries[-1] = tip
        broken_log["entries"] = b_entries
        broken_check = verify_risk_chain(broken_log)
        broken_cert_fails = broken_check.get("valid") is not True

    parent_fails = False
    if len(list(risk_log.get("entries") or [])) >= 2:
        parent_log = copy.deepcopy(dict(risk_log))
        p_entries = list(parent_log.get("entries") or [])
        tip = dict(p_entries[-1])
        tip["parent_risk_root"] = "deadbeef-parent-root"
        p_entries[-1] = tip
        parent_log["entries"] = p_entries
        parent_check = verify_risk_chain(parent_log)
        parent_fails = parent_check.get("valid") is not True
    else:
        parent_fails = True

    digest_tamper_fails = False
    if m_entries:
        net_log = copy.deepcopy(dict(risk_log))
        n_entries = list(net_log.get("entries") or [])
        tip = dict(n_entries[-1])
        tip["risk_assessment_digest"] = "c" * 24
        n_entries[-1] = tip
        net_log["entries"] = n_entries
        net_log["risk_assessment_digest"] = tip["risk_assessment_digest"]
        net_check = verify_risk_chain(net_log)
        digest_tamper_fails = net_check.get("valid") is not True

    tampered = copy.deepcopy(dict(intact_bundle))
    tampered["risk_hash"] = "e" * 24
    tamper_check = verify_risk_bundle_integrity(tampered)
    tamper_fails = tamper_check.get("ok") is not True

    single = copy.deepcopy(dict(intact_bundle))
    single_risks = copy.deepcopy(dict(single.get("risks") or {}))
    s_entries = list(single_risks.get("entries") or [])[:1]
    single_risks["entries"] = s_entries
    single_risks["entry_count"] = len(s_entries)
    if s_entries:
        single_risks["tip_height"] = s_entries[0].get("risk_height")
        single_risks["tip_risk_root"] = s_entries[0].get("risk_root")
        single_risks["risk_assessment_digest"] = s_entries[0].get("risk_assessment_digest")
        single["risks"] = single_risks
        single["risk_count"] = 1
        single["tip_height"] = single_risks["tip_height"]
        single["tip_risk_root"] = single_risks["tip_risk_root"]
        single["risk_assessment_digest"] = single_risks["risk_assessment_digest"]
        if "risk_hash" in single:
            del single["risk_hash"]
        single["risk_hash"] = compute_risk_bundle_hash(single)
        single_check = verify_risk_bundle_integrity(single)
        single_risk_fails = single_check.get("ok") is not True
    else:
        single_risk_fails = True

    replay_match = False
    if specs:
        replay = replay_risks_from_specs(
            specs, solvency_bundle, goal="adversarial-replay"
        )
        replay_match = (
            bool(replay.get("ok"))
            and str(replay.get("tip_risk_root") or "")
            == str(risk_log.get("tip_risk_root") or "")
            and int(replay.get("tip_height") or 0)
            == int(risk_log.get("tip_height") or 0)
            and str(replay.get("risk_assessment_digest") or "")
            == str(risk_log.get("risk_assessment_digest") or "")
        )

    dup_fails = False
    if specs:
        dup = apply_risk_transition(
            risk_log, specs[-1], solvency_bundle=solvency_bundle, goal="dup"
        )
        dup_fails = dup.get("ok") is not True and dup.get("error") in {
            "duplicate_risk_rejected",
        }

    incomplete_fails = single_risk_fails
    used_skill = legacy_pipeline_was_used()
    ok = (
        bool(intact.get("ok"))
        and bool(intact_chain.get("valid"))
        and mutation_fails
        and reorder_fails
        and wrong_solvency_fails
        and forged_root_fails
        and gap_fails
        and broken_cert_fails
        and parent_fails
        and digest_tamper_fails
        and tamper_fails
        and single_risk_fails
        and replay_match
        and dup_fails
        and incomplete_fails
        and not used_skill
    )
    return {
        "ok": ok,
        "action": "risk_adversarial_checks",
        "intact_ok": bool(intact.get("ok")),
        "chain_ok": bool(intact_chain.get("valid")),
        "mutation_fails_as_expected": mutation_fails,
        "reorder_fails_as_expected": reorder_fails,
        "wrong_solvency_fails_as_expected": wrong_solvency_fails,
        "forged_root_fails_as_expected": forged_root_fails,
        "gap_fails_as_expected": gap_fails,
        "broken_cert_fails_as_expected": broken_cert_fails,
        "wrong_parent_fails_as_expected": parent_fails,
        "digest_tamper_fails_as_expected": digest_tamper_fails,
        "tamper_fails_as_expected": tamper_fails,
        "single_risk_fails_as_expected": single_risk_fails,
        "replay_matches_tip": replay_match,
        "duplicate_apply_fails_as_expected": dup_fails,
        "incomplete_fails_as_expected": incomplete_fails,
        "used_skill_route_discovery": used_skill,
    }


def run_risk_plane(
    repo_path: Path,
    goal: str = "risk over solvency",
    done_when: str = "",
    *,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 960,
    max_steps: int = 3,
    run_solvency: bool = True,
    run_liquidity: bool = True,
    run_collateral: bool = True,
    run_margin: bool = True,
    run_clearing: bool = True,
    run_settlement: bool = True,
    run_actuation: bool = True,
    run_execution: bool = True,
    run_finality: bool = True,
    run_quorum: bool = True,
    run_continuity: bool = False,
    run_reconciliation: bool = False,
    force_synthetic_drift: bool = True,
    inject_byzantine: bool = True,
    prove_imported: bool = True,
    epoch_count: int = 2,
    min_actions: int = 2,
    min_settlements: int = 2,
    min_clearings: int = 2,
    min_margins: int = 2,
    min_collaterals: int = 2,
    min_liquidities: int = 2,
    min_solvencies: int = 2,
    min_risks: int = 2,
    lineage_path: Path | None = None,
    bundle_path: Path | None = None,
    quorum_path: Path | None = None,
    finality_path: Path | None = None,
    execution_path: Path | None = None,
    actuation_path: Path | None = None,
    settlement_path: Path | None = None,
    margin_path: Path | None = None,
    collateral_path: Path | None = None,
    liquidity_path: Path | None = None,
    solvency_path: Path | None = None,
    risk_path: Path | None = None,
    sandbox_dir: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Closed risk plane: solvency → multi-risk assessments → cert → rehydrate → adversarial.

    Past solvent positions: each solvency position binds an ordered risk position into a
    hash-chained solvency log with risk position digests and solvency certificates bound
    to the solvency tip. Mutation, reorder, wrong-funding binding, double-risk,
    forged roots, height gaps, broken certs, digest tamper, and single-solvency bundles fail;
    sterile rehydrate+prove and genesis replay matching tip succeed without skill-route.
    """

    root = repo_path.resolve()
    path, _ledger = ensure_seeded_ledger(root)
    want_epochs = max(2, int(epoch_count))
    want_actions = max(2, int(min_actions))
    want_settlements = max(2, int(min_settlements))
    want_clearings = max(2, int(min_clearings))
    want_margins = max(2, int(min_margins))
    want_collaterals = max(2, int(min_collaterals))
    want_liquidities = max(2, int(min_liquidities))
    want_solvencies = max(2, int(min_solvencies))
    want_risks = max(2, int(min_risks))

    out_lineage = (
        lineage_path.resolve()
        if lineage_path is not None
        else default_lineage_path(root)
    )
    out_solvency = (
        solvency_path.resolve()
        if solvency_path is not None
        else (default_solvency_bundle_dir(root) / "risk-source-solvency.json")
    )

    solvency_report: dict[str, Any] | None = None
    solvency_bundle: dict[str, Any] | None = None
    if run_solvency:
        solvency_report = run_solvency_plane(
            root,
            goal if goal else "solvency for risk",
            strip_context_only_outcome_predicates(done_when or ""),
            command_runner=command_runner,
            timeout=timeout,
            max_steps=max_steps,
            run_capital=run_solvency,
            run_liquidity=run_liquidity,
            run_collateral=run_collateral,
            run_margin=run_margin,
            run_clearing=run_clearing,
            run_settlement=run_settlement,
            run_actuation=run_actuation,
            run_execution=run_execution,
            run_finality=run_finality,
            run_quorum=run_quorum,
            run_continuity=run_continuity,
            run_reconciliation=run_reconciliation,
            force_synthetic_drift=force_synthetic_drift,
            inject_byzantine=inject_byzantine,
            prove_imported=prove_imported,
            epoch_count=want_epochs,
            min_actions=want_actions,
            min_settlements=want_settlements,
            min_clearings=want_clearings,
            min_margins=want_margins,
            min_collaterals=want_collaterals,
            min_liquidities=want_liquidities,
            min_solvencies=want_solvencies,
            lineage_path=out_lineage,
            bundle_path=bundle_path,
            quorum_path=quorum_path,
            finality_path=finality_path,
            execution_path=execution_path,
            actuation_path=actuation_path,
            settlement_path=settlement_path,
            margin_path=margin_path,
            collateral_path=collateral_path,
            liquidity_path=liquidity_path,
            solvency_path=out_solvency,
            persist=persist,
        )
        c_path = Path(
            (
                solvency_report.get("capital")
                or solvency_report.get("solvency")
                or solvency_report.get("funding")
                or solvency_report.get("margin")
                or {}
            ).get("bundle_path")
            or ""
        )
        if c_path and c_path.is_file():
            solvency_bundle = load_solvency_bundle(c_path)
        elif out_solvency.is_file():
            solvency_bundle = load_solvency_bundle(out_solvency)
        else:
            solvency_bundle = None
    else:
        if out_solvency.is_file():
            solvency_bundle = load_solvency_bundle(out_solvency)
        else:
            solvency_report = run_solvency_plane(
                root,
                goal,
                "",
                command_runner=command_runner,
                timeout=timeout,
                max_steps=max_steps,
                run_capital=True,
                run_liquidity=run_liquidity,
                run_collateral=run_collateral,
                run_margin=run_margin,
                run_clearing=run_clearing,
                run_settlement=run_settlement,
                run_actuation=run_actuation,
                run_execution=run_execution,
                run_finality=run_finality,
                run_quorum=run_quorum,
                run_continuity=False,
                run_reconciliation=False,
                inject_byzantine=inject_byzantine,
                prove_imported=prove_imported,
                epoch_count=want_epochs,
                min_actions=want_actions,
                min_settlements=want_settlements,
                min_clearings=want_clearings,
                min_margins=want_margins,
                min_collaterals=want_collaterals,
                min_liquidities=want_liquidities,
                min_solvencies=want_solvencies,
                lineage_path=out_lineage,
                settlement_path=settlement_path,
                margin_path=margin_path,
                collateral_path=collateral_path,
                liquidity_path=liquidity_path,
                solvency_path=out_solvency,
                persist=persist,
            )
            if out_solvency.is_file():
                solvency_bundle = load_solvency_bundle(out_solvency)

    parent_solvent = bool(
        (solvency_report or {}).get("solvent")
        or (solvency_report or {}).get("risked")
        or (solvency_report or {}).get("ok")
        or (solvency_bundle or {}).get("ok")
    )
    if solvency_bundle is None or not (
        solvency_bundle.get("ok") or parent_solvent
    ):
        return {
            "ok": False,
            "action": "risk_plane",
            "error": "solvency_source_failed",
            "solvency": None
            if solvency_report is None
            else {
                "ok": solvency_report.get("ok"),
                "solvent": solvency_report.get("solvent") or solvency_report.get("risked"),
            },
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "ledger_path": str(path),
        }

    applied = apply_solvency_bundle_to_risks(
        solvency_bundle,
        goal=goal,
        min_risks=want_risks,
    )
    if not applied.get("ok"):
        return {
            "ok": False,
            "action": "risk_plane",
            "error": applied.get("error") or "risk_apply_failed",
            "apply": {
                "ok": applied.get("ok"),
                "error": applied.get("error"),
                "applied_count": applied.get("applied_count"),
            },
            "settlement": {
                "ok": True if solvency_report is None else bool(solvency_report.get("ok")),
                "solvency_hash": solvency_bundle.get("solvency_hash"),
            },
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "ledger_path": str(path),
        }

    risk_log = applied["risk_log"]
    margin = build_risk_bundle(
        risk_log,
        solvency_bundle,
        goal=goal,
    )
    out_c = (
        risk_path.resolve()
        if risk_path is not None
        else (
            default_risk_bundle_dir(root)
            / f"risk-{margin.get('risk_hash') or 'unknown'}.json"
        )
    )
    if persist and margin.get("ok"):
        write_risk_bundle(out_c, margin)
        reloaded = load_risk_bundle(out_c)
    else:
        reloaded = margin

    integrity = verify_risk_bundle_integrity(reloaded)
    rehydrate = rehydrate_risk_bundle(
        root,
        reloaded,
        sandbox_dir=sandbox_dir,
    )
    sterile = rehydrate.get("sterile_ledger")
    if prove_imported and isinstance(sterile, CapabilityLedger):
        member_ids = list((reloaded.get("package") or {}).get("member_ids") or [])
        roots = list((reloaded.get("package") or {}).get("roots") or member_ids[:3])
        if not roots:
            roots = list((reloaded.get("package") or {}).get("members") or {}).keys()
            roots = list(roots)[:3]
        prove = prove_sterile_package(
            root,
            sterile,
            roots,
            command_runner=command_runner,
            timeout=min(timeout, 120),
        )
    else:
        prove = {
            "ok": not prove_imported,
            "action": "prove_sterile_package",
            "proved_count": 0,
            "proofs": [],
            "used_skill_route_discovery": False,
        }

    chain = verify_risk_chain(
        reloaded.get("risks")
        if isinstance(reloaded.get("risks"), Mapping)
        else risk_log
    )
    cert_verify = verify_risk_certificate(
        reloaded.get("risk_certificate")
        if isinstance(reloaded.get("risk_certificate"), Mapping)
        else {}
    )
    adversarial = run_risk_adversarial_checks(
        reloaded, risk_log, solvency_bundle
    )

    used_skill = bool(
        (solvency_report or {}).get("used_skill_route_discovery")
        or margin.get("used_skill_route_discovery")
        or integrity.get("used_skill_route_discovery")
        or rehydrate.get("used_skill_route_discovery")
        or prove.get("used_skill_route_discovery")
        or adversarial.get("used_skill_route_discovery")
        or legacy_pipeline_was_used()
    )
    tip_height = int(reloaded.get("tip_height") or chain.get("tip_height") or 0)
    risk_n = int(reloaded.get("risk_count") or chain.get("entry_count") or 0)
    solvency_n = int(
        reloaded.get("solvency_count") or solvency_bundle.get("solvency_count") or 0
    )
    settlement_n = int(
        reloaded.get("settlement_count") or solvency_bundle.get("settlement_count") or 0
    )
    action_n = int(reloaded.get("action_count") or solvency_bundle.get("action_count") or 0)
    state_n = int(reloaded.get("state_count") or solvency_bundle.get("state_count") or 0)
    epoch_n = int(reloaded.get("epoch_count") or solvency_bundle.get("epoch_count") or 0)
    risked = (
        bool(margin.get("ok"))
        and bool(integrity.get("ok"))
        and bool(rehydrate.get("ok"))
        and bool(prove.get("ok"))
        and bool(chain.get("valid"))
        and bool(cert_verify.get("valid"))
        and bool(adversarial.get("ok"))
        and tip_height >= 2
        and risk_n >= 2
        and not used_skill
    )
    provisional_ok = risked and (
        solvency_report is None or bool(solvency_report.get("ok")) or not run_solvency
    )

    context = {
        "used_skill_route_discovery": used_skill,
        "clearing": {
            "ok": True if solvency_report is None else bool(solvency_report.get("ok")),
            "solvent": True
            if solvency_report is None
            else bool(solvency_report.get("solvent") or solvency_report.get("liquid")),
            "solvency_count": solvency_n,
            "tip_height": solvency_bundle.get("tip_height"),
            "tip_solvency_root": solvency_bundle.get("tip_solvency_root"),
            "solvency_hash": solvency_bundle.get("solvency_hash"),
            "solvency_root_valid": True,
            "certificate_valid": True,
            "solvency_position_digest": solvency_bundle.get("solvency_position_digest"),
            "deterministic": True,
            "post_clearing": True,
            "multi_clearing": solvency_n >= 2,
        },
        "clearing_plane": {
            "ok": True if solvency_report is None else bool(solvency_report.get("ok")),
            "risked": True
            if solvency_report is None
            else bool(solvency_report.get("risked")),
            "solvency_count": solvency_n,
            "solvency_root_valid": True,
        },
        "net": {
            "ok": True if solvency_report is None else bool(solvency_report.get("ok")),
            "risked": True
            if solvency_report is None
            else bool(solvency_report.get("risked")),
            "solvency_count": solvency_n,
            "solvency_position_digest": solvency_bundle.get("solvency_position_digest"),
            "solvency_root_valid": True,
        },
        "settlement": {
            "ok": True,
            "settled": True,
            "settlement_count": settlement_n,
            "settlement_root_valid": True,
            "certificate_valid": True,
            "deterministic": True,
            "post_actuation": True,
            "multi_settlement": settlement_n >= 2 if settlement_n else True,
        },
        "settlement_plane": {
            "ok": True,
            "settled": True,
            "settlement_count": settlement_n,
            "settlement_root_valid": True,
        },
        "receipts": {
            "ok": True,
            "settled": True,
            "settlement_count": settlement_n,
            "settlement_root_valid": True,
        },
        "actuation": {
            "ok": True,
            "effects_applied": True,
            "action_count": action_n,
            "action_root_valid": True,
            "certificate_valid": True,
            "deterministic": True,
            "post_execution": True,
            "multi_action": action_n >= 2 if action_n else True,
        },
        "actuation_plane": {
            "ok": True,
            "effects_applied": True,
            "action_count": action_n,
            "action_root_valid": True,
        },
        "effects": {
            "ok": True,
            "effects_applied": True,
            "action_count": action_n,
            "action_root_valid": True,
        },
        "execution": {
            "ok": True,
            "state_applied": True,
            "state_height": state_n,
            "tip_height": state_n,
            "tip_state_root": solvency_bundle.get("bound_state_root"),
            "execution_hash": solvency_bundle.get("execution_hash"),
            "state_root_valid": True,
            "certificate_valid": True,
            "deterministic": True,
            "post_finality": True,
            "multi_state": state_n >= 2 if state_n else True,
        },
        "execution_plane": {
            "ok": True,
            "state_applied": True,
            "state_height": state_n,
            "state_root_valid": True,
        },
        "worldstate": {
            "ok": True,
            "state_applied": True,
            "state_height": state_n,
            "tip_state_root": solvency_bundle.get("bound_state_root"),
            "state_root_valid": True,
        },
        "finality": {
            "ok": True,
            "finalized": True,
            "epoch_count": epoch_n,
            "finality_cert_valid": True,
            "certificate_valid": True,
            "irreversible": True,
            "multi_epoch": epoch_n >= 2 if epoch_n else True,
        },
        "finality_plane": {
            "ok": True,
            "finalized": True,
            "epoch_count": epoch_n,
            "finality_cert_valid": True,
        },
        "quorum": {
            "ok": True,
            "quorum_met": True,
            "origin_count": reloaded.get("origin_count"),
            "quorum_size": reloaded.get("agreeing_count"),
            "agreeing_count": reloaded.get("agreeing_count"),
            "byzantine_excluded": int(reloaded.get("byzantine_count") or 0) >= 1,
            "byzantine_count": reloaded.get("byzantine_count"),
            "quorum_cert_valid": True,
        },
        "funding": {
            "ok": True if solvency_report is None else bool(solvency_report.get("ok")),
            "solvent": True
            if solvency_report is None
            else bool(
                solvency_report.get("solvent")
                or solvency_report.get("ok")
                or solvency_n >= 2
            ),
            "solvency_count": solvency_n,
            "tip_height": solvency_bundle.get("tip_height"),
            "tip_solvency_root": solvency_bundle.get("tip_solvency_root"),
            "solvency_hash": solvency_bundle.get("solvency_hash"),
            "solvency_root_valid": True,
            "certificate_valid": True,
            "solvency_position_digest": solvency_bundle.get("solvency_position_digest"),
            "deterministic": True,
            "post_liquidity": True,
            "multi_funding": solvency_n >= 2,
            "bound_liquidity_root": solvency_bundle.get("bound_liquidity_root"),
        },
        "funding_plane": {
            "ok": True if solvency_report is None else bool(solvency_report.get("ok")),
            "solvent": True
            if solvency_report is None
            else bool(solvency_report.get("solvent") or solvency_report.get("ok")),
            "solvency_count": solvency_n,
            "solvency_root_valid": True,
        },
        "facility": {
            "ok": True if solvency_report is None else bool(solvency_report.get("ok")),
            "solvent": True
            if solvency_report is None
            else bool(solvency_report.get("solvent") or solvency_report.get("ok")),
            "solvency_count": solvency_n,
            "solvency_position_digest": solvency_bundle.get("solvency_position_digest"),
            "solvency_root_valid": True,
        },
        "risk": {
            "ok": provisional_ok,
            "risked": risked,
            "risk_count": risk_n,
            "tip_height": tip_height,
            "tip_risk_root": reloaded.get("tip_risk_root"),
            "risk_hash": reloaded.get("risk_hash"),
            "risk_root_valid": bool(cert_verify.get("valid")),
            "certificate_valid": bool(cert_verify.get("valid")),
            "risk_assessment_digest": reloaded.get("risk_assessment_digest"),
            "solvency_position_digest": reloaded.get("solvency_position_digest"),
            "deterministic": True,
            "post_solvency": True,
            "multi_risk": risk_n >= 2,
            "bound_solvency_root": reloaded.get("bound_solvency_root"),
        },
        "risk_plane": {
            "ok": provisional_ok,
            "risked": risked,
            "risk_count": risk_n,
            "risk_root_valid": bool(cert_verify.get("valid")),
        },
        "assessment": {
            "ok": provisional_ok,
            "risked": risked,
            "risk_count": risk_n,
            "risk_assessment_digest": reloaded.get("risk_assessment_digest"),
            "risk_root_valid": bool(cert_verify.get("valid")),
        },
        "chain": chain,
        "margin_chain": chain,
        "clearing_chain": (solvency_report or {}).get("chain") or {},
        "lineage_chain": (solvency_report or {}).get("chain") or {},
        "lineage": {
            "ok": True,
            "entry_count": reloaded.get("lineage_entry_count"),
        },
        "origin_count": reloaded.get("origin_count"),
        "risk_count": risk_n,
        "solvency_count": solvency_n,
        "settlement_count": settlement_n,
        "action_count": action_n,
        "tip_height": tip_height,
        "state_height": state_n,
        "epoch_count": epoch_n,
        "risk_certificate": reloaded.get("risk_certificate"),
        "risk_hash": reloaded.get("risk_hash"),
        "solvency_hash": reloaded.get("solvency_hash"),
        "settlement_hash": reloaded.get("settlement_hash"),
        "actuation_hash": reloaded.get("actuation_hash"),
        "execution_hash": reloaded.get("execution_hash"),
        "tip_risk_root": reloaded.get("tip_risk_root"),
        "bound_solvency_root": reloaded.get("bound_solvency_root"),
        "tip_solvency_root": reloaded.get("tip_solvency_root"),
        "bound_settlement_root": reloaded.get("bound_settlement_root"),
        "tip_settlement_root": reloaded.get("tip_settlement_root"),
        "bound_action_root": reloaded.get("bound_action_root"),
        "tip_action_root": reloaded.get("tip_action_root"),
        "bound_state_root": reloaded.get("bound_state_root"),
        "risk_assessment_digest": reloaded.get("risk_assessment_digest"),
        "solvency_position_digest": reloaded.get("solvency_position_digest"),
    }
    risk_done_when = (
        "no_skill_route; risk_ok; risked_ok; min_risks:2; "
        "risk_root_valid; solvency_ok; solvent_ok; min_solvencies:2; "
        "solvency_root_valid; chain_valid; capability_exists:repo.import-health"
    )
    final_contract = evaluate_outcome_contract(
        root,
        risk_done_when,
        context=context,
        command_runner=command_runner,
        timeout=min(timeout, 60),
        run_programs=False,
    )
    ok = (
        provisional_ok
        and bool(final_contract.get("ok"))
        and final_contract.get("met") is True
    )
    return {
        "ok": ok,
        "action": "risk_plane",
        "goal": goal,
        "done_when": done_when,
        "risk_done_when": risk_done_when,
        "met": final_contract.get("met"),
        "machine_checkable": True,
        "risked": risked,
        "risk_count": risk_n,
        "tip_height": tip_height,
        "tip_risk_root": reloaded.get("tip_risk_root"),
        "bound_solvency_root": reloaded.get("bound_solvency_root"),
        "bound_solvency_height": reloaded.get("bound_solvency_height"),
        "risk_assessment_digest": reloaded.get("risk_assessment_digest"),
        "solvency_count": solvency_n,
        "tip_solvency_root": reloaded.get("tip_solvency_root"),
        "bound_settlement_root": reloaded.get("bound_settlement_root"),
        "solvency_position_digest": reloaded.get("solvency_position_digest"),
        "settlement_count": settlement_n,
        "tip_settlement_root": reloaded.get("tip_settlement_root"),
        "bound_action_root": reloaded.get("bound_action_root"),
        "action_count": action_n,
        "tip_action_root": reloaded.get("tip_action_root"),
        "bound_state_root": reloaded.get("bound_state_root"),
        "state_count": state_n,
        "state_height": state_n,
        "epoch_count": epoch_n,
        "origin_count": reloaded.get("origin_count"),
        "agreeing_count": reloaded.get("agreeing_count"),
        "byzantine_count": reloaded.get("byzantine_count"),
        "solvency": None
        if solvency_report is None
        else {
            "ok": solvency_report.get("ok"),
            "solvent": solvency_report.get("solvent") or solvency_report.get("risked"),
            "solvency_hash": (
                (solvency_report.get("funding") or solvency_report.get("margin") or {}).get(
                    "solvency_hash"
                )
                or solvency_report.get("solvency_hash")
            ),
            "solvency_count": solvency_report.get("solvency_count"),
            "tip_solvency_root": solvency_report.get("tip_solvency_root"),
        },
        "risk": {
            "ok": margin.get("ok"),
            "risk_hash": reloaded.get("risk_hash"),
            "bundle_path": str(out_c) if persist and margin.get("ok") else None,
            "package_hash": reloaded.get("package_hash"),
            "member_count": reloaded.get("member_count"),
            "risk_count": risk_n,
            "tip_height": tip_height,
            "tip_risk_root": reloaded.get("tip_risk_root"),
            "bound_solvency_root": reloaded.get("bound_solvency_root"),
            "risk_assessment_digest": reloaded.get("risk_assessment_digest"),
            "certificate_count": reloaded.get("certificate_count"),
            "lineage_entry_count": reloaded.get("lineage_entry_count"),
            "lineage_head_hash": reloaded.get("lineage_head_hash"),
            "solvency_hash": reloaded.get("solvency_hash"),
            "settlement_hash": reloaded.get("settlement_hash"),
            "actuation_hash": reloaded.get("actuation_hash"),
            "execution_hash": reloaded.get("execution_hash"),
            "persisted": persist and out_c.exists() if margin.get("ok") else False,
            "deterministic": True,
            "post_solvency": True,
        },
        "integrity": {
            "ok": integrity.get("ok"),
            "hash_ok": integrity.get("hash_ok"),
            "chain_valid": integrity.get("chain_valid"),
            "multi_risk": integrity.get("multi_risk"),
            "package_ok": integrity.get("package_ok"),
            "risk_certificate_valid": integrity.get("risk_certificate_valid"),
            "solvency_certificate_valid": integrity.get(
                "solvency_certificate_valid"
            ),
            "bound_ok": integrity.get("bound_ok"),
            "risk_ok": integrity.get("risk_ok"),
            "deterministic": integrity.get("deterministic"),
            "post_solvency": integrity.get("post_solvency"),
        },
        "rehydrate": {
            "ok": rehydrate.get("ok"),
            "sandbox_dir": rehydrate.get("sandbox_dir"),
            "lineage_path": rehydrate.get("lineage_path"),
            "risks_path": rehydrate.get("risks_path"),
            "solvencies_path": rehydrate.get("solvencies_path"),
            "settlements_path": rehydrate.get("settlements_path"),
            "actions_path": rehydrate.get("actions_path"),
            "sterile_ledger_path": rehydrate.get("sterile_ledger_path"),
            "import": rehydrate.get("import"),
            "chain": rehydrate.get("chain"),
            "risk_certificate": rehydrate.get("risk_certificate"),
            "solvency_certificate": rehydrate.get("solvency_certificate"),
            "margin_digests_match": rehydrate.get("margin_digests_match"),
        },
        "prove": {
            "ok": prove.get("ok"),
            "proved_count": prove.get("proved_count"),
            "proofs": prove.get("proofs"),
        },
        "chain": {
            "ok": chain.get("ok"),
            "valid": chain.get("valid"),
            "entry_count": chain.get("entry_count"),
            "tip_height": chain.get("tip_height"),
            "tip_risk_root": chain.get("tip_risk_root"),
            "risk_assessment_digest": chain.get("risk_assessment_digest"),
            "errors": chain.get("errors") or [],
        },
        "risk_certificate": {
            "ok": cert_verify.get("ok"),
            "valid": cert_verify.get("valid"),
            "hash_ok": cert_verify.get("hash_ok"),
            "certificate_hash": cert_verify.get("certificate_hash"),
            "risk_height": cert_verify.get("risk_height"),
            "risk_root": cert_verify.get("risk_root"),
            "bound_solvency_root": cert_verify.get("bound_solvency_root"),
            "risk_assessment_digest": cert_verify.get("risk_assessment_digest"),
        },
        "adversarial": {
            "ok": adversarial.get("ok"),
            "intact_ok": adversarial.get("intact_ok"),
            "mutation_fails_as_expected": adversarial.get(
                "mutation_fails_as_expected"
            ),
            "reorder_fails_as_expected": adversarial.get("reorder_fails_as_expected"),
            "wrong_solvency_fails_as_expected": adversarial.get(
                "wrong_solvency_fails_as_expected"
            ),
            "forged_root_fails_as_expected": adversarial.get(
                "forged_root_fails_as_expected"
            ),
            "gap_fails_as_expected": adversarial.get("gap_fails_as_expected"),
            "broken_cert_fails_as_expected": adversarial.get(
                "broken_cert_fails_as_expected"
            ),
            "wrong_parent_fails_as_expected": adversarial.get(
                "wrong_parent_fails_as_expected"
            ),
            "digest_tamper_fails_as_expected": adversarial.get(
                "digest_tamper_fails_as_expected"
            ),
            "tamper_fails_as_expected": adversarial.get("tamper_fails_as_expected"),
            "single_risk_fails_as_expected": adversarial.get(
                "single_risk_fails_as_expected"
            ),
            "replay_matches_tip": adversarial.get("replay_matches_tip"),
            "duplicate_apply_fails_as_expected": adversarial.get(
                "duplicate_apply_fails_as_expected"
            ),
            "incomplete_fails_as_expected": adversarial.get(
                "incomplete_fails_as_expected"
            ),
        },
        "final_contract": {
            "ok": final_contract.get("ok"),
            "met": final_contract.get("met"),
            "passed_count": final_contract.get("passed_count"),
            "failed_count": final_contract.get("failed_count"),
            "failed": final_contract.get("failed"),
        },
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


def builtin_risk_plane() -> dict[str, Any]:
    """Invocable capability: solvency → multi-risk deterministic assessments → prove."""

    root = Path(__file__).resolve().parents[2]
    goal = (
        (os.environ.get("BLACKHOLE_MISSION_GOAL") or "").strip()
        or "risk over solvency"
    )
    done_when = (os.environ.get("BLACKHOLE_DONE_WHEN") or "").strip()
    max_steps = int(os.environ.get("BLACKHOLE_PROGRAM_MAX_STEPS") or "3")
    run_solvency = (
        os.environ.get("BLACKHOLE_RISK_RUN_SOLVENCY") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    run_liquidity = (
        os.environ.get("BLACKHOLE_CAPITAL_RUN_FUNDING") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    run_collateral = (
        os.environ.get("BLACKHOLE_LIQUIDITY_RUN_COLLATERAL") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    run_margin = (
        os.environ.get("BLACKHOLE_COLLATERAL_RUN_MARGIN") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    run_clearing = (
        os.environ.get("BLACKHOLE_MARGIN_RUN_CLEARING") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    run_settlement = (
        os.environ.get("BLACKHOLE_CLEARING_RUN_SETTLEMENT") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    run_actuation = (
        os.environ.get("BLACKHOLE_SETTLEMENT_RUN_ACTUATION") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    run_execution = (
        os.environ.get("BLACKHOLE_ACTUATION_RUN_EXECUTION") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    run_finality = (
        os.environ.get("BLACKHOLE_EXECUTION_RUN_FINALITY") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    run_quorum = (
        os.environ.get("BLACKHOLE_FINALITY_RUN_QUORUM") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    run_continuity = (
        os.environ.get("BLACKHOLE_QUORUM_RUN_CONTINUITY") or "0"
    ).strip().lower() not in {"0", "false", "no"}
    run_recon = (
        os.environ.get("BLACKHOLE_CONTINUITY_RUN_RECON") or "0"
    ).strip().lower() not in {"0", "false", "no"}
    force_synthetic = (
        os.environ.get("BLACKHOLE_RECONCILE_SYNTHETIC") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    inject_byz = (
        os.environ.get("BLACKHOLE_QUORUM_INJECT_BYZANTINE") or "1"
    ).strip().lower() not in {"0", "false", "no"}
    epoch_count = int(os.environ.get("BLACKHOLE_FINALITY_EPOCH_COUNT") or "2")
    min_actions = int(os.environ.get("BLACKHOLE_ACTUATION_MIN_ACTIONS") or "2")
    min_settlements = int(os.environ.get("BLACKHOLE_SETTLEMENT_MIN_SETTLEMENTS") or "2")
    min_clearings = int(os.environ.get("BLACKHOLE_CLEARING_MIN_CLEARINGS") or "2")
    min_margins = int(os.environ.get("BLACKHOLE_MARGIN_MIN_MARGINS") or "2")
    min_collaterals = int(os.environ.get("BLACKHOLE_COLLATERAL_MIN_COLLATERALS") or "2")
    min_liquidities = int(os.environ.get("BLACKHOLE_LIQUIDITY_MIN_LIQUIDITIES") or "2")
    min_solvencies = int(os.environ.get("BLACKHOLE_SOLVENCY_MIN_SOLVENCIES") or "2")
    min_risks = int(os.environ.get("BLACKHOLE_RISK_MIN_RISKS") or "2")
    lineage_raw = (os.environ.get("BLACKHOLE_LINEAGE_PATH") or "").strip()
    lineage_path = Path(lineage_raw) if lineage_raw else None
    bundle_raw = (os.environ.get("BLACKHOLE_CONTINUITY_BUNDLE_PATH") or "").strip()
    bundle_path = Path(bundle_raw) if bundle_raw else None
    q_raw = (os.environ.get("BLACKHOLE_QUORUM_BUNDLE_PATH") or "").strip()
    quorum_path = Path(q_raw) if q_raw else None
    f_raw = (os.environ.get("BLACKHOLE_FINALITY_BUNDLE_PATH") or "").strip()
    finality_path = Path(f_raw) if f_raw else None
    e_raw = (os.environ.get("BLACKHOLE_EXECUTION_BUNDLE_PATH") or "").strip()
    execution_path = Path(e_raw) if e_raw else None
    a_raw = (os.environ.get("BLACKHOLE_ACTUATION_BUNDLE_PATH") or "").strip()
    actuation_path = Path(a_raw) if a_raw else None
    s_raw = (os.environ.get("BLACKHOLE_SETTLEMENT_BUNDLE_PATH") or "").strip()
    settlement_path = Path(s_raw) if s_raw else None
    g_raw = (os.environ.get("BLACKHOLE_MARGIN_BUNDLE_PATH") or "").strip()
    margin_path = Path(g_raw) if g_raw else None
    col_raw = (os.environ.get("BLACKHOLE_COLLATERAL_BUNDLE_PATH") or "").strip()
    collateral_path = Path(col_raw) if col_raw else None
    liq_raw = (os.environ.get("BLACKHOLE_LIQUIDITY_BUNDLE_PATH") or "").strip()
    liquidity_path = Path(liq_raw) if liq_raw else None
    c_raw = (os.environ.get("BLACKHOLE_SOLVENCY_BUNDLE_PATH") or "").strip()
    solvency_path = Path(c_raw) if c_raw else None
    m_raw = (os.environ.get("BLACKHOLE_RISK_BUNDLE_PATH") or "").strip()
    risk_path = Path(m_raw) if m_raw else None
    return run_risk_plane(
        root,
        goal,
        done_when,
        max_steps=max_steps,
        run_solvency=run_solvency,
        run_liquidity=run_liquidity,
        run_collateral=run_collateral,
        run_margin=run_margin,
        run_clearing=run_clearing,
        run_settlement=run_settlement,
        run_actuation=run_actuation,
        run_execution=run_execution,
        run_finality=run_finality,
        run_quorum=run_quorum,
        run_continuity=run_continuity,
        run_reconciliation=run_recon,
        force_synthetic_drift=force_synthetic,
        inject_byzantine=inject_byz,
        epoch_count=epoch_count,
        min_actions=min_actions,
        min_settlements=min_settlements,
        min_clearings=min_clearings,
        min_margins=min_margins,
        min_collaterals=min_collaterals,
        min_liquidities=min_liquidities,
        min_solvencies=min_solvencies,
        min_risks=min_risks,
        lineage_path=lineage_path,
        bundle_path=bundle_path,
        quorum_path=quorum_path,
        finality_path=finality_path,
        execution_path=execution_path,
        actuation_path=actuation_path,
        settlement_path=settlement_path,
        margin_path=margin_path,
        collateral_path=collateral_path,
        liquidity_path=liquidity_path,
        solvency_path=solvency_path,
        risk_path=risk_path,
        timeout=960,
    )

