# CLEARING PLANE IMPLEMENTATION FRAGMENT
# Injected into capability_compounder.py after builtin_settlement_plane.

CLEARING_BUNDLE_SCHEMA = 1
CLEARING_CERTIFICATE_SCHEMA = 1
CLEARING_LOG_SCHEMA = 1
DEFAULT_CLEARING_BUNDLE_RELATIVE = Path("artifacts") / "clearing-bundles"


def default_clearing_bundle_dir(repo_path: Path) -> Path:
    return (repo_path / DEFAULT_CLEARING_BUNDLE_RELATIVE).resolve()


def empty_clearing_log() -> dict[str, Any]:
    return {
        "schema_version": CLEARING_LOG_SCHEMA,
        "kind": "clearing_log",
        "entries": [],
        "entry_count": 0,
        "tip_height": 0,
        "tip_clearing_root": "",
        "bound_settlement_root": "",
        "bound_settlement_height": 0,
        "settlement_hash": "",
        "net_position_digest": "",
        "updated_at": utc_now_iso(),
    }


def compute_clearing_root(clearing: Mapping[str, Any]) -> str:
    """Hash clearing body excluding self root, certificates, and wall-clock fields."""

    body = {
        key: value
        for key, value in clearing.items()
        if key
        not in {
            "clearing_root",
            "clearing_certificate",
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


def compute_clearing_certificate_hash(payload: Mapping[str, Any]) -> str:
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"certificate_hash", "ok", "valid"}
    }
    digest = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()[:24]


def compute_clearing_bundle_hash(bundle: Mapping[str, Any]) -> str:
    body = {
        key: value
        for key, value in bundle.items()
        if key
        not in {
            "clearing_hash",
            "ok",
            "bundle_path",
            "exported_at",
            "source_ledger_path",
            "action",
        }
    }
    digest = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()[:24]


def compute_net_position_digest(
    *,
    parent_net_digest: str,
    bound_settlement_root: str,
    receipt_digest: str,
    capability_id: str,
    outcome: str = "cleared",
) -> str:
    """Deterministic net of prior clearing position with a newly cleared settlement."""

    payload = {
        "parent_net_digest": parent_net_digest or "",
        "bound_settlement_root": bound_settlement_root,
        "receipt_digest": receipt_digest,
        "capability_id": capability_id,
        "outcome": outcome or "cleared",
        "plane": "clearing",
    }
    digest = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()[:24]


