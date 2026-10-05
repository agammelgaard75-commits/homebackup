# Network isolation assessment — 2026-10-05

Assessed 14:10–14:20 UTC from `192.168.2.100` on `ens18`.

**Verdict: FAIL for containment of requests to other internal hosts. The allowed Ollama endpoint provides an indirect path into the protected LAN.** The former native-LAN IPv6 and guest VLAN-tagging escapes were not reproduced.

## High: unauthenticated Ollama model fetching bypasses direct network isolation

Confirmed path:

```text
192.168.2.100 → 192.168.3.189:11434 /api/pull
             → 192.168.1.43:8080 → 192.168.1.43:8443
```

`192.168.3.189:11434` identifies itself as Ollama **0.35.1**. The host and existing n8n network namespace can both access it. No authentication was supplied. `/api/tags` and `/v1/models` expose 17 installed model names.

The API accepts a caller-selected registry address through `/api/pull`. Using unique nonexistent model names and `insecure: true`, I caused the Ollama process to request a controlled HTTP endpoint on this scan host. The callback arrived **from `192.168.3.189`**, with user agent `ollama/0.35.1 (amd64 windows) Go/go1.26.0`. The listener returned HTTP 418 and a unique marker; Ollama returned that marker in its error response. No valid model manifest or blob was served.

Subsequent bounded requests demonstrated access to another internal host:

| Destination | Direct from scan host | Through Ollama |
| --- | --- | --- |
| `192.168.1.43:8080` | TCP timeout | HTTP redirect to `https://192.168.1.43:8443/...`, followed by certificate verification failure |
| `192.168.1.43:8443` | TCP timeout | TLS handshake reaches an untrusted certificate; a separate plaintext request returns HTTP 400 with `This combination of host and port requires TLS.` |
| `192.168.1.43:22` | TCP timeout | Ollama reports a connection established from `192.168.3.189`, then reset while reading; protocol identity unverified |
| `192.168.3.189:445` | TCP timeout | Ollama reports a connection established to its own LAN address, then reset while reading; protocol identity unverified |
| `127.0.0.1:11434` on Ollama host | Not applicable | Nonexistent registry path receives HTTP 404, surfaced as `file does not exist` |

The 8080/8443 results were repeated. A certificate-validation error is positive TLS reachability evidence, although certificate validation prevented fetching the HTTPS body. The separate plaintext HTTP 400 response confirms application communication and response-body reflection. Connection-refused errors on other destinations establish rejection, not an open service; client timeouts are inconclusive.

**Impact:** a process permitted to call Ollama can make the more trusted Ollama host initiate internal HTTP requests and relay some responses. Direct firewall rules on the scan host do not contain that behavior. This is a confirmed server-side request capability exposed across the trust boundary; it is not a claim of code execution, login access, or a newly assigned CVE. No credentials were requested or used.

The tested behavior is consistent with the version's [registry-fetch implementation](https://github.com/ollama/ollama/blob/v0.35.1/server/images.go) and [pull request handler](https://github.com/ollama/ollama/blob/v0.35.1/server/routes.go): callers supply the registry and insecure option, and insecure mode permits cross-host redirects. The exposure and trust-boundary failure matter even when private-registry support is intentional.

Evidence: [controlled callback and initial probes](isolation-audit/retest-20261005T1411Z/ollama-fetch-probe.json), [additional internal probes](isolation-audit/retest-20261005T1411Z/ollama-internal-probes.json), [repeated direct-versus-indirect comparison](isolation-audit/retest-20261005T1411Z/pivot-confirmation.json), [API responses and CORS](isolation-audit/retest-20261005T1411Z/ollama-api.json), [container Ollama response](isolation-audit/retest-20261005T1411Z/container-ollama.txt). Reproduction scripts are retained alongside these files; they perform active requests if run.

## Coverage and other results

