# Sub2API Multimodal Frontend Design

## Goal

Update `/ui` from a single-purpose image generator into a compact multimodal invocation workspace. The first implemented mode remains image generation, but the interface should make room for image, video, and audio tasks and multiple stateless conversation windows.

## Approach

Use a client-only implementation in `frontend/index.html` and `frontend/app.js`. Keep the existing backend queue source available as "Local Gateway" and add a "Sub2API" source that calls a user-supplied OpenAI-compatible base URL and API token directly from the browser.

The default Sub2API endpoint shape is:

```text
POST {baseUrl}/v1/images/generations
Authorization: Bearer {apiToken}
Content-Type: application/json
```

The request body uses `{ prompt, model, n }`. Responses may contain either immediate OpenAI image data (`data[].b64_json` or `data[].url`) or this project's queued `{ request_id }` shape. Local gateway jobs keep the existing polling flow.

## UI Design

The first viewport becomes a workbench:

- Left sidebar: stateless conversation windows, add/rename/select/delete.
- Main panel: transcript-style output for the selected window.
- Right panel: source settings, modality tabs, prompt composer, model, count, and run controls.

Use a restrained operational interface: neutral dark background, compact panels, clear tabs, no marketing hero, and no nested cards. Video and audio tabs are present as disabled/planned modes so the layout communicates the future multimodal direction without pretending those calls exist.

## State

Persist windows, active window ID, Sub2API base URL, and selected source in `localStorage`. Persisting the API token is optional via a "remember token" checkbox; otherwise it stays in memory only. Do not hardcode tokens in source files.

## Errors

Show source-specific errors inline. Validate missing prompt, missing Sub2API URL, and missing token before network calls. If a response has an unexpected shape, surface a concise "unsupported response" message with HTTP status when available.

## Testing

Add Python static tests for required frontend affordances and security constraints: source selector, Sub2API URL/token inputs, multimodal tabs, multi-window controls, direct Sub2API endpoint composition, and absence of hardcoded secret tokens.
