# File states (designed before the UI)

Every file a clerk drops goes through these states. Each has one icon, one colour and one line for Marisol.

| State | Colour | Line Marisol reads | Leaves to |
|---|---|---|---|
| `queued` | grey | Waiting for a clean room. | `writing_step` |
| `writing_step` | blue | The model writes the extraction step for this kind of file (Vultr Serverless Inference, outside the room). | `sandbox_up` |
| `sandbox_up` | blue | A throwaway room is ready: no network, no secrets, 512 MB, 30 s. | `opening` |
| `opening` | blue | Opening the file inside the room. | `extracting`, `blocked`, `failed` |
| `extracting` | blue | Only text passed through the drawer. | `reading_fields` |
| `reading_fields` | blue | The model reads vendor, amount, due date and bank details from the text, as data. | `extracted`, `blocked` |
| `retry` | amber | The step failed in the room; the model rewrites it with the error (max 2). | `sandbox_up`, `failed` |
| `extracted` | green | Fields ready. Check the flags, then send it to the pay list. | `destroyed` |
| `blocked` | red | The file tried something (network, secrets, a fork bomb). It hit the wall; fields are still here. | `destroyed` |
| `failed` | red | Couldn't read this file (damaged or empty). Ask the vendor for a new copy. | `destroyed` |
| `destroyed` | grey | The room is gone. Receipt kept. | — (terminal) |

Rules:
- `destroyed` always follows, whatever happened, and carries a timestamp. A file never stays "open".
- `blocked` is not a failure: the clerk still gets the fields when they could be read safely.
- Flags (bank details changed, sender domain differs) are shown on `extracted` and `blocked` cards and stop
  "Send to pay list" until the controller approves.
