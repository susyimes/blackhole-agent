from pathlib import Path

from blackhole_agent.altsvc_actuation import (
    ALTSVC_ACTUATION_GOAL,
    ALTSVC_ACTUATION_ID,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.connectip_actuation import CONNECTIP_ACTUATION_GOAL, CONNECTIP_ACTUATION_ID
from blackhole_agent.datachannel_actuation import DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.http3_actuation import HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID
from blackhole_agent.datagram_actuation import DATAGRAM_ACTUATION_GOAL, DATAGRAM_ACTUATION_ID
from blackhole_agent.masque_actuation import MASQUE_ACTUATION_GOAL, MASQUE_ACTUATION_ID
from blackhole_agent.ohttp_actuation import OHTTP_ACTUATION_GOAL, OHTTP_ACTUATION_ID
from blackhole_agent.http11_actuation import HTTP11_ACTUATION_GOAL, HTTP11_ACTUATION_ID
from blackhole_agent.http2_actuation import HTTP2_ACTUATION_GOAL, HTTP2_ACTUATION_ID
from blackhole_agent.httpcache_actuation import HTTPCACHE_ACTUATION_GOAL, HTTPCACHE_ACTUATION_ID
from blackhole_agent.httpsemantics_actuation import HTTPSMANTICS_ACTUATION_GOAL, HTTPSMANTICS_ACTUATION_ID
from blackhole_agent.clienthints_actuation import CLIENTHINTS_ACTUATION_GOAL, CLIENTHINTS_ACTUATION_ID
from blackhole_agent.structuredfields_actuation import (
    STRUCTUREDFIELDS_ACTUATION_GOAL,
    STRUCTUREDFIELDS_ACTUATION_ID,
)
from blackhole_agent.earlyhints_actuation import EARLYHINTS_ACTUATION_GOAL, EARLYHINTS_ACTUATION_ID
from blackhole_agent.encryptedcontent_actuation import (
    CONTENT_CODING,
    DEFAULT_ENCID,
    DEFAULT_ECEDIGEST,
    EMPTY_ENCID,
    FRAME_ENCRYPT,
    FRAME_DECRYPT,
    ENCRYPTEDCONTENT_ACTUATION_DONE_WHEN,
    ENCRYPTEDCONTENT_ACTUATION_GOAL,
    ENCRYPTEDCONTENT_ACTUATION_ID,
    ENCRYPTEDCONTENT_LEFTOVER,
    ECE_FIRST,
    RFC_CIPHER_B64,
    RFC_IKM_B64,
    RFC_SALT_B64,
    SENTINEL,
    encrypt_request,
    encrypt_response,
    builtin_encryptedcontent_actuation_proof,
    canonical_encrypt,
    canonical_decrypt,
    crc32c,
    decrypt_aes128gcm,
    decrypt_request,
    decrypt_response,
    encrypt_aes128gcm,
    encode_encrypt,
    encode_decrypt,
    independent_encryptedcontent_digest,
    parse_ece_header,
    parse_http_request,
    parse_http_response,
    parse_message,
    run_encryptedcontent_workflow,
    b64url,
    b64url_decode,
)
from blackhole_agent.bhttp_actuation import BHTTP_ACTUATION_GOAL, BHTTP_ACTUATION_ID
from blackhole_agent.digestfields_actuation import DIGESTFIELDS_ACTUATION_GOAL, DIGESTFIELDS_ACTUATION_ID
from blackhole_agent.httpsig_actuation import HTTPSIG_ACTUATION_GOAL, HTTPSIG_ACTUATION_ID
from blackhole_agent.ohsvcb_actuation import OHSVCB_ACTUATION_GOAL, OHSVCB_ACTUATION_ID
from blackhole_agent.ice_actuation import ICE_ACTUATION_GOAL, ICE_ACTUATION_ID
from blackhole_agent.ike_actuation import IKE_ACTUATION_GOAL, IKE_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.ntp_actuation import NTP_ACTUATION_GOAL, NTP_ACTUATION_ID
from blackhole_agent.quic_actuation import QUIC_ACTUATION_GOAL, QUIC_ACTUATION_ID
from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
from blackhole_agent.sctp_actuation import SCTP_ACTUATION_GOAL, SCTP_ACTUATION_ID
from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.srtp_actuation import SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID
from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    ENCRYPTEDCONTENT_TOOL_PROVIDER,
    build_tool_routing_preflight,
    encryptedcontent_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
    EARLYHINTS_ACTUATION_GOAL,
    CLIENTHINTS_ACTUATION_GOAL,
    STRUCTUREDFIELDS_ACTUATION_GOAL,
    HTTPSMANTICS_ACTUATION_GOAL,
    HTTPCACHE_ACTUATION_GOAL,
    HTTP2_ACTUATION_GOAL,
    HTTP11_ACTUATION_GOAL,
    BHTTP_ACTUATION_GOAL,
    DIGESTFIELDS_ACTUATION_GOAL,
    HTTPSIG_ACTUATION_GOAL,
    OHSVCB_ACTUATION_GOAL,
    OHTTP_ACTUATION_GOAL,
    CONNECTIP_ACTUATION_GOAL,
    MASQUE_ACTUATION_GOAL,
    DATAGRAM_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_GOAL,
    HTTP3_ACTUATION_GOAL,
    QUIC_ACTUATION_GOAL,
    DATACHANNEL_ACTUATION_GOAL,
    SCTP_ACTUATION_GOAL,
    SRTP_ACTUATION_GOAL,
    DTLS_ACTUATION_GOAL,
    ICE_ACTUATION_GOAL,
    TURN_ACTUATION_GOAL,
    STUN_ACTUATION_GOAL,
    SIP_ACTUATION_GOAL,
    IKE_ACTUATION_GOAL,
    DHCP_ACTUATION_GOAL,
    RADIUS_ACTUATION_GOAL,
    NTP_ACTUATION_GOAL,
    SYSLOG_ACTUATION_GOAL,
    SNMP_ACTUATION_GOAL,
    TFTP_ACTUATION_GOAL,
    FTP_ACTUATION_GOAL,
    DNS_ACTUATION_GOAL,
    ALTSVC_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
    EARLYHINTS_ACTUATION_ID,
    CLIENTHINTS_ACTUATION_ID,
    STRUCTUREDFIELDS_ACTUATION_ID,
    HTTPSMANTICS_ACTUATION_ID,
    HTTPCACHE_ACTUATION_ID,
    HTTP2_ACTUATION_ID,
    HTTP11_ACTUATION_ID,
    BHTTP_ACTUATION_ID,
    DIGESTFIELDS_ACTUATION_ID,
    HTTPSIG_ACTUATION_ID,
    OHSVCB_ACTUATION_ID,
    OHTTP_ACTUATION_ID,
    CONNECTIP_ACTUATION_ID,
    MASQUE_ACTUATION_ID,
    DATAGRAM_ACTUATION_ID,
    WEBTRANSPORT_ACTUATION_ID,
    HTTP3_ACTUATION_ID,
    QUIC_ACTUATION_ID,
    DATACHANNEL_ACTUATION_ID,
    SCTP_ACTUATION_ID,
    SRTP_ACTUATION_ID,
    DTLS_ACTUATION_ID,
    ICE_ACTUATION_ID,
    TURN_ACTUATION_ID,
    STUN_ACTUATION_ID,
    SIP_ACTUATION_ID,
    IKE_ACTUATION_ID,
    DHCP_ACTUATION_ID,
    RADIUS_ACTUATION_ID,
    NTP_ACTUATION_ID,
    SYSLOG_ACTUATION_ID,
    SNMP_ACTUATION_ID,
    TFTP_ACTUATION_ID,
    FTP_ACTUATION_ID,
    DNS_ACTUATION_ID,
    ALTSVC_ACTUATION_ID,
)


