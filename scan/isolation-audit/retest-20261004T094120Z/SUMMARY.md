# Network reachability retest

## Latest retest: 2026-10-04, 09:41 UTC

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

Evidence: [configuration](baseline.txt), [ARP/VLAN probes](l2-probe.json), [IPv6 TCP](ipv6-services.txt), [application/DNS](service-proof.json), [IPv6 discovery](multicast-ens18.json), [host IPv4](routed-ipv4.txt), [container IPv4](container-ipv4.txt), [host HTTPS](internet-ipv4.txt), [container HTTPS](container-internet.txt).

Scope: bounded repeat of previously observed paths. Timeouts establish no observed response, not exhaustive isolation. Nmap's `Host is up, received user-set` is an assumption from `-Pn`, not discovery evidence. Container HTTPS tests egress using a host-resolved public address; it does not validate the application's DNS configuration. Other VLANs, ports, protocols, inbound access, persistence and historical host-hardening findings were not reassessed. No configuration changes or authentication attempts were made.

---