| Check | Coverage | Result |
| --- | --- | --- |
| Full TCP scan of Ollama host | All 65,535 TCP ports on `192.168.3.189` | Only 11434 open; 65,534 no-response/filtered |
| Three-subnet TCP sweep | 42 selected service ports across `192.168.1.0/24`, `192.168.2.0/24`, `192.168.3.0/24`, excluding this host; 767 addresses, including subnet boundary addresses | Only `192.168.3.189:11434` open |
| Broader known-host TCP scans | Top 1,000 TCP ports on `192.168.1.1`, `.43`, `.50`, `.201`, `192.168.2.1`, `192.168.3.1` | All 6,000 no-response/filtered |
| IPv6 services | 16 TCP ports on 10 historical link-local peers | Router TCP 53 open, 15 router ports refused; all 144 non-router combinations no response |
| IPv6 discovery | Two all-nodes echo requests | Only router responds, excluding this host |
| Router DNS | Benign `example.com A` query | Link-local IPv6 UDP DNS answers; IPv4 times out; former ULA has no local route |
| Local ARP sweep | `192.168.2.0/24` | Only gateway and this host reported |
| VLAN/native ARP | Native, VLAN 1/2/3, priority tag 0, double tags 2→3 / 0→3 / 2→1, 802.1ad outer tag | Only own-segment gateway replies to untagged and priority-tag-0 controls; no other-network replies |
| Firewall variants | Source TCP ports 53 and 443, fragmented SYN; six hosts and nine destination ports per variant | Only Ollama 11434 responds |
| UDP sample | Ten ports on five known hosts | All 50 open-or-filtered due to no response; **no UDP service demonstrated by this scan** |
| Container-origin TCP | Five hosts, 13 ports each | Only Ollama 11434 open |
| Internet control | Host and existing n8n namespace, IPv4 HTTPS | Both HTTP 200 |
| CORS preflight | External example origin, local-IP origin, localhost origin | External and local-IP origins refused; localhost allowed. This does not authenticate direct API clients. |

Router DNS is `fe80::6c63:f8ff:fe15:eaa0%ens18`. It remains a reachable application service; whether it is a policy exception depends on the intended DNS allowance.

The previous retests used only eight destination TCP ports and omitted 11434, so their results did not establish that Ollama was blocked. Today's broad results do not establish when the Ollama allowance was introduced.

Machine-readable [scan summary](isolation-audit/retest-20261005T1411Z/scan-summary.json) includes exact Nmap commands, counts and completion status. Raw `.xml`, `.nmap`, `.gnmap`, and `.log` outputs are retained for every Nmap scan. Additional evidence: [baseline](isolation-audit/retest-20261005T1411Z/baseline.txt), [VLAN probes](isolation-audit/retest-20261005T1411Z/l2-probe.json), [tag variants](isolation-audit/retest-20261005T1411Z/tag-variants.json), [DNS/application checks](isolation-audit/retest-20261005T1411Z/service-proof.json), [multicast](isolation-audit/retest-20261005T1411Z/multicast-ens18.json), [container scan](isolation-audit/retest-20261005T1411Z/container-ipv4.txt).

## Remediation priorities — not applied

1. **Constrain the allowed Ollama API.** Put an authenticated gateway with an explicit route allowlist in front of it. Expose only the inference operations required by this isolated workload; keep model-fetch and model-management operations on a separate trusted administration path. Authentication alone does not contain a caller that legitimately holds an inference credential if it can still invoke `/api/pull`.
2. **Restrict egress from the Ollama process or its isolated runtime.** Deny protected LAN and host-local services except explicit requirements; permit necessary registry access deliberately. Apply controls where local administrator access in the scan guest cannot change them.
3. **Retest the actual request chain after changes.** Allowed inference should still work, while the controlled callback, private-registry fetches, and redirects to `192.168.1.43` should fail. Include container-origin access in the retest.
4. Keep the working external VLAN restrictions. Decide explicitly whether router IPv6 DNS belongs on this segment's allowlist.

## Safety, cleanup and limits

No firewall, route, interface, service configuration, or account settings were changed. No model inference, model creation/deletion, valid model downloads, credential attacks, ARP poisoning, persistent tunnels, or code-execution payloads were used. The callback HTTP listener was temporary and is closed. All **17 model names and digests match the pre-test inventory**; see [cleanup verification](isolation-audit/retest-20261005T1411Z/cleanup-verification.json). Normal service logs, counters and neighbor caches may reflect the probes.

This was a full TCP-port scan of the named Ollama host plus a broad, explicitly bounded isolation assessment. It was **not** all 65,535 ports on every address, a full UDP scan, or a complete application vulnerability audit. Unknown subnets, every VLAN ID, alternate-address assignment, inbound access from a separate machine, and reboot persistence were not tested. Nmap `-Pn` labels hosts up by assumption; the 767 reported addresses are not 767 discovered live machines. Filtered ports and timeouts are absence of a response, not proof of isolation. Some application probes used 5–6 second client deadlines. Internet access from the container used a host-resolved address and does not validate container DNS configuration.