def test_goal_binds_encryptedcontent_actuation_plane() -> None:
    assert leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(ENCRYPTEDCONTENT_LEFTOVER) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(ALTSVC_ACTUATION_GOAL) == (ALTSVC_ACTUATION_ID,)
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert leftover_marker_ids(CLIENTHINTS_ACTUATION_GOAL) == (CLIENTHINTS_ACTUATION_ID,)
    assert ALTSVC_ACTUATION_ID in LOCAL_DENYLIST
    assert EARLYHINTS_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert ENCRYPTEDCONTENT_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL)
    encryptedcontent_signature = semantic_signature(ENCRYPTEDCONTENT_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(encryptedcontent_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_encryptedcontent_tool_completes_encrypt_decrypt_poll() -> None:
    descriptor = encryptedcontent_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ENCRYPTEDCONTENT_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("encryptedcontent",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ENCRYPTEDCONTENT_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["encryptedcontent"]

    missing = run_encryptedcontent_workflow(with_encid=False)
    skip_bind = run_encryptedcontent_workflow(skip_bind=True)
    skip_encrypt = run_encryptedcontent_workflow(do_encrypt=False)
    skip_decrypt = run_encryptedcontent_workflow(do_decrypt=False)
    skip_ecedigest = run_encryptedcontent_workflow(do_ecedigest=False)
    skip_replay = run_encryptedcontent_workflow(replay=False)
    skip_encid = run_encryptedcontent_workflow(use_encid=False)
    live = run_encryptedcontent_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_encid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_encrypt["ok"] is False
    assert skip_encrypt["error"] == "encrypt_required"
    assert skip_decrypt["ok"] is False
    assert skip_decrypt["error"] == "decrypt_required"
    assert skip_ecedigest["ok"] is False
    assert skip_ecedigest["error"] == "ecedigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_encid["ok"] is False
    assert skip_encid["error"] == "encid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_encryptedcontent_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["encrypt_frame"] is True
    assert row["decrypt_frame"] is True
    assert row["ecedigest_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["encid_bound"] is True
    assert row["digest"]
    assert live["encid"] == DEFAULT_ENCID
    assert live["ecedigest"] == DEFAULT_ECEDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_encrypt(identity=SENTINEL, encid=DEFAULT_ENCID, ecedigest=DEFAULT_ECEDIGEST)
    )
    assert queried["is_encrypt"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["encid"] == DEFAULT_ENCID
    assert queried["ecedigest"] == DEFAULT_ECEDIGEST
    assert queried["type"] == FRAME_ENCRYPT
    assert queried["first_byte"] == ECE_FIRST
    answered = parse_message(
        encode_decrypt(identity=SENTINEL, encid=DEFAULT_ENCID, ecedigest=DEFAULT_ECEDIGEST)
    )
    assert answered["is_decrypt"] is True and answered["is_response"] is True
    assert answered["encid"] == DEFAULT_ENCID
    assert answered["ecedigest"] == DEFAULT_ECEDIGEST
    packed = encode_encrypt(identity=SENTINEL, encid=DEFAULT_ENCID, ecedigest=DEFAULT_ECEDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_encrypt(identity=SENTINEL, encid=DEFAULT_ENCID, include_encid=False)
    )
    assert bare["has_encid"] is False
    assert bare["encid"] == EMPTY_ENCID
    ikm = b64url_decode(RFC_IKM_B64)
    salt = b64url_decode(RFC_SALT_B64)
    walrus = b"I am the walrus"
    cipher = encrypt_aes128gcm(walrus, ikm, salt)
    assert b64url(cipher) == RFC_CIPHER_B64
    assert decrypt_aes128gcm(cipher, ikm) == walrus
    header = parse_ece_header(cipher)
    assert header["rs"] == 4096
    assert header["idlen"] == 0
    assert header["content_coding"] == CONTENT_CODING
    asked = parse_http_request(encrypt_request(SENTINEL, DEFAULT_ENCID, cipher))
    listed = parse_http_request(decrypt_request(SENTINEL, DEFAULT_ENCID, DEFAULT_ECEDIGEST, cipher))
    got = parse_http_response(encrypt_response(SENTINEL, DEFAULT_ENCID, DEFAULT_ECEDIGEST, cipher))
    decrypt_reply = parse_http_response(
        decrypt_response(SENTINEL, DEFAULT_ENCID, DEFAULT_ECEDIGEST, walrus)
    )
    assert asked["method"] == "POST"
    assert asked["ece_kind"] == "encrypt"
    assert asked["content_encoding"] == CONTENT_CODING
    assert listed["ece_kind"] == "decrypt"
    assert got["status"] == 201
    assert decrypt_reply["status"] == 200
    assert got["content_encoding"] == CONTENT_CODING
    assert decrypt_reply["body"] == walrus
    assert canonical_encrypt(SENTINEL, DEFAULT_ENCID).startswith(CONTENT_CODING)
    assert "ecedigest=" in canonical_decrypt(SENTINEL, DEFAULT_ENCID, DEFAULT_ECEDIGEST)


def test_builtin_proof_seals_encryptedcontent_actuation() -> None:
    report = builtin_encryptedcontent_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "encryptedcontent_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_encryptedcontent"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_encid_is_forbidden"]
    assert report["checks"]["skip_encrypt_stays_empty"]
    assert report["checks"]["skip_decrypt_stays_empty"]
    assert report["checks"]["skip_ecedigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_encid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_ecedigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_encryptedcontent"]
    assert report["checks"]["catalog_names_encryptedcontent"]
    assert report["checks"]["catalog_names_altsvc"]
    assert report["checks"]["leftover_text_binds_encryptedcontent"]
    assert report["checks"]["proved_encryptedcontent_consumes_leftover"]
    assert report["mission_goal"] == ENCRYPTEDCONTENT_ACTUATION_GOAL
    assert report["done_when"] == ENCRYPTEDCONTENT_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[ENCRYPTEDCONTENT_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "encryptedcontent" in capability.tags
    assert "rfc8188" in capability.tags
    assert "http" in capability.tags
    assert "encid" in capability.tags
    assert "ecedigest" in capability.tags
    assert "aes128gcm" in capability.tags


def test_selection_gate_accepts_encryptedcontent_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        ENCRYPTEDCONTENT_ACTUATION_GOAL,
        ENCRYPTEDCONTENT_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(ENCRYPTEDCONTENT_ACTUATION_GOAL)
    assert "encryptedcontent" in family
    assert "rfc8188" in family
    assert "encid" in family
    assert "ecedigest" in family
    assert "earlyhint" not in family
    assert "rfc8297" not in family
    assert "linkid" not in family
    assert "altsvc" not in family
    assert "rfc7838" not in family
    assert "altsvcid" not in family
    assert "origindigest" not in family
    assert "rfc9000" not in family
    assert "http3" not in family
    assert "clienthint" not in family
    assert "rfc8942" not in family
    assert "chid" not in family
    assert "structuredfield" not in family
    assert "rfc8941" not in family
    assert "dictid" not in family
    assert "sfv" not in family