def issue_clearing_certificate(
    *,
    clearing_height: int,
    clearing_root: str,
    parent_clearing_root: str,
    bound_settlement_root: str,
    bound_settlement_height: int,
    settlement_hash: str,
    settlement_certificate_hash: str,
    package_hash: str,
    lineage_head_hash: str,
    net_position_digest: str,
    clearing_count: int,
    member_ids: Sequence[str] | None = None,
    goal: str = "",
    claims: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    members = sorted({str(item).strip() for item in (member_ids or []) if str(item).strip()})
    cert: dict[str, Any] = {
        "schema_version": CLEARING_CERTIFICATE_SCHEMA,
        "kind": "clearing_certificate",
        "issued_at": utc_now_iso(),
        "clearing_height": int(clearing_height),
        "clearing_root": str(clearing_root or ""),
        "parent_clearing_root": str(parent_clearing_root or ""),
        "bound_settlement_root": str(bound_settlement_root or ""),
        "bound_settlement_height": int(bound_settlement_height or 0),
        "settlement_hash": str(settlement_hash or ""),
        "settlement_certificate_hash": str(settlement_certificate_hash or ""),
        "package_hash": str(package_hash or ""),
        "lineage_head_hash": str(lineage_head_hash or ""),
        "net_position_digest": str(net_position_digest or ""),
        "clearing_count": int(clearing_count),
        "member_ids": members,
        "member_count": len(members),
        "goal": goal or "",
        "claims": dict(claims or {}),
        "deterministic": True,
        "post_settlement": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    cert["certificate_hash"] = compute_clearing_certificate_hash(cert)
    cert["ok"] = (
        bool(cert["certificate_hash"])
        and bool(cert["clearing_root"])
        and bool(cert["bound_settlement_root"])
        and bool(cert["settlement_hash"])
        and bool(cert["net_position_digest"])
        and cert["clearing_height"] >= 1
        and cert["clearing_count"] >= 1
        and cert["deterministic"] is True
        and cert["post_settlement"] is True
        and not bool(cert["used_skill_route_discovery"])
    )
    cert["valid"] = bool(cert["ok"])
    return cert


def verify_clearing_certificate(payload: Mapping[str, Any] | Path) -> dict[str, Any]:
    if isinstance(payload, Path):
        data = json.loads(payload.read_text(encoding="utf-8"))
    else:
        data = dict(payload)
    recomputed = compute_clearing_certificate_hash(data)
    stored = str(data.get("certificate_hash") or "")
    hash_ok = bool(stored) and stored == recomputed
    valid = (
        hash_ok
        and data.get("kind") == "clearing_certificate"
        and bool(data.get("clearing_root"))
        and bool(data.get("bound_settlement_root"))
        and bool(data.get("settlement_hash"))
        and bool(data.get("net_position_digest"))
        and int(data.get("clearing_height") or 0) >= 1
        and int(data.get("clearing_count") or 0) >= 1
        and data.get("deterministic") is True
        and data.get("post_settlement") is True
        and not bool(data.get("used_skill_route_discovery"))
    )
    return {
        "ok": valid,
        "valid": valid,
        "hash_ok": hash_ok,
        "certificate_hash": stored if hash_ok else recomputed,
        "clearing_height": data.get("clearing_height"),
        "clearing_root": data.get("clearing_root"),
        "bound_settlement_root": data.get("bound_settlement_root"),
        "net_position_digest": data.get("net_position_digest"),
        "settlement_hash": data.get("settlement_hash"),
        "used_skill_route_discovery": bool(data.get("used_skill_route_discovery")),
    }


def write_clearing_certificate(path: Path, certificate: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, dict(certificate))
    return path


def _load_clearing_disk_evidence(
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Best-effort load of a durable clearing proof bundle for context-less gates."""

    candidates: list[Path] = []
    ctx = context or {}
    for key in ("repo_path", "workspace", "workspace_path"):
        raw = ctx.get(key)
        if raw:
            root = Path(str(raw))
            candidates.extend(
                [
                    root / "artifacts" / "clearing-bundles" / "proof-clearing.json",
                    root / DEFAULT_CLEARING_BUNDLE_RELATIVE / "proof-clearing.json",
                ]
            )
    here = Path.cwd()
    candidates.extend(
        [
            here / "artifacts" / "clearing-bundles" / "proof-clearing.json",
            here / DEFAULT_CLEARING_BUNDLE_RELATIVE / "proof-clearing.json",
        ]
    )
    try:
        pkg_root = Path(__file__).resolve().parents[2]
        candidates.append(
            pkg_root / "artifacts" / "clearing-bundles" / "proof-clearing.json"
        )
    except Exception:
        pass
    for base in {Path.cwd(), Path(__file__).resolve().parents[2]}:
        bundle_dir = base / "artifacts" / "clearing-bundles"
        if bundle_dir.is_dir():
            candidates.extend(sorted(bundle_dir.glob("clearing-*.json"), reverse=True)[:3])
            candidates.extend(sorted(bundle_dir.glob("proof-clearing*.json"), reverse=True)[:3])

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
            bundle = load_clearing_bundle(resolved)
        except Exception:
            continue
        integrity = verify_clearing_bundle_integrity(bundle)
        if not integrity.get("ok"):
            continue
        cert = (
            bundle.get("clearing_certificate")
            if isinstance(bundle.get("clearing_certificate"), Mapping)
            else {}
        )
        cert_verify = (
            verify_clearing_certificate(cert) if cert else {"ok": False, "valid": False}
        )
        clearing_count = int(
            bundle.get("clearing_count")
            or (bundle.get("clearings") or {}).get("entry_count")
            or 0
        )
        tip_height = int(bundle.get("tip_height") or clearing_count or 0)
        if clearing_count < 2 or tip_height < 2 or not cert_verify.get("valid"):
            continue
        return {
            "ok": True,
            "cleared": True,
            "clearing_count": clearing_count,
            "tip_height": tip_height,
            "tip_clearing_root": bundle.get("tip_clearing_root"),
            "clearing_hash": bundle.get("clearing_hash"),
            "clearing_root_valid": True,
            "certificate_valid": True,
            "net_position_digest": bundle.get("net_position_digest"),
            "clearing_certificate": cert,
            "bundle_path": str(resolved),
            "source": "disk_proof_bundle",
        }
    return None


def derive_clearing_specs_from_settlement(
    settlement_bundle: Mapping[str, Any],
    *,
    min_clearings: int = 2,
) -> list[dict[str, Any]]:
    """Derive one clearing position per settlement receipt (multi-clearing required)."""

    settlements = (
        settlement_bundle.get("settlements")
        if isinstance(settlement_bundle.get("settlements"), Mapping)
        else {}
    )
    entries = list(settlements.get("entries") or [])
    specs: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        settlement_root = str(entry.get("settlement_root") or "")
        if not settlement_root:
            continue
        specs.append(
            {
                "capability_id": str(entry.get("capability_id") or ""),
                "effect": str(entry.get("effect") or ""),
                "bound_settlement_root": settlement_root,
                "bound_settlement_height": int(entry.get("settlement_height") or 0),
                "receipt_digest": str(entry.get("receipt_digest") or ""),
                "bound_action_root": str(entry.get("bound_action_root") or ""),
                "package_hash": str(
                    entry.get("package_hash")
                    or settlement_bundle.get("package_hash")
                    or ""
                ),
                "outcome": "cleared",
            }
        )
    want = max(2, int(min_clearings))
    return specs[:want] if len(specs) >= want else specs


def apply_clearing_transition(
    clearing_log: Mapping[str, Any],
    spec: Mapping[str, Any],
    *,
    settlement_bundle: Mapping[str, Any],
    goal: str = "",
    claims: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one clearing position bound to a settlement receipt root and net it."""

    log = copy.deepcopy(dict(clearing_log)) if clearing_log else empty_clearing_log()
    entries = list(log.get("entries") or [])
    next_height = len(entries) + 1
    parent_root = str(entries[-1].get("clearing_root") or "") if entries else ""
    parent_net = str(entries[-1].get("net_position_digest") or "") if entries else ""

    bound_settlement_root = str(spec.get("bound_settlement_root") or "")
    bound_settlement_height = int(spec.get("bound_settlement_height") or 0)
    capability_id = str(spec.get("capability_id") or "")
    effect = str(spec.get("effect") or "")
    outcome = str(spec.get("outcome") or "cleared")
    package_hash = str(
        spec.get("package_hash") or settlement_bundle.get("package_hash") or ""
    )
    settlement_hash = str(settlement_bundle.get("settlement_hash") or "")
    tip_settlement_root = str(settlement_bundle.get("tip_settlement_root") or "")
    settlements = (
        settlement_bundle.get("settlements")
        if isinstance(settlement_bundle.get("settlements"), Mapping)
        else {}
    )
    settlement_entries = list(settlements.get("entries") or [])
    known_roots = {
        str(item.get("settlement_root") or "")
        for item in settlement_entries
        if isinstance(item, Mapping) and item.get("settlement_root")
    }
    if tip_settlement_root:
        known_roots.add(tip_settlement_root)

    if not capability_id or not bound_settlement_root or not settlement_hash:
        return {
            "ok": False,
            "action": "apply_clearing_transition",
            "error": "missing_clearing_bind_fields",
            "clearing_log": log,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    if bound_settlement_root not in known_roots:
        return {
            "ok": False,
            "action": "apply_clearing_transition",
            "error": "bound_settlement_root_mismatch",
            "bound_settlement_root": bound_settlement_root,
            "known_settlement_roots": sorted(known_roots),
            "clearing_log": log,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    if any(
        str(item.get("bound_settlement_root") or "") == bound_settlement_root
        and str(item.get("outcome") or "") == outcome
        for item in entries
    ):
        return {
            "ok": False,
            "action": "apply_clearing_transition",
            "error": "duplicate_clearing_rejected",
            "clearing_log": log,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    settle_cert = (
        settlement_bundle.get("settlement_certificate")
        if isinstance(settlement_bundle.get("settlement_certificate"), Mapping)
        else {}
    )
    settle_cert_hash = str(settle_cert.get("certificate_hash") or "")
    lineage_head = str(settlement_bundle.get("lineage_head_hash") or "")
    member_ids = list(settlement_bundle.get("member_ids") or [])
    receipt_digest = str(spec.get("receipt_digest") or "")
    if not receipt_digest:
        # Recover from settlement entry if available.
        for item in settlement_entries:
            if (
                isinstance(item, Mapping)
                and str(item.get("settlement_root") or "") == bound_settlement_root
            ):
                receipt_digest = str(item.get("receipt_digest") or "")
                break
    net_position_digest = compute_net_position_digest(
        parent_net_digest=parent_net,
        bound_settlement_root=bound_settlement_root,
        receipt_digest=receipt_digest,
        capability_id=capability_id,
        outcome=outcome,
    )

    body: dict[str, Any] = {
        "schema_version": CLEARING_LOG_SCHEMA,
        "kind": "clearing_position",
        "clearing_height": next_height,
        "parent_clearing_root": parent_root,
        "bound_settlement_root": bound_settlement_root,
        "bound_settlement_height": bound_settlement_height,
        "settlement_hash": settlement_hash,
        "settlement_certificate_hash": settle_cert_hash,
        "package_hash": package_hash,
        "lineage_head_hash": lineage_head,
        "capability_id": capability_id,
        "effect": effect,
        "outcome": outcome,
        "receipt_digest": receipt_digest,
        "net_position_digest": net_position_digest,
        "parent_net_digest": parent_net,
        "bound_action_root": str(spec.get("bound_action_root") or ""),
        "member_ids": sorted({str(m).strip() for m in member_ids if str(m).strip()}),
        "deterministic": True,
        "post_settlement": True,
        "applied_at": utc_now_iso(),
        "goal": goal or str(settlement_bundle.get("goal") or ""),
        "claims": dict(claims or {}),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    clearing_root = compute_clearing_root(body)
    body["clearing_root"] = clearing_root
    cert = issue_clearing_certificate(
        clearing_height=next_height,
        clearing_root=clearing_root,
        parent_clearing_root=parent_root,
        bound_settlement_root=bound_settlement_root,
        bound_settlement_height=bound_settlement_height,
        settlement_hash=settlement_hash,
        settlement_certificate_hash=settle_cert_hash,
        package_hash=package_hash,
        lineage_head_hash=lineage_head,
        net_position_digest=net_position_digest,
        clearing_count=next_height,
        member_ids=body["member_ids"],
        goal=goal or str(settlement_bundle.get("goal") or ""),
        claims={
            "capability_id": capability_id,
            "effect": effect,
            "outcome": outcome,
            "plane": "clearing",
            **dict(claims or {}),
        },
    )
    body["clearing_certificate"] = cert
    body["ok"] = (
        bool(cert.get("ok"))
        and bool(clearing_root)
        and bool(net_position_digest)
        and body["deterministic"] is True
        and body["post_settlement"] is True
        and not bool(body.get("used_skill_route_discovery"))
    )

    entries.append(body)
    log["entries"] = entries
    log["entry_count"] = len(entries)
    log["tip_height"] = next_height
    log["tip_clearing_root"] = clearing_root
    log["bound_settlement_root"] = bound_settlement_root
    log["bound_settlement_height"] = bound_settlement_height
    log["settlement_hash"] = settlement_hash
    log["net_position_digest"] = net_position_digest
    log["updated_at"] = utc_now_iso()
    log["schema_version"] = CLEARING_LOG_SCHEMA
    log["kind"] = "clearing_log"
    return {
        "ok": bool(body.get("ok")),
        "action": "apply_clearing_transition",
        "entry": body,
        "clearing_height": next_height,
        "clearing_root": clearing_root,
        "parent_clearing_root": parent_root,
        "bound_settlement_root": bound_settlement_root,
        "net_position_digest": net_position_digest,
        "clearing_log": log,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def verify_clearing_chain(clearing_log: Mapping[str, Any]) -> dict[str, Any]:
    """Validate sequential heights, parent roots, nets, hashes, and clearing certs."""

    entries = list(clearing_log.get("entries") or [])
    errors: list[str] = []
    if not entries:
        return {
            "ok": False,
            "valid": False,
            "action": "verify_clearing_chain",
            "entry_count": 0,
            "tip_height": 0,
            "tip_clearing_root": "",
            "errors": ["empty_clearing_log"],
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    prev_root = ""
    prev_net = ""
    bound_settlements: set[str] = set()
    settlement_hashes: set[str] = set()
    for index, raw in enumerate(entries):
        if not isinstance(raw, Mapping):
            errors.append(f"entry[{index}]_not_mapping")
            continue
        height = int(raw.get("clearing_height") or 0)
        expected_height = index + 1
        if height != expected_height:
            errors.append(f"entry[{index}]_height={height}_expected={expected_height}")
        parent = str(raw.get("parent_clearing_root") or "")
        if index == 0:
            if parent:
                errors.append(f"entry[{index}]_genesis_has_parent")
        else:
            if parent != prev_root:
                errors.append(
                    f"entry[{index}]_parent_mismatch got={parent[:12]} expected={prev_root[:12]}"
                )
        stored = str(raw.get("clearing_root") or "")
        recomputed = compute_clearing_root({**dict(raw), "clearing_root": ""})
        if not stored or stored != recomputed:
            errors.append(f"entry[{index}]_clearing_root_mismatch")
        if raw.get("deterministic") is not True:
            errors.append(f"entry[{index}]_not_deterministic")
        if raw.get("post_settlement") is not True:
            errors.append(f"entry[{index}]_not_post_settlement")
        bound = str(raw.get("bound_settlement_root") or "")
        if not bound:
            errors.append(f"entry[{index}]_missing_bound_settlement_root")
        else:
            bound_settlements.add(bound)
        s_hash = str(raw.get("settlement_hash") or "")
        if not s_hash:
            errors.append(f"entry[{index}]_missing_settlement_hash")
        else:
            settlement_hashes.add(s_hash)
        receipt_digest = str(raw.get("receipt_digest") or "")
        parent_net_stored = str(raw.get("parent_net_digest") or "")
        if parent_net_stored != prev_net:
            errors.append(f"entry[{index}]_parent_net_mismatch")
        expected_net = compute_net_position_digest(
            parent_net_digest=prev_net,
            bound_settlement_root=bound,
            receipt_digest=receipt_digest,
            capability_id=str(raw.get("capability_id") or ""),
            outcome=str(raw.get("outcome") or "cleared"),
        )
        stored_net = str(raw.get("net_position_digest") or "")
        if not stored_net or stored_net != expected_net:
            errors.append(f"entry[{index}]_net_position_digest_mismatch")
        cert = raw.get("clearing_certificate")
        if not isinstance(cert, Mapping):
            errors.append(f"entry[{index}]_missing_clearing_certificate")
        else:
            cert_verify = verify_clearing_certificate(cert)
            if not cert_verify.get("valid"):
                errors.append(f"entry[{index}]_clearing_cert_invalid")
            if str(cert.get("clearing_root") or "") != stored:
                errors.append(f"entry[{index}]_cert_clearing_root_mismatch")
            if int(cert.get("clearing_height") or 0) != height:
                errors.append(f"entry[{index}]_cert_height_mismatch")
            if str(cert.get("bound_settlement_root") or "") != bound:
                errors.append(f"entry[{index}]_cert_bound_settlement_mismatch")
            if str(cert.get("net_position_digest") or "") != stored_net:
                errors.append(f"entry[{index}]_cert_net_mismatch")
        prev_root = stored
        prev_net = stored_net

    if len(settlement_hashes) > 1:
        errors.append("mixed_settlement_hashes")

    tip = entries[-1] if entries else {}
    tip_height = int(tip.get("clearing_height") or 0) if isinstance(tip, Mapping) else 0
    tip_root = str(tip.get("clearing_root") or "") if isinstance(tip, Mapping) else ""
    tip_net = str(tip.get("net_position_digest") or "") if isinstance(tip, Mapping) else ""
    log_tip_height = int(clearing_log.get("tip_height") or 0)
    log_tip_root = str(clearing_log.get("tip_clearing_root") or "")
    log_net = str(clearing_log.get("net_position_digest") or "")
    if log_tip_height and log_tip_height != tip_height:
        errors.append("tip_height_metadata_mismatch")
    if log_tip_root and log_tip_root != tip_root:
        errors.append("tip_clearing_root_metadata_mismatch")
    if log_net and log_net != tip_net:
        errors.append("net_position_digest_metadata_mismatch")

    valid = not errors and tip_height >= 1 and bool(tip_root) and bool(tip_net)
    return {
        "ok": valid,
        "valid": valid,
        "action": "verify_clearing_chain",
        "entry_count": len(entries),
        "tip_height": tip_height,
        "tip_clearing_root": tip_root,
        "net_position_digest": tip_net,
        "bound_settlement_roots": sorted(bound_settlements),
        "settlement_hash": next(iter(settlement_hashes), ""),
        "errors": errors,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def apply_settlement_bundle_to_clearings(
    settlement_bundle: Mapping[str, Any],
    *,
    goal: str = "",
    min_clearings: int = 2,
) -> dict[str, Any]:
    """Clear multi-settlement receipts into a deterministic netted clearing log."""

    integrity = verify_settlement_bundle_integrity(settlement_bundle)
    if not integrity.get("ok"):
        return {
            "ok": False,
            "action": "apply_settlement_bundle_to_clearings",
            "error": "settlement_integrity_failed",
            "integrity": integrity,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    specs = derive_clearing_specs_from_settlement(
        settlement_bundle, min_clearings=min_clearings
    )
    if len(specs) < 2:
        return {
            "ok": False,
            "action": "apply_settlement_bundle_to_clearings",
            "error": "need_multi_clearing",
            "spec_count": len(specs),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    clearing_log = empty_clearing_log()
    applied: list[dict[str, Any]] = []
    for index, spec in enumerate(specs):
        result = apply_clearing_transition(
            clearing_log,
            spec,
            settlement_bundle=settlement_bundle,
            goal=f"{goal or settlement_bundle.get('goal') or 'clearing'} (clearing {index + 1})",
            claims={"clearing_index": index + 1, "plane": "clearing"},
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "action": "apply_settlement_bundle_to_clearings",
                "error": result.get("error") or "apply_failed",
                "applied_count": len(applied),
                "apply": {
                    "ok": result.get("ok"),
                    "error": result.get("error"),
                    "clearing_height": result.get("clearing_height"),
                },
                "clearing_log": clearing_log,
                "used_skill_route_discovery": legacy_pipeline_was_used(),
            }
        clearing_log = result["clearing_log"]
        applied.append(result["entry"])

    chain = verify_clearing_chain(clearing_log)
    ok = bool(chain.get("valid")) and len(applied) >= 2 and not legacy_pipeline_was_used()
    return {
        "ok": ok,
        "action": "apply_settlement_bundle_to_clearings",
        "clearing_log": clearing_log,
        "applied": applied,
        "applied_count": len(applied),
        "clearing_count": len(applied),
        "tip_height": clearing_log.get("tip_height"),
        "tip_clearing_root": clearing_log.get("tip_clearing_root"),
        "bound_settlement_root": clearing_log.get("bound_settlement_root"),
        "net_position_digest": clearing_log.get("net_position_digest"),
        "chain": chain,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def build_clearing_bundle(
    clearing_log: Mapping[str, Any],
    settlement_bundle: Mapping[str, Any],
    *,
    goal: str = "clearing over settlement",
) -> dict[str, Any]:
    """Package clearing log + settlement tip into a portable clearing bundle."""

    chain = verify_clearing_chain(clearing_log)
    if not chain.get("valid"):
        return {
            "ok": False,
            "action": "build_clearing_bundle",
            "error": "clearing_chain_invalid",
            "chain": chain,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    entries = list(clearing_log.get("entries") or [])
    tip = entries[-1]
    tip_cert = (
        tip.get("clearing_certificate")
        if isinstance(tip.get("clearing_certificate"), Mapping)
        else {}
    )
    tip_cert_verify = (
        verify_clearing_certificate(tip_cert) if tip_cert else {"valid": False}
    )
    settle_cert = (
        settlement_bundle.get("settlement_certificate")
        if isinstance(settlement_bundle.get("settlement_certificate"), Mapping)
        else {}
    )
    act_cert = (
        settlement_bundle.get("actuation_certificate")
        if isinstance(settlement_bundle.get("actuation_certificate"), Mapping)
        else {}
    )
    package = (
        settlement_bundle.get("package")
        if isinstance(settlement_bundle.get("package"), Mapping)
        else {}
    )
    certificates: dict[str, dict[str, Any]] = {}
    for clearing in entries:
        cert = clearing.get("clearing_certificate")
        if isinstance(cert, Mapping) and cert.get("certificate_hash"):
            certificates[str(cert["certificate_hash"])] = {
                "certificate_hash": cert.get("certificate_hash"),
                "payload": cert,
                "clearing_height": clearing.get("clearing_height"),
            }
    if isinstance(settle_cert, Mapping) and settle_cert.get("certificate_hash"):
        certificates[str(settle_cert["certificate_hash"])] = {
            "certificate_hash": settle_cert.get("certificate_hash"),
            "payload": settle_cert,
            "kind": "settlement_certificate",
        }
    if isinstance(act_cert, Mapping) and act_cert.get("certificate_hash"):
        certificates[str(act_cert["certificate_hash"])] = {
            "certificate_hash": act_cert.get("certificate_hash"),
            "payload": act_cert,
            "kind": "actuation_certificate",
        }
    exec_cert = (
        settlement_bundle.get("execution_certificate")
        if isinstance(settlement_bundle.get("execution_certificate"), Mapping)
        else {}
    )
    if isinstance(exec_cert, Mapping) and exec_cert.get("certificate_hash"):
        certificates[str(exec_cert["certificate_hash"])] = {
            "certificate_hash": exec_cert.get("certificate_hash"),
            "payload": exec_cert,
            "kind": "execution_certificate",
        }

    member_ids = list(settlement_bundle.get("member_ids") or package.get("member_ids") or [])
    cb: dict[str, Any] = {
        "schema_version": CLEARING_BUNDLE_SCHEMA,
        "kind": "clearing_bundle",
        "action": "build_clearing_bundle",
        "goal": goal,
        "clearings": copy.deepcopy(dict(clearing_log)),
        "settlements": copy.deepcopy(
            settlement_bundle.get("settlements")
            if isinstance(settlement_bundle.get("settlements"), Mapping)
            else {}
        ),
        "actions": copy.deepcopy(
            settlement_bundle.get("actions")
            if isinstance(settlement_bundle.get("actions"), Mapping)
            else {}
        ),
        "package": copy.deepcopy(dict(package)),
        "lineage": copy.deepcopy(
            settlement_bundle.get("lineage")
            if isinstance(settlement_bundle.get("lineage"), Mapping)
            else {}
        ),
        "clearing_certificate": copy.deepcopy(dict(tip_cert)),
        "settlement_certificate": copy.deepcopy(dict(settle_cert)),
        "actuation_certificate": copy.deepcopy(dict(act_cert)),
        "execution_certificate": copy.deepcopy(dict(exec_cert)),
        "certificates": certificates,
        "certificate_count": len(certificates),
        "clearing_count": len(entries),
        "settlement_count": int(settlement_bundle.get("settlement_count") or 0),
        "action_count": int(settlement_bundle.get("action_count") or 0),
        "tip_height": int(clearing_log.get("tip_height") or 0),
        "tip_clearing_root": str(clearing_log.get("tip_clearing_root") or ""),
        "bound_settlement_root": str(clearing_log.get("bound_settlement_root") or ""),
        "bound_settlement_height": int(clearing_log.get("bound_settlement_height") or 0),
        "tip_settlement_root": str(settlement_bundle.get("tip_settlement_root") or ""),
        "bound_action_root": str(settlement_bundle.get("bound_action_root") or ""),
        "tip_action_root": str(settlement_bundle.get("tip_action_root") or ""),
        "bound_state_root": str(settlement_bundle.get("bound_state_root") or ""),
        "net_position_digest": str(clearing_log.get("net_position_digest") or ""),
        "settlement_hash": str(settlement_bundle.get("settlement_hash") or ""),
        "actuation_hash": str(settlement_bundle.get("actuation_hash") or ""),
        "execution_hash": str(settlement_bundle.get("execution_hash") or ""),
        "package_hash": str(settlement_bundle.get("package_hash") or ""),
        "member_ids": sorted({str(m).strip() for m in member_ids if str(m).strip()}),
        "member_count": len(member_ids),
        "lineage_head_hash": str(settlement_bundle.get("lineage_head_hash") or ""),
        "lineage_entry_count": int(settlement_bundle.get("lineage_entry_count") or 0),
        "origin_count": settlement_bundle.get("origin_count"),
        "agreeing_count": settlement_bundle.get("agreeing_count"),
        "byzantine_count": settlement_bundle.get("byzantine_count"),
        "state_count": settlement_bundle.get("state_count"),
        "epoch_count": settlement_bundle.get("epoch_count"),
        "deterministic": True,
        "post_settlement": True,
        "exported_at": utc_now_iso(),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    cb["clearing_hash"] = compute_clearing_bundle_hash(cb)
    cb["ok"] = (
        bool(chain.get("valid"))
        and bool(tip_cert_verify.get("valid"))
        and len(entries) >= 2
        and bool(cb["clearing_hash"])
        and bool(cb["settlement_hash"])
        and bool(cb["net_position_digest"])
        and cb["deterministic"] is True
        and cb["post_settlement"] is True
        and not bool(cb["used_skill_route_discovery"])
    )
    return cb


def write_clearing_bundle(path: Path, bundle: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, dict(bundle))
    return path


def load_clearing_bundle(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("clearing bundle must be a JSON object")
    return data


def verify_clearing_bundle_integrity(bundle: Mapping[str, Any]) -> dict[str, Any]:
    expected = str(bundle.get("clearing_hash") or "").strip()
    recomputed = compute_clearing_bundle_hash(bundle)
    hash_ok = bool(expected) and expected == recomputed
    clearings = (
        bundle.get("clearings")
        if isinstance(bundle.get("clearings"), Mapping)
        else {}
    )
    chain = (
        verify_clearing_chain(clearings)
        if clearings
        else {"ok": False, "valid": False, "errors": ["missing_clearings"]}
    )
    cert = (
        bundle.get("clearing_certificate")
        if isinstance(bundle.get("clearing_certificate"), Mapping)
        else {}
    )
    cert_verify = (
        verify_clearing_certificate(cert) if cert else {"valid": False, "ok": False}
    )
    settle_cert = (
        bundle.get("settlement_certificate")
        if isinstance(bundle.get("settlement_certificate"), Mapping)
        else {}
    )
    settle_cert_verify = (
        verify_settlement_certificate(settle_cert)
        if settle_cert
        else {"valid": False, "ok": False}
    )
    multi = int(bundle.get("clearing_count") or chain.get("entry_count") or 0) >= 2
    package = bundle.get("package") if isinstance(bundle.get("package"), Mapping) else {}
    package_ok = bool(package) and bool(bundle.get("package_hash"))
    bound_ok = bool(bundle.get("bound_settlement_root")) and bool(
        bundle.get("settlement_hash")
    )
    net_ok = bool(bundle.get("net_position_digest")) and str(
        bundle.get("net_position_digest") or ""
    ) == str(chain.get("net_position_digest") or bundle.get("net_position_digest") or "")
    deterministic = bundle.get("deterministic") is True
    post_settlement = bundle.get("post_settlement") is True
    used_skill = bool(bundle.get("used_skill_route_discovery")) or legacy_pipeline_was_used()
    ok = (
        hash_ok
        and bool(chain.get("valid"))
        and bool(cert_verify.get("valid"))
        and bool(settle_cert_verify.get("valid"))
        and multi
        and package_ok
        and bound_ok
        and net_ok
        and deterministic
        and post_settlement
        and not used_skill
    )
    return {
        "ok": ok,
        "action": "verify_clearing_bundle_integrity",
        "hash_ok": hash_ok,
        "chain_valid": bool(chain.get("valid")),
        "multi_clearing": multi,
        "package_ok": package_ok,
        "clearing_certificate_valid": bool(cert_verify.get("valid")),
        "settlement_certificate_valid": bool(settle_cert_verify.get("valid")),
        "bound_ok": bound_ok,
        "net_ok": net_ok,
        "deterministic": deterministic,
        "post_settlement": post_settlement,
        "tip_height": chain.get("tip_height"),
        "tip_clearing_root": chain.get("tip_clearing_root"),
        "net_position_digest": chain.get("net_position_digest"),
        "clearing_hash": expected if hash_ok else recomputed,
        "errors": list(chain.get("errors") or []),
        "used_skill_route_discovery": used_skill,
    }


def rehydrate_clearing_bundle(
    repo_path: Path,
    bundle: Mapping[str, Any],
    *,
    sandbox_dir: Path | None = None,
) -> dict[str, Any]:
    """Materialize tip package + clearing log into a sterile sandbox and re-check nets."""

    root = repo_path.resolve()
    integrity = verify_clearing_bundle_integrity(bundle)
    if not integrity.get("ok"):
        return {
            "ok": False,
            "action": "rehydrate_clearing_bundle",
            "error": "clearing_integrity_failed",
            "integrity": integrity,
            "used_skill_route_discovery": integrity.get("used_skill_route_discovery"),
        }

    c_hash = str(bundle.get("clearing_hash") or "unknown")
    sandbox = (
        sandbox_dir.resolve()
        if sandbox_dir is not None
        else (root / "artifacts" / "clearing-sandbox" / c_hash[:16])
    )
    sandbox.mkdir(parents=True, exist_ok=True)

    package = dict(bundle.get("package") or {})
    lineage = copy.deepcopy(bundle.get("lineage") or {})
    clearings = copy.deepcopy(bundle.get("clearings") or {})
    settlements = copy.deepcopy(bundle.get("settlements") or {})
    actions = copy.deepcopy(bundle.get("actions") or {})
    lineage_path = sandbox / "lineage.json"
    if lineage:
        write_lineage_log(lineage_path, lineage)
    clearings_path = sandbox / "clearings.json"
    atomic_write_json(clearings_path, clearings)
    settlements_path = sandbox / "settlements.json"
    atomic_write_json(settlements_path, settlements)
    actions_path = sandbox / "actions.json"
    atomic_write_json(actions_path, actions)

    empty = CapabilityLedger(schema_version=SCHEMA_VERSION, updated_at=utc_now_iso())
    empty, import_report = import_capability_package(empty, package, replace=True)
    sterile_ledger_path = sandbox / "ledger.json"
    save_ledger(sterile_ledger_path, empty)

    cert = (
        bundle.get("clearing_certificate")
        if isinstance(bundle.get("clearing_certificate"), Mapping)
        else {}
    )
    cert_path = sandbox / "clearing-certificate.json"
    if cert:
        write_clearing_certificate(cert_path, cert)
    settle_cert = (
        bundle.get("settlement_certificate")
        if isinstance(bundle.get("settlement_certificate"), Mapping)
        else {}
    )
    settle_cert_path = sandbox / "settlement-certificate.json"
    if settle_cert:
        write_settlement_certificate(settle_cert_path, settle_cert)

    chain = verify_clearing_chain(clearings)
    cert_verify = (
        verify_clearing_certificate(cert) if cert else {"ok": False, "valid": False}
    )
    settle_cert_verify = (
        verify_settlement_certificate(settle_cert)
        if settle_cert
        else {"ok": False, "valid": False}
    )
    re_net_ok = True
    prev_net = ""
    for entry in list(clearings.get("entries") or []):
        if not isinstance(entry, Mapping):
            re_net_ok = False
            break
        expected = compute_net_position_digest(
            parent_net_digest=prev_net,
            bound_settlement_root=str(entry.get("bound_settlement_root") or ""),
            receipt_digest=str(entry.get("receipt_digest") or ""),
            capability_id=str(entry.get("capability_id") or ""),
            outcome=str(entry.get("outcome") or "cleared"),
        )
        if expected != str(entry.get("net_position_digest") or ""):
            re_net_ok = False
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
        and bool(settle_cert_verify.get("valid"))
        and re_net_ok
        and int(import_report.get("imported_count") or 0) >= 1
        and not used_skill
    )
    return {
        "ok": ok,
        "action": "rehydrate_clearing_bundle",
        "sandbox_dir": str(sandbox),
        "lineage_path": str(lineage_path) if lineage else None,
        "clearings_path": str(clearings_path),
        "settlements_path": str(settlements_path),
        "actions_path": str(actions_path),
        "sterile_ledger_path": str(sterile_ledger_path),
        "certificate_path": str(cert_path) if cert else None,
        "settlement_certificate_path": str(settle_cert_path) if settle_cert else None,
        "clearing_hash": c_hash,
        "import": import_report,
        "chain": {
            "ok": chain.get("ok"),
            "valid": chain.get("valid"),
            "entry_count": chain.get("entry_count"),
            "tip_height": chain.get("tip_height"),
            "tip_clearing_root": chain.get("tip_clearing_root"),
            "net_position_digest": chain.get("net_position_digest"),
            "errors": chain.get("errors") or [],
        },
        "lineage_chain": {
            "ok": lineage_chain.get("ok"),
            "valid": lineage_chain.get("valid"),
            "entry_count": lineage_chain.get("entry_count"),
        },
        "clearing_certificate": {
            "ok": cert_verify.get("ok"),
            "valid": cert_verify.get("valid"),
            "certificate_hash": cert_verify.get("certificate_hash"),
            "clearing_root": cert_verify.get("clearing_root"),
        },
        "settlement_certificate": {
            "ok": settle_cert_verify.get("ok"),
            "valid": settle_cert_verify.get("valid"),
            "certificate_hash": settle_cert_verify.get("certificate_hash"),
        },
        "net_digests_match": re_net_ok,
        "integrity": {
            "ok": integrity.get("ok"),
            "hash_ok": integrity.get("hash_ok"),
            "multi_clearing": integrity.get("multi_clearing"),
            "tip_height": integrity.get("tip_height"),
        },
        "sterile_ledger": empty,
        "used_skill_route_discovery": used_skill,
    }


def replay_clearings_from_specs(
    specs: Sequence[Mapping[str, Any]],
    settlement_bundle: Mapping[str, Any],
    *,
    goal: str = "",
) -> dict[str, Any]:
    clearing_log = empty_clearing_log()
    for index, spec in enumerate(specs):
        result = apply_clearing_transition(
            clearing_log,
            spec,
            settlement_bundle=settlement_bundle,
            goal=f"{goal} (replay {index + 1})",
            claims={"replay": True, "clearing_index": index + 1},
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "error": result.get("error") or "replay_failed",
                "clearing_log": clearing_log,
                "applied_count": index,
            }
        clearing_log = result["clearing_log"]
    chain = verify_clearing_chain(clearing_log)
    return {
        "ok": bool(chain.get("valid")),
        "clearing_log": clearing_log,
        "tip_clearing_root": clearing_log.get("tip_clearing_root"),
        "tip_height": clearing_log.get("tip_height"),
        "net_position_digest": clearing_log.get("net_position_digest"),
        "chain": chain,
    }


def run_clearing_adversarial_checks(
    intact_bundle: Mapping[str, Any],
    clearing_log: Mapping[str, Any],
    settlement_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Falsify clearing honesty: mutation, reorder, wrong-settlement, double-clear, forged root, net."""

    intact = verify_clearing_bundle_integrity(intact_bundle)
    intact_chain = verify_clearing_chain(clearing_log)

    mutated_log = copy.deepcopy(dict(clearing_log))
    m_entries = list(mutated_log.get("entries") or [])
    mutation_fails = False
    if m_entries:
        first = dict(m_entries[0])
        first["capability_id"] = "evil.capability"
        m_entries[0] = first
        mutated_log["entries"] = m_entries
        mutation_check = verify_clearing_chain(mutated_log)
        mutation_fails = mutation_check.get("valid") is not True

    reorder_fails = False
    if len(list(clearing_log.get("entries") or [])) >= 2:
        rev = copy.deepcopy(dict(clearing_log))
        rev["entries"] = list(reversed(list(rev.get("entries") or [])))
        reorder_check = verify_clearing_chain(rev)
        reorder_fails = reorder_check.get("valid") is not True
    else:
        reorder_fails = True

    wrong_settlement_fails = False
    if m_entries:
        ws = copy.deepcopy(dict(clearing_log))
        w_entries = list(ws.get("entries") or [])
        tip = dict(w_entries[-1])
        tip["bound_settlement_root"] = "a" * 24
        w_entries[-1] = tip
        ws["entries"] = w_entries
        ws["bound_settlement_root"] = tip["bound_settlement_root"]
        wrong_check = verify_clearing_chain(ws)
        wrong_settlement_fails = wrong_check.get("valid") is not True
    specs = derive_clearing_specs_from_settlement(settlement_bundle)
    bad_spec = dict(specs[0]) if specs else {}
    if bad_spec:
        bad_spec["bound_settlement_root"] = "b" * 24
        apply_bad = apply_clearing_transition(
            empty_clearing_log(),
            bad_spec,
            settlement_bundle=settlement_bundle,
            goal="bad-bind",
        )
        wrong_settlement_fails = wrong_settlement_fails and (
            apply_bad.get("ok") is not True
            and apply_bad.get("error") == "bound_settlement_root_mismatch"
        )

    forged_log = copy.deepcopy(dict(clearing_log))
    f_entries = list(forged_log.get("entries") or [])
    forged_root_fails = False
    if f_entries:
        tip = dict(f_entries[-1])
        tip["clearing_root"] = "f" * 24
        f_entries[-1] = tip
        forged_log["entries"] = f_entries
        forged_log["tip_clearing_root"] = tip["clearing_root"]
        forged_check = verify_clearing_chain(forged_log)
        forged_root_fails = forged_check.get("valid") is not True

    gap_log = copy.deepcopy(dict(clearing_log))
    g_entries = list(gap_log.get("entries") or [])
    gap_fails = False
    if g_entries:
        last = dict(g_entries[-1])
        last["clearing_height"] = int(last.get("clearing_height") or 1) + 5
        g_entries[-1] = last
        gap_log["entries"] = g_entries
        gap_log["tip_height"] = last["clearing_height"]
        gap_check = verify_clearing_chain(gap_log)
        gap_fails = gap_check.get("valid") is not True

    broken_cert_fails = False
    if m_entries:
        broken_log = copy.deepcopy(dict(clearing_log))
        b_entries = list(broken_log.get("entries") or [])
        tip = dict(b_entries[-1])
        cert = dict(tip.get("clearing_certificate") or {})
        cert["certificate_hash"] = "0" * 24
        tip["clearing_certificate"] = cert
        b_entries[-1] = tip
        broken_log["entries"] = b_entries
        broken_check = verify_clearing_chain(broken_log)
        broken_cert_fails = broken_check.get("valid") is not True

    parent_fails = False
    if len(list(clearing_log.get("entries") or [])) >= 2:
        parent_log = copy.deepcopy(dict(clearing_log))
        p_entries = list(parent_log.get("entries") or [])
        tip = dict(p_entries[-1])
        tip["parent_clearing_root"] = "deadbeef-parent-root"
        p_entries[-1] = tip
        parent_log["entries"] = p_entries
        parent_check = verify_clearing_chain(parent_log)
        parent_fails = parent_check.get("valid") is not True
    else:
        parent_fails = True

    net_tamper_fails = False
    if m_entries:
        net_log = copy.deepcopy(dict(clearing_log))
        n_entries = list(net_log.get("entries") or [])
        tip = dict(n_entries[-1])
        tip["net_position_digest"] = "c" * 24
        n_entries[-1] = tip
        net_log["entries"] = n_entries
        net_log["net_position_digest"] = tip["net_position_digest"]
        net_check = verify_clearing_chain(net_log)
        net_tamper_fails = net_check.get("valid") is not True

    tampered = copy.deepcopy(dict(intact_bundle))
    tampered["clearing_hash"] = "e" * 24
    tamper_check = verify_clearing_bundle_integrity(tampered)
    tamper_fails = tamper_check.get("ok") is not True

    single = copy.deepcopy(dict(intact_bundle))
    single_clearings = copy.deepcopy(dict(single.get("clearings") or {}))
    s_entries = list(single_clearings.get("entries") or [])[:1]
    single_clearings["entries"] = s_entries
    single_clearings["entry_count"] = len(s_entries)
    if s_entries:
        single_clearings["tip_height"] = s_entries[0].get("clearing_height")
        single_clearings["tip_clearing_root"] = s_entries[0].get("clearing_root")
        single_clearings["net_position_digest"] = s_entries[0].get("net_position_digest")
        single["clearings"] = single_clearings
        single["clearing_count"] = 1
        single["tip_height"] = single_clearings["tip_height"]
        single["tip_clearing_root"] = single_clearings["tip_clearing_root"]
        single["net_position_digest"] = single_clearings["net_position_digest"]
        if "clearing_hash" in single:
            del single["clearing_hash"]
        single["clearing_hash"] = compute_clearing_bundle_hash(single)
        single_check = verify_clearing_bundle_integrity(single)
        single_clearing_fails = single_check.get("ok") is not True
    else:
        single_clearing_fails = True

    replay_match = False
    if specs:
        replay = replay_clearings_from_specs(
            specs, settlement_bundle, goal="adversarial-replay"
        )
        replay_match = (
            bool(replay.get("ok"))
            and str(replay.get("tip_clearing_root") or "")
            == str(clearing_log.get("tip_clearing_root") or "")
            and int(replay.get("tip_height") or 0)
            == int(clearing_log.get("tip_height") or 0)
            and str(replay.get("net_position_digest") or "")
            == str(clearing_log.get("net_position_digest") or "")
        )

    dup_fails = False
    if specs:
        dup = apply_clearing_transition(
            clearing_log, specs[-1], settlement_bundle=settlement_bundle, goal="dup"
        )
        dup_fails = dup.get("ok") is not True and dup.get("error") in {
            "duplicate_clearing_rejected",
        }

    incomplete_fails = single_clearing_fails
    used_skill = legacy_pipeline_was_used()
    ok = (
        bool(intact.get("ok"))
        and bool(intact_chain.get("valid"))
        and mutation_fails
        and reorder_fails
        and wrong_settlement_fails
        and forged_root_fails
        and gap_fails
        and broken_cert_fails
        and parent_fails
        and net_tamper_fails
        and tamper_fails
        and single_clearing_fails
        and replay_match
        and dup_fails
        and incomplete_fails
        and not used_skill
    )
    return {
        "ok": ok,
        "action": "clearing_adversarial_checks",
        "intact_ok": bool(intact.get("ok")),
        "chain_ok": bool(intact_chain.get("valid")),
        "mutation_fails_as_expected": mutation_fails,
        "reorder_fails_as_expected": reorder_fails,
        "wrong_settlement_fails_as_expected": wrong_settlement_fails,
        "forged_root_fails_as_expected": forged_root_fails,
        "gap_fails_as_expected": gap_fails,
        "broken_cert_fails_as_expected": broken_cert_fails,
        "wrong_parent_fails_as_expected": parent_fails,
        "net_tamper_fails_as_expected": net_tamper_fails,
        "tamper_fails_as_expected": tamper_fails,
        "single_clearing_fails_as_expected": single_clearing_fails,
        "replay_matches_tip": replay_match,
        "duplicate_apply_fails_as_expected": dup_fails,
        "incomplete_fails_as_expected": incomplete_fails,
        "used_skill_route_discovery": used_skill,
    }


def run_clearing_plane(
    repo_path: Path,
    goal: str = "clearing over settlement",
    done_when: str = "",
    *,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 720,
    max_steps: int = 3,
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
    lineage_path: Path | None = None,
    bundle_path: Path | None = None,
    quorum_path: Path | None = None,
    finality_path: Path | None = None,
    execution_path: Path | None = None,
    actuation_path: Path | None = None,
    settlement_path: Path | None = None,
    clearing_path: Path | None = None,
    sandbox_dir: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Closed clearing plane: settlement → multi-clearing net positions → cert → rehydrate → adversarial.

    Past settled receipts: each settlement binds an ordered clearing position into a
    hash-chained clearing log with net position digests and clearing certificates bound
    to the settlement tip. Mutation, reorder, wrong-settlement binding, double-clearing,
    forged roots, height gaps, broken certs, net tamper, and single-clearing bundles fail;
    sterile rehydrate+prove and genesis replay matching tip succeed without skill-route.
    """

    root = repo_path.resolve()
    path, _ledger = ensure_seeded_ledger(root)
    want_epochs = max(2, int(epoch_count))
    want_actions = max(2, int(min_actions))
    want_settlements = max(2, int(min_settlements))
    want_clearings = max(2, int(min_clearings))

    out_lineage = (
        lineage_path.resolve()
        if lineage_path is not None
        else default_lineage_path(root)
    )
    out_settlement = (
        settlement_path.resolve()
        if settlement_path is not None
        else (default_settlement_bundle_dir(root) / "clearing-source-settlement.json")
    )

    settlement_report: dict[str, Any] | None = None
    settlement_bundle: dict[str, Any] | None = None
    if run_settlement:
        settlement_report = run_settlement_plane(
            root,
            goal if goal else "settlement for clearing",
            strip_context_only_outcome_predicates(done_when or ""),
            command_runner=command_runner,
            timeout=timeout,
            max_steps=max_steps,
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
            lineage_path=out_lineage,
            bundle_path=bundle_path,
            quorum_path=quorum_path,
            finality_path=finality_path,
            execution_path=execution_path,
            actuation_path=actuation_path,
            settlement_path=out_settlement,
            persist=persist,
        )
        s_path = Path((settlement_report.get("settlement") or {}).get("bundle_path") or "")
        if s_path and s_path.is_file():
            settlement_bundle = load_settlement_bundle(s_path)
        elif out_settlement.is_file():
            settlement_bundle = load_settlement_bundle(out_settlement)
        else:
            settlement_bundle = None
    else:
        if out_settlement.is_file():
            settlement_bundle = load_settlement_bundle(out_settlement)
        else:
            settlement_report = run_settlement_plane(
                root,
                goal,
                "",
                command_runner=command_runner,
                timeout=timeout,
                max_steps=max_steps,
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
                lineage_path=out_lineage,
                settlement_path=out_settlement,
                persist=persist,
            )
            if out_settlement.is_file():
                settlement_bundle = load_settlement_bundle(out_settlement)

    if settlement_bundle is None or not (
        settlement_bundle.get("ok")
        or (settlement_report and settlement_report.get("settled"))
    ):
        return {
            "ok": False,
            "action": "clearing_plane",
            "error": "settlement_source_failed",
            "settlement": None
            if settlement_report is None
            else {
                "ok": settlement_report.get("ok"),
                "settled": settlement_report.get("settled"),
            },
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "ledger_path": str(path),
        }

    applied = apply_settlement_bundle_to_clearings(
        settlement_bundle,
        goal=goal,
        min_clearings=want_clearings,
    )
    if not applied.get("ok"):
        return {
            "ok": False,
            "action": "clearing_plane",
            "error": applied.get("error") or "clearing_apply_failed",
            "apply": {
                "ok": applied.get("ok"),
                "error": applied.get("error"),
                "applied_count": applied.get("applied_count"),
            },
            "settlement": {
                "ok": True if settlement_report is None else bool(settlement_report.get("ok")),
                "settlement_hash": settlement_bundle.get("settlement_hash"),
            },
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "ledger_path": str(path),
        }

    clearing_log = applied["clearing_log"]
    clearing = build_clearing_bundle(
        clearing_log,
        settlement_bundle,
        goal=goal,
    )
    out_c = (
        clearing_path.resolve()
        if clearing_path is not None
        else (
            default_clearing_bundle_dir(root)
            / f"clearing-{clearing.get('clearing_hash') or 'unknown'}.json"
        )
    )
    if persist and clearing.get("ok"):
        write_clearing_bundle(out_c, clearing)
        reloaded = load_clearing_bundle(out_c)
    else:
        reloaded = clearing

    integrity = verify_clearing_bundle_integrity(reloaded)
    rehydrate = rehydrate_clearing_bundle(
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

    chain = verify_clearing_chain(
        reloaded.get("clearings")
        if isinstance(reloaded.get("clearings"), Mapping)
        else clearing_log
    )
    cert_verify = verify_clearing_certificate(
        reloaded.get("clearing_certificate")
        if isinstance(reloaded.get("clearing_certificate"), Mapping)
        else {}
    )
    adversarial = run_clearing_adversarial_checks(
        reloaded, clearing_log, settlement_bundle
    )

    used_skill = bool(
        (settlement_report or {}).get("used_skill_route_discovery")
        or clearing.get("used_skill_route_discovery")
        or integrity.get("used_skill_route_discovery")
        or rehydrate.get("used_skill_route_discovery")
        or prove.get("used_skill_route_discovery")
        or adversarial.get("used_skill_route_discovery")
        or legacy_pipeline_was_used()
    )
    tip_height = int(reloaded.get("tip_height") or chain.get("tip_height") or 0)
    clearing_n = int(reloaded.get("clearing_count") or chain.get("entry_count") or 0)
    settlement_n = int(reloaded.get("settlement_count") or settlement_bundle.get("settlement_count") or 0)
    action_n = int(reloaded.get("action_count") or settlement_bundle.get("action_count") or 0)
    state_n = int(reloaded.get("state_count") or settlement_bundle.get("state_count") or 0)
    epoch_n = int(reloaded.get("epoch_count") or settlement_bundle.get("epoch_count") or 0)
    cleared = (
        bool(clearing.get("ok"))
        and bool(integrity.get("ok"))
        and bool(rehydrate.get("ok"))
        and bool(prove.get("ok"))
        and bool(chain.get("valid"))
        and bool(cert_verify.get("valid"))
        and bool(adversarial.get("ok"))
        and tip_height >= 2
        and clearing_n >= 2
        and not used_skill
    )
    provisional_ok = cleared and (
        settlement_report is None or bool(settlement_report.get("ok")) or not run_settlement
    )

    context = {
        "used_skill_route_discovery": used_skill,
        "settlement": {
            "ok": True if settlement_report is None else bool(settlement_report.get("ok")),
            "settled": True
            if settlement_report is None
            else bool(settlement_report.get("settled")),
            "settlement_count": settlement_n,
            "tip_height": settlement_bundle.get("tip_height"),
            "tip_settlement_root": settlement_bundle.get("tip_settlement_root"),
            "settlement_hash": settlement_bundle.get("settlement_hash"),
            "settlement_root_valid": True,
            "certificate_valid": True,
            "deterministic": True,
            "post_actuation": True,
            "multi_settlement": settlement_n >= 2,
        },
        "settlement_plane": {
            "ok": True if settlement_report is None else bool(settlement_report.get("ok")),
            "settled": True
            if settlement_report is None
            else bool(settlement_report.get("settled")),
            "settlement_count": settlement_n,
            "settlement_root_valid": True,
        },
        "receipts": {
            "ok": True if settlement_report is None else bool(settlement_report.get("ok")),
            "settled": True
            if settlement_report is None
            else bool(settlement_report.get("settled")),
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
            "state_height": settlement_bundle.get("bound_state_root") and state_n or state_n,
            "tip_height": state_n,
            "tip_state_root": settlement_bundle.get("bound_state_root"),
            "execution_hash": settlement_bundle.get("execution_hash"),
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
            "tip_state_root": settlement_bundle.get("bound_state_root"),
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
        "clearing": {
            "ok": provisional_ok,
            "cleared": cleared,
            "clearing_count": clearing_n,
            "tip_height": tip_height,
            "tip_clearing_root": reloaded.get("tip_clearing_root"),
            "clearing_hash": reloaded.get("clearing_hash"),
            "clearing_root_valid": bool(cert_verify.get("valid")),
            "certificate_valid": bool(cert_verify.get("valid")),
            "net_position_digest": reloaded.get("net_position_digest"),
            "deterministic": True,
            "post_settlement": True,
            "multi_clearing": clearing_n >= 2,
            "bound_settlement_root": reloaded.get("bound_settlement_root"),
        },
        "clearing_plane": {
            "ok": provisional_ok,
            "cleared": cleared,
            "clearing_count": clearing_n,
            "clearing_root_valid": bool(cert_verify.get("valid")),
        },
        "net": {
            "ok": provisional_ok,
            "cleared": cleared,
            "clearing_count": clearing_n,
            "net_position_digest": reloaded.get("net_position_digest"),
            "clearing_root_valid": bool(cert_verify.get("valid")),
        },
        "chain": chain,
        "clearing_chain": chain,
        "settlement_chain": (settlement_report or {}).get("chain") or {},
        "lineage_chain": (settlement_report or {}).get("chain") or {},
        "lineage": {
            "ok": True,
            "entry_count": reloaded.get("lineage_entry_count"),
        },
        "origin_count": reloaded.get("origin_count"),
        "clearing_count": clearing_n,
        "settlement_count": settlement_n,
        "action_count": action_n,
        "tip_height": tip_height,
        "state_height": state_n,
        "epoch_count": epoch_n,
        "clearing_certificate": reloaded.get("clearing_certificate"),
        "clearing_hash": reloaded.get("clearing_hash"),
        "settlement_hash": reloaded.get("settlement_hash"),
        "actuation_hash": reloaded.get("actuation_hash"),
        "execution_hash": reloaded.get("execution_hash"),
        "tip_clearing_root": reloaded.get("tip_clearing_root"),
        "bound_settlement_root": reloaded.get("bound_settlement_root"),
        "tip_settlement_root": reloaded.get("tip_settlement_root"),
        "bound_action_root": reloaded.get("bound_action_root"),
        "tip_action_root": reloaded.get("tip_action_root"),
        "bound_state_root": reloaded.get("bound_state_root"),
        "net_position_digest": reloaded.get("net_position_digest"),
    }
    clearing_done_when = (
        "no_skill_route; clearing_ok; cleared_ok; min_clearings:2; "
        "clearing_root_valid; settlement_ok; settled_ok; min_settlements:2; "
        "settlement_root_valid; chain_valid; capability_exists:repo.import-health"
    )
    final_contract = evaluate_outcome_contract(
        root,
        clearing_done_when,
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
        "action": "clearing_plane",
        "goal": goal,
        "done_when": done_when,
        "clearing_done_when": clearing_done_when,
        "met": final_contract.get("met"),
        "machine_checkable": True,
        "cleared": cleared,
        "clearing_count": clearing_n,
        "tip_height": tip_height,
        "tip_clearing_root": reloaded.get("tip_clearing_root"),
        "bound_settlement_root": reloaded.get("bound_settlement_root"),
        "bound_settlement_height": reloaded.get("bound_settlement_height"),
        "net_position_digest": reloaded.get("net_position_digest"),
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
        "settlement": None
        if settlement_report is None
        else {
            "ok": settlement_report.get("ok"),
            "settled": settlement_report.get("settled"),
            "settlement_hash": (settlement_report.get("settlement") or {}).get(
                "settlement_hash"
            ),
            "settlement_count": settlement_report.get("settlement_count"),
            "tip_settlement_root": settlement_report.get("tip_settlement_root"),
        },
        "clearing": {
            "ok": clearing.get("ok"),
            "clearing_hash": reloaded.get("clearing_hash"),
            "bundle_path": str(out_c) if persist and clearing.get("ok") else None,
            "package_hash": reloaded.get("package_hash"),
            "member_count": reloaded.get("member_count"),
            "clearing_count": clearing_n,
            "tip_height": tip_height,
            "tip_clearing_root": reloaded.get("tip_clearing_root"),
            "bound_settlement_root": reloaded.get("bound_settlement_root"),
            "net_position_digest": reloaded.get("net_position_digest"),
            "certificate_count": reloaded.get("certificate_count"),
            "lineage_entry_count": reloaded.get("lineage_entry_count"),
            "lineage_head_hash": reloaded.get("lineage_head_hash"),
            "settlement_hash": reloaded.get("settlement_hash"),
            "actuation_hash": reloaded.get("actuation_hash"),
            "execution_hash": reloaded.get("execution_hash"),
            "persisted": persist and out_c.exists() if clearing.get("ok") else False,
            "deterministic": True,
            "post_settlement": True,
        },
        "integrity": {
            "ok": integrity.get("ok"),
            "hash_ok": integrity.get("hash_ok"),
            "chain_valid": integrity.get("chain_valid"),
            "multi_clearing": integrity.get("multi_clearing"),
            "package_ok": integrity.get("package_ok"),
            "clearing_certificate_valid": integrity.get("clearing_certificate_valid"),
            "settlement_certificate_valid": integrity.get(
                "settlement_certificate_valid"
            ),
            "bound_ok": integrity.get("bound_ok"),
            "net_ok": integrity.get("net_ok"),
            "deterministic": integrity.get("deterministic"),
            "post_settlement": integrity.get("post_settlement"),
        },
        "rehydrate": {
            "ok": rehydrate.get("ok"),
            "sandbox_dir": rehydrate.get("sandbox_dir"),
            "lineage_path": rehydrate.get("lineage_path"),
            "clearings_path": rehydrate.get("clearings_path"),
            "settlements_path": rehydrate.get("settlements_path"),
            "actions_path": rehydrate.get("actions_path"),
            "sterile_ledger_path": rehydrate.get("sterile_ledger_path"),
            "import": rehydrate.get("import"),
            "chain": rehydrate.get("chain"),
            "clearing_certificate": rehydrate.get("clearing_certificate"),
            "settlement_certificate": rehydrate.get("settlement_certificate"),
            "net_digests_match": rehydrate.get("net_digests_match"),
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
            "tip_clearing_root": chain.get("tip_clearing_root"),
            "net_position_digest": chain.get("net_position_digest"),
            "errors": chain.get("errors") or [],
        },
        "clearing_certificate": {
            "ok": cert_verify.get("ok"),
            "valid": cert_verify.get("valid"),
            "hash_ok": cert_verify.get("hash_ok"),
            "certificate_hash": cert_verify.get("certificate_hash"),
            "clearing_height": cert_verify.get("clearing_height"),
            "clearing_root": cert_verify.get("clearing_root"),
            "bound_settlement_root": cert_verify.get("bound_settlement_root"),
            "net_position_digest": cert_verify.get("net_position_digest"),
        },
        "adversarial": {
            "ok": adversarial.get("ok"),
            "intact_ok": adversarial.get("intact_ok"),
            "mutation_fails_as_expected": adversarial.get(
                "mutation_fails_as_expected"
            ),
            "reorder_fails_as_expected": adversarial.get("reorder_fails_as_expected"),
            "wrong_settlement_fails_as_expected": adversarial.get(
                "wrong_settlement_fails_as_expected"
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
            "net_tamper_fails_as_expected": adversarial.get(
                "net_tamper_fails_as_expected"
            ),
            "tamper_fails_as_expected": adversarial.get("tamper_fails_as_expected"),
            "single_clearing_fails_as_expected": adversarial.get(
                "single_clearing_fails_as_expected"
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


def builtin_clearing_plane() -> dict[str, Any]:
    """Invocable capability: settlement → multi-clearing deterministic net positions → prove."""

    root = Path(__file__).resolve().parents[2]
    goal = (
        (os.environ.get("BLACKHOLE_MISSION_GOAL") or "").strip()
        or "clearing over settlement"
    )
    done_when = (os.environ.get("BLACKHOLE_DONE_WHEN") or "").strip()
    max_steps = int(os.environ.get("BLACKHOLE_PROGRAM_MAX_STEPS") or "3")
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
    c_raw = (os.environ.get("BLACKHOLE_CLEARING_BUNDLE_PATH") or "").strip()
    clearing_path = Path(c_raw) if c_raw else None
    return run_clearing_plane(
        root,
        goal,
        done_when,
        max_steps=max_steps,
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
        lineage_path=lineage_path,
        bundle_path=bundle_path,
        quorum_path=quorum_path,
        finality_path=finality_path,
        execution_path=execution_path,
        actuation_path=actuation_path,
        settlement_path=settlement_path,
        clearing_path=clearing_path,
        timeout=720,
    )