---

# Previous assessments

# Network isolation assessment

## Historical retest: 2026-10-04, 09:41 UTC

**Previously demonstrated native-LAN and VLAN 3 escapes were not reproduced. Internet HTTPS works; router link-local DNS remains reachable.**

| Check | Fresh result |
| --- | --- |
| Nine prior non-router IPv6 peers, TCP 22/53/80/443/445/8006/8080/8443 | All 72 connections received no response; additional SSH/HTTP application probes timed out |
| Router `fe80::6c63:f8ff:fe15:eaa0%ens18` | TCP 53 open; UDP DNS returned a matching successful response to `example.com A`; other seven sampled TCP ports refused connections |
| IPv6 multicast discovery on `ens18` | Only router responded, excluding this host |
| Native/untagged ARP to `192.168.1.1` and `192.168.1.50` | No replies to two requests each |
| Guest-tagged VLAN 3 ARP to `192.168.3.1` | No replies to two requests |
| Guest-tagged VLAN 2 ARP to `192.168.2.1` | No replies to two requests |
| Untagged ARP control to `192.168.2.1` | Reply received; no VLAN tag in frame or offload metadata |
| Host routed IPv4, seven previous targets and eight TCP ports each | All 56 connections received no response |
| Existing n8n network namespace, three gateways and six TCP ports each | All 18 connections received no response |
| Host IPv4 HTTPS to `example.com` | HTTP 200 |
| n8n network namespace IPv4 HTTPS, using host-resolved address | HTTP 200 |
| Router IPv4 UDP DNS | Timed out |
| Former router ULA UDP DNS | Local network-unreachable error |

**Current guest configuration:** `192.168.2.100/24` and the default route via `192.168.2.1` are on `ens18`. The old `ens18.2` interface is absent. `ens18` still has link-local IPv6 and no IPv6 default route. Untagged gateway traffic remains visible inside the guest; this is consistent with VLAN 2 assignment at an external access port, and does not mean the former native LAN is exposed. Hypervisor/switch tagging was not inspected.

**Remaining exception:** router DNS is reachable over link-local IPv6. If DNS is approved on this segment, this is consistent with that exception. If all router application services should be denied, this remains a policy gap.

Evidence: [configuration](isolation-audit/retest-20261004T094120Z/baseline.txt), [ARP/VLAN probes](isolation-audit/retest-20261004T094120Z/l2-probe.json), [IPv6 TCP](isolation-audit/retest-20261004T094120Z/ipv6-services.txt), [application/DNS](isolation-audit/retest-20261004T094120Z/service-proof.json), [IPv6 discovery](isolation-audit/retest-20261004T094120Z/multicast-ens18.json), [host IPv4](isolation-audit/retest-20261004T094120Z/routed-ipv4.txt), [container IPv4](isolation-audit/retest-20261004T094120Z/container-ipv4.txt), [host HTTPS](isolation-audit/retest-20261004T094120Z/internet-ipv4.txt), [container HTTPS](isolation-audit/retest-20261004T094120Z/container-internet.txt).

Scope: bounded repeat of previously observed paths. Timeouts establish no observed response, not exhaustive isolation. Nmap's `Host is up, received user-set` is an assumption from `-Pn`, not discovery evidence. Container HTTPS tests egress using a host-resolved public address; it does not validate the application's DNS configuration. Other VLANs, ports, protocols, inbound access, persistence and historical host-hardening findings were not reassessed. No configuration changes or authentication attempts were made.

---

## Historical retest: 2026-10-04, 08:09–08:11 UTC

**Previously demonstrated native-LAN and VLAN 3 escapes were not reproduced. Router link-local DNS remains reachable.**

