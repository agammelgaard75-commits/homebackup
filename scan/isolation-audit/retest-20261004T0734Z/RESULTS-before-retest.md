# Network isolation assessment

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
