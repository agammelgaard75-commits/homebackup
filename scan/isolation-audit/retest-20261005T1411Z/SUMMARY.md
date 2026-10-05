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

Evidence: [controlled callback and initial probes](ollama-fetch-probe.json), [additional internal probes](ollama-internal-probes.json), [repeated direct-versus-indirect comparison](pivot-confirmation.json), [API responses and CORS](ollama-api.json), [container Ollama response](container-ollama.txt). Reproduction scripts are retained alongside these files; they perform active requests if run.

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

Machine-readable [scan summary](scan-summary.json) includes exact Nmap commands, counts and completion status. Raw `.xml`, `.nmap`, `.gnmap`, and `.log` outputs are retained for every Nmap scan. Additional evidence: [baseline](baseline.txt), [VLAN probes](l2-probe.json), [tag variants](tag-variants.json), [DNS/application checks](service-proof.json), [multicast](multicast-ens18.json), [container scan](container-ipv4.txt).

## Remediation priorities — not applied

1. **Constrain the allowed Ollama API.** Put an authenticated gateway with an explicit route allowlist in front of it. Expose only the inference operations required by this isolated workload; keep model-fetch and model-management operations on a separate trusted administration path. Authentication alone does not contain a caller that legitimately holds an inference credential if it can still invoke `/api/pull`.
2. **Restrict egress from the Ollama process or its isolated runtime.** Deny protected LAN and host-local services except explicit requirements; permit necessary registry access deliberately. Apply controls where local administrator access in the scan guest cannot change them.
3. **Retest the actual request chain after changes.** Allowed inference should still work, while the controlled callback, private-registry fetches, and redirects to `192.168.1.43` should fail. Include container-origin access in the retest.
4. Keep the working external VLAN restrictions. Decide explicitly whether router IPv6 DNS belongs on this segment's allowlist.

## Safety, cleanup and limits

No firewall, route, interface, service configuration, or account settings were changed. No model inference, model creation/deletion, valid model downloads, credential attacks, ARP poisoning, persistent tunnels, or code-execution payloads were used. The callback HTTP listener was temporary and is closed. All **17 model names and digests match the pre-test inventory**; see [cleanup verification](cleanup-verification.json). Normal service logs, counters and neighbor caches may reflect the probes.

This was a full TCP-port scan of the named Ollama host plus a broad, explicitly bounded isolation assessment. It was **not** all 65,535 ports on every address, a full UDP scan, or a complete application vulnerability audit. Unknown subnets, every VLAN ID, alternate-address assignment, inbound access from a separate machine, and reboot persistence were not tested. Nmap `-Pn` labels hosts up by assumption; the 767 reported addresses are not 767 discovered live machines. Filtered ports and timeouts are absence of a response, not proof of isolation. Some application probes used 5–6 second client deadlines. Internet access from the container used a host-resolved address and does not validate container DNS configuration.