| Check | Fresh result |
| --- | --- |
| Prior IPv6 LAN peers, including SSH and Proxmox TCP 8006 | All eight sampled ports on all nine non-router peers timed out; SSH/HTTP application checks also timed out |
| Native/untagged ARP to `192.168.1.1` and `192.168.1.50` | No replies to two requests each |
| Guest-tagged VLAN 3 ARP to `192.168.3.1` | No replies to two requests |
| Guest-tagged VLAN 2 ARP to `192.168.2.1` | No replies to two requests |
| Untagged ARP control to `192.168.2.1` | Replies received, with no VLAN tag including offload metadata |
| IPv6 multicast discovery | Only router responded on `ens18`; no other peer responded on `ens18.2`, excluding self |
| Router `fe80::6c63:f8ff:fe15:eaa0%ens18` | TCP 53 open; UDP DNS returned a matching successful `example.com A` response; other seven sampled TCP ports refused connections |
| Router IPv6 DNS on `ens18.2` | Timed out |
| Host routed IPv4: seven previous targets, eight ports each | All timed out |
| Existing n8n network namespace: three gateways, six ports each | All timed out |
| Host Internet HTTPS | HTTP 200 |
| n8n network namespace Internet HTTPS with host-resolved address | HTTP 200 |

**Tagging interpretation:** `192.168.2.100/24` and the default route are now on `ens18`. `ens18.2` retains only a link-local IPv6 address. The successful untagged gateway control and unsuccessful guest-tagged controls are consistent with an access port assigning VLAN 2 outside the guest. This is an inference: no hypervisor or switch configuration was inspected. Untagged frames remain visible inside the VM; these results do not establish whether uplink traffic carries VLAN tags. The former native LAN is no longer reachable by the sampled probes.

**Remaining policy exception:** router DNS is accessible using link-local IPv6. If router DNS is an approved service on the isolation segment, this result is consistent with that exception. If the intended policy denies all router application services, that requirement still fails. This is not evidence of continued VLAN 3 or native-LAN access.

Evidence: [configuration](isolation-audit/retest-20261004T080927Z/baseline.txt), [ARP/VLAN probes](isolation-audit/retest-20261004T080927Z/l2-probe.json), [IPv6 TCP checks](isolation-audit/retest-20261004T080927Z/ipv6-services.txt), [application/DNS checks](isolation-audit/retest-20261004T080927Z/service-proof.json), [discovery on ens18](isolation-audit/retest-20261004T080927Z/multicast-ens18.json), [discovery on ens18.2](isolation-audit/retest-20261004T080927Z/multicast-ens18.2.json), [host IPv4](isolation-audit/retest-20261004T080927Z/routed-ipv4.txt), [container IPv4](isolation-audit/retest-20261004T080927Z/container-ipv4.txt), [host HTTPS](isolation-audit/retest-20261004T080927Z/internet-ipv4.txt), [container HTTPS](isolation-audit/retest-20261004T080927Z/container-internet-resolved.txt).

Scope: bounded retest of previously observed paths, not exhaustive isolation certification. No network configuration changes, authentication, exploitation, or service changes. `ping` was unavailable, so multicast discovery used two raw ICMPv6 echo requests per interface. The initial namespace-only container HTTPS command could not resolve its hostname; the follow-up used a host-resolved public address and succeeded, verifying HTTPS egress but not the container application's DNS setup. Hypervisor enforcement, other VLANs/protocols, inbound management and reboot persistence were not verified. Historical host-hardening findings below were not reassessed.

---

## Historical retest: 2026-10-04, 07:34–07:36 UTC

**Verdict remains FAIL. Disabling routed IPv6 has not removed the local-network bypass.**

The previous ULA address (`fd8b:7c34:a921:20:be24:11ff:feac:52ab`) and IPv6 default route have disappeared. However, `ens18` and `ens18.2` retain `fe80::be24:11ff:feac:52ab/64` and their link-local routes. The IPv6 disable flags for `all`, `default`, `ens18`, and `ens18.2` are all **0**, meaning IPv6 is still enabled on this host. These observations establish the host state; the upstream device's configuration was not inspected.

Fresh connections, rather than cached neighbor entries, confirmed:

