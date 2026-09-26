# Local Agent — sanitized architecture overview

This diagram is deliberately suitable for a portfolio draft. It omits local
paths, project media, credentials, paired identities, radio settings, and model
weight locations. It distinguishes verified interfaces from experimental work.

## System boundary

```mermaid
flowchart LR
    Operator[Operator] --> Desktop[Desktop browser UI]
    Phone[Phone / Sideband] -. paired LXMF, experimental transport .-> Bridge[LXMF bridge]

    subgraph Workstation[Local workstation]
        Desktop --> HTTP[HTTP server\nlocalhost only]
        Bridge --> Agent[Transport-agnostic agent loop]
        HTTP --> Agent
        Agent --> Memory[Persistent memory + approved retrieval]
        Agent --> Tools[Schema-validated tool whitelist]
        Tools --> Files[Local files / URL fetch on request]
        Tools --> Media[Lazy media analysis queue]
        Tools --> Comfy[Guarded ComfyUI controls]
        Agent --> Route[GPU / CPU router]
        Route --> GPU[GPU reasoning model\nwhen resource is free]
        Route --> CPU[CPU reasoning model\nwhen render owns GPU]
        Media --> VLM[Exact lazy VLM\nloads only for media]
    end

    Comfy --> Render[ComfyUI render backend]
```

## GPU ownership and model lifecycle

```mermaid
flowchart TD
    Request[New chat or media request] --> Check{Render owner, backend,\nor foreign GPU use?}
    Check -- yes --> CPU[Route chat to CPU tier]
    Check -- yes --> Queue[Keep media job queued]
    Check -- no --> Chat{General chat?}
    Chat -- yes --> GPUChat[Use full GPU reasoning model]
    Chat -- no --> Media[Start exact lazy VLM]
    GPUChat --> RenderStarts{Render claims GPU?}
    Media --> RenderStarts
    RenderStarts -- yes --> Evict[Release agent model/VLM safely]
    Evict --> Queue
    RenderStarts -- no --> Finish[Finish request]
    Finish --> Release[Release background media model]
```

## Remote permission decision

```mermaid
flowchart TD
    Inbound[Inbound LXMF message] --> Paired{Paired identity?}
    Paired -- no --> Refuse[Refuse and log]
    Paired -- yes --> Answer[Run transport-agnostic agent loop]
    Answer --> Tool{Tool requested?}
    Tool -- no --> Reply[Chunked LXMF reply]
    Tool -- yes --> Permit{Allowed for this identity\nand whitelist validation passes?}
    Permit -- no --> Deny[Deny and audit log]
    Permit -- yes --> Execute[Run allowed tool]
    Execute --> Reply
```

## Portfolio claim labels

- **Verified local components:** localhost GUI, structured tool calling, tool
  validation, model routing, private-safe H3 evaluation, and a paired Sideband
  Tier A round trip.
- **Experimental:** LoRa/RNode mesh delivery and its reliability/latency
  measurements.
- **In progress:** custom Sideband Android packaging and direct phone media
  integrations.
