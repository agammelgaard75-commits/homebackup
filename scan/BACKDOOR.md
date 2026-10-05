# Internal access through Ollama

**Confirmed on 2026-10-05: Ollama allowed this isolated server to reach `192.168.1.43:8080` indirectly.** No persistent backdoor was installed.

## How it worked

Direct connections from `192.168.2.100` to `192.168.1.43:8080` timed out. However, this server could access the unauthenticated Ollama API at `192.168.3.189:11434`.

Ollama's `/api/pull` endpoint accepts a model name containing a registry address. I supplied a unique nonexistent model on `192.168.1.43:8080`, with `insecure: true` to permit HTTP:

```http
POST http://192.168.3.189:11434/api/pull
Content-Type: application/json

{"model":"192.168.1.43:8080/audit/isolation-audit-confirm-20261005:latest","insecure":true,"stream":false}
```

Ollama then initiated the request **from `192.168.3.189`**, using that machine's network access:

```text
192.168.2.100
  → 192.168.3.189:11434  POST /api/pull
  → 192.168.1.43:8080   GET /v2/audit/isolation-audit-confirm-20261005/manifests/latest
  → 192.168.1.43:8443   HTTPS redirect
```

The HTTP service on 8080 redirected Ollama to HTTPS on 8443. Ollama reached the TLS service, but rejected its untrusted certificate. The API returned HTTP 500 containing the destination URL and `x509: certificate signed by unknown authority`. That error demonstrates reachability; it does not mean the initial connection was blocked.

## Evidence and impact

- Direct TCP checks to 8080 and 8443 timed out after three seconds each.
- The repeated indirect request reached the HTTPS certificate check in **0.082 seconds**.
- A separate plaintext request through Ollama to 8443 returned the service's HTTP 400 body: `This combination of host and port requires TLS.`
- An earlier controlled callback independently confirmed requests originated from `192.168.3.189` and that Ollama relayed an error-response body.

This is **server-side request forgery (SSRF) across the isolation boundary**: the allowed Ollama service can act as an intermediary to destinations blocked from the isolated server. The registry-fetch feature supplies the capability; exposing it to this segment creates the bypass. No login, code execution, or host compromise was demonstrated. No valid model was downloaded; the 17 model names and digests remained unchanged.

Evidence: [direct/indirect confirmation](isolation-audit/retest-20261005T1411Z/pivot-confirmation.json), [callback proof](isolation-audit/retest-20261005T1411Z/ollama-fetch-probe.json), [inventory and cleanup verification](isolation-audit/retest-20261005T1411Z/cleanup-verification.json).

## Fix

Expose only required inference routes through an authenticated gateway; prevent this segment from calling `/api/pull` and other model-management routes. Also restrict the Ollama process's outbound access to protected internal services. Authentication alone does not stop this path if the same client credentials still permit model fetching. Retest the complete chain after applying those controls.