| Retest | Result |
| --- | --- |
| `fe80::f64d:30ff:fe60:69ad%ens18`, TCP 22 and 8006 | Still open. Fresh SSH banner and TLS/HTTP response identifying `pve-api-daemon/3.0` |
| `fe80::be24:11ff:fe4b:3ef5%ens18`, TCP 22/8080/8443 | Still open; fresh SSH banner and HTTP 302 |
| `fe80::be24:11ff:febe:aa22%ens18`, TCP 22 | Still open; fresh SSH banner |
| `fe80::aef2:3cff:feab:af25%ens18`, TCP 80/443 | Still open; fresh HTTP response on 80 |
| Router link-local DNS on both `ens18` and `ens18.2` | Still answers UDP queries; TCP 53 also open on `ens18` |
| Native/untagged ARP to `192.168.1.1` | Still receives an untagged reply |
| VLAN 3 ARP to `192.168.3.1` | Still receives a VLAN 3 reply, verified using VLAN-offload metadata |
| VLAN 2 ARP control to `192.168.2.1` | Receives VLAN 2 reply |
| Routed IPv4 TCP 22/53/80/443/8006 to `192.168.1.1`, `192.168.2.1`, `192.168.3.1` | All timed out |
| IPv4 Internet HTTPS to `example.com` | HTTP 200 |
| IPv6 Internet HTTPS to `example.com` | Connection failed; IPv6 default route absent |
| UDP query to former gateway ULA `fd8b:7c34:a921:20::1` | Local `Network is unreachable` error |

**Explanation:** the confirmed bypass uses direct link-local communication on `ens18`, which still has a link-local address and route. It does not need the removed ULA address or an IPv6 default route. The separate native-LAN and VLAN 3 Ethernet exposures also remain. Removing routed IPv6 alone therefore does not establish containment.

**Required fix remains external VLAN enforcement:** restrict this guest's virtual port to its intended isolation segment and remove native-LAN/other-VLAN access. See the original remediation priorities below. No host or network settings were changed during this retest, and no authentication or exploitation was attempted.

Retest evidence: [current configuration](isolation-audit/retest-20261004T0734Z/baseline.txt), [TCP scan](isolation-audit/retest-20261004T0734Z/untagged-ipv6-services.txt), [SSH/HTTP/DNS responses](isolation-audit/retest-20261004T0734Z/service-proof.json), [Proxmox response](isolation-audit/retest-20261004T0734Z/port8006-proof.json), [ARP/VLAN replies](isolation-audit/retest-20261004T0734Z/l2-probe.json), [IPv4 and Internet controls](isolation-audit/retest-20261004T0734Z/controls.txt).

The original assessment below is retained as historical evidence; its ULA/default-route observations describe the first run, not the current state. This retest repeated the previously discovered peer TCP checks and bounded application/ARP probes. It did not repeat multicast discovery, container-namespace tests, or passive observation.

---

## Original assessment

**Verdict: FAIL — this server is not boxed into its intended local-network segment.**

Assessed on **2026-10-04, approximately 07:13–07:20 UTC**. Host: `sandbox`, Ubuntu 24.04.5 LTS, KVM guest. The configured IPv4 address is `192.168.2.100/24` on guest VLAN interface `ens18.2`.

The normal routed IPv4 path appears filtered for the sampled destinations and ports. However, the parent interface `ens18` exposes another local network over IPv6, and guest-generated VLAN 3 frames receive replies. I reached local SSH and web services, including a service identifying itself as a **Proxmox API daemon**, without changing any networking configuration or attempting authentication.

## Confirmed findings

### 1. Critical: local services accessible through the untagged IPv6 interface

Two IPv6 multicast echo requests on each interface found **10 other responding addresses on `ens18`**, versus only the router on `ens18.2`. Self-responses were excluded from these counts.

Ordinary TCP connections as user `bot`, without sudo, confirmed these open ports. All addresses below use scope `%ens18`:

| IPv6 link-local address | Open TCP ports | Additional evidence |
| --- | --- | --- |
| `fe80::f64d:30ff:fe60:69ad` | 22, 8006 | SSH banner; TLS/HTTP response on 8006 identifies `Server: pve-api-daemon/3.0` |
| `fe80::be24:11ff:fe4b:3ef5` | 22, 8080, 8443 | OpenSSH banner; HTTP 302 on 8080 |
| `fe80::be24:11ff:febe:aa22` | 22 | OpenSSH banner |
| `fe80::aef2:3cff:feab:af25` | 80, 443 | HTTP response on 80 |
| `fe80::6c63:f8ff:fe15:eaa0` | 53 | Successful DNS response, also verified over UDP |

The Proxmox service returned HTTP 501 because HEAD is unsupported; this still establishes successful TCP, TLS and application communication. Its banner suggests a virtualization management endpoint. I did not verify whether it hosts this VM.

**Impact:** a process on this server can contact local infrastructure directly over IPv6. This bypass does not require adding an address, changing a route, root privileges, or traversing the IPv4 gateway. Reachability is proven; compromise of those services was neither attempted nor established.

Evidence: [IPv6 service scan](isolation-audit/untagged-ipv6-services.txt), [minimal service responses](isolation-audit/service-proof.json), [Proxmox service response](isolation-audit/port8006-proof.json), [neighbor discovery](isolation-audit/ipv6-neighbors.json).

### 2. High: the guest can exchange traffic outside VLAN 2 at Ethernet level

I sent two ARP requests per target using this NIC's real MAC address and sender IPv4 address `0.0.0.0`. No ARP replies, gratuitous announcements, address assignments, or interface changes were made.

| Ethernet path | Target | Result |
| --- | --- | --- |
| Untagged/native | `192.168.1.1` | ARP reply received, untagged |
| Untagged/native | `192.168.1.50` | No reply to these probes |
| VLAN 2, control | `192.168.2.1` | ARP reply received on VLAN 2 |
| **VLAN 3** | **`192.168.3.1`** | **ARP reply received on VLAN 3** |

The probe reads Linux `PACKET_AUXDATA` to account for VLAN tags stripped by NIC/kernel offloading. The reply MAC was `6e:63:f8:15:ea:a0` for all responding gateways.

**Impact:** the VM's Ethernet attachment is not restricted to VLAN 2. Native-network access is independently demonstrated by the IPv6 connections above. VLAN 3 bidirectional ARP access is proven; TCP access from a VLAN 3 IPv4 address was not tested. An overly permissive virtual bridge/trunk is a likely cause, but the hypervisor configuration was not available for inspection.

Evidence and reproducible probe: [ARP results](isolation-audit/l2-probe.json), [probe source](isolation-audit/l2-probe.py).

### 3. Medium: router DNS remains accessible through link-local IPv6

Gateway TCP probes to `192.168.2.1` and `fd8b:7c34:a921:20::1` timed out on the eight sampled ports. UDP DNS queries to both addresses also timed out.

In contrast, `fe80::6c63:f8ff:fe15:eaa0%ens18.2` and the same address scoped to `%ens18` accepted TCP connections on port 53 and answered a benign UDP `example.com A` query with matching transaction ID, response code 0, two answers and recursion available.

This is an application-level exception beyond necessary neighbor discovery. It may be intentional, but no approved exception list was supplied. It does not establish a DNS vulnerability or access to other internal services.

Evidence: [gateway IPv4](isolation-audit/gateway-ipv4.txt), [gateway IPv6](isolation-audit/gateway-ipv6.txt), [DNS responses](isolation-audit/service-proof.json).

### 4. Host firewall provides no fallback containment

- UFW is inactive. IPv4 and IPv6 INPUT/OUTPUT policies accept traffic, with no host isolation rules found in nftables or legacy iptables.
- IPv4 forwarding is enabled. Docker's `DOCKER-USER` chain is empty; the Docker bridge has outbound forwarding/NAT rules.
- SSH listens on all IPv4/IPv6 addresses. LiteLLM listens on IPv4 port 4000. The `n8n` container publishes port 5678 on all IPv4/IPv6 addresses.
- Effective default SSH settings include `permitrootlogin yes`, `passwordauthentication yes` and `allowtcpforwarding yes`. These are additional hardening concerns, not evidence that any password works; per-connection Match rules and account state were not evaluated.
- An existing SSH connection from `192.168.3.189` to this server was observed. This establishes an inbound management path, potentially intentional, and reinforces the need to preserve management access during remediation.

An IPv4-only container can still be exposed through the host's IPv6 port publishing, as seen in this server's listeners and documented by [Docker](https://docs.docker.com/engine/network/port-publishing/).

Evidence: [firewalls, listeners and SSH settings](isolation-audit/baseline.txt), [network and container details](isolation-audit/network-details.txt).

## Tests that did not find a bypass

| Test | Observed result |
| --- | --- |
| Host → `192.168.2.1`, TCP 22/53/80/443/445/8006/8080/8443 | All timed out |
| Host → `192.168.1.1`, `.43`, `.50`, `.201`, and `192.168.3.1`, `.189`, same ports | All timed out |
| Existing n8n network namespace → `192.168.1.1`, `192.168.2.1`, `192.168.3.1`, TCP 22/53/80/443/445/8006 | All timed out |
| Host → gateway ULA `fd8b:7c34:a921:20::1`, eight TCP ports above | All timed out |
| Direct IPv4 HTTPS to `example.com`, proxies disabled | HTTP 200; permitted Internet access works |
| Direct IPv6 HTTPS to `example.com`, proxies disabled | Connection timed out |

Timeouts are consistent with upstream filtering; they do not prove every destination or protocol is blocked. Nmap used `-Pn`, so its “Host is up, received user-set” text is an assumption, not a successful discovery result. Port service names are Nmap labels unless separately confirmed by a response.

Evidence: [routed IPv4](isolation-audit/routed-ipv4.txt), [container IPv4](isolation-audit/container-ipv4.txt), [Internet controls](isolation-audit/internet-controls.txt).

## Work performed and safety

Inspected interfaces, IPv4/IPv6 routes, policy routing, neighbors, resolver settings, Netplan, firewall rules, listening sockets, SSH defaults and Docker networking. Used bounded TCP connect scans with eight or fewer ports per target, one retry and configured maximum rate 10; brief multicast discovery; four UDP DNS queries; eight ARP requests; and minimal SSH banners/HTTP HEAD responses. Container-origin probes entered only the existing container's network namespace using host tools; no container image or application was modified.

A 12-second passive observation collected address-header summaries only, without promiscuous mode or retained payloads. These initial summaries do **not** account for VLAN offload and must not be used to classify frames as untagged; the dedicated ARP probe does account for offload. See [header summaries](isolation-audit/passive-headers.json).

No firewall, route, VLAN, address, sysctl, service, account or package settings were changed. No credentials, logins, exploitation, poisoning, floods, DHCP changes or reverse tunnels were used. Normal logs, counters and neighbor caches may reflect the probes. Local audit artifacts are the only deliberate persistent changes.

## Remediation priorities — not applied

1. **Enforce VLAN membership outside this guest.** Restrict the VM's virtual port to the isolation network, remove access to the native LAN and VLAN 3, and reject guest tags outside the permitted VLAN. An access-port design assigning VLAN 2 at the hypervisor is preferable where supported. Coordinate the guest configuration: the current guest already tags VLAN 2, so changing only the hypervisor tag can break connectivity. Proxmox documents host-side VLAN assignment in its [network configuration guide](https://pve.proxmox.com/wiki/Network_Configuration). Whether this VM's actual host uses Proxmox still requires verification.
2. **Enforce both IPv4 and IPv6 policy.** Restrict local destinations, including the actual ULA/global IPv6 LAN prefixes, and restrict gateway services to explicit exceptions. Retain the IPv6 control traffic needed by any supported IPv6 deployment. Removing a guest address or disabling guest IPv6 alone is insufficient containment against guest root access while other Ethernet segments remain exposed.
3. **Add host firewall protection and narrow listeners.** Preserve approved management access and Internet egress. Apply local-network egress restrictions to both host-generated and container-forwarded traffic. With this server's Docker iptables backend, use appropriate `DOCKER-USER` policy before Docker's forwarding accepts; INPUT/OUTPUT rules alone do not cover that path. See [Docker's firewall guidance](https://docs.docker.com/engine/network/firewall-iptables/). Bind application ports only where needed and review SSH authentication/forwarding settings.
4. **Retest from both sides.** Verify that native-LAN and VLAN 3 probes fail, the listed link-local services are unreachable, approved management still works, and IPv4 Internet HTTPS still succeeds. Repeat host and container tests against the complete intended subnet list, then verify persistence after a controlled restart.

Network changes could interrupt the active SSH session and applications. They require an approved change with console access and rollback; none were attempted during this assessment.

## Scope and confidence

**High confidence that isolation is broken**, based on successful application connections and VLAN-tagged replies. This is a sampled assessment, not a certification of all paths. The exact protected subnet list and management/DNS exceptions were not supplied; targets came from local configuration, existing connections, passive traffic and neighbor discovery. Unknown subnets, full port ranges, other VLAN IDs, inbound access from a separate machine, alternate source IPv4 addresses, NAT hairpin paths and third-party tunnel paths were not exhaustively tested. I did not access hypervisor/switch configuration or establish persistence after reboot.

Fixing the Ethernet attachment is the first priority. The working routed IPv4 filters do not prevent the confirmed local-network bypasses.
