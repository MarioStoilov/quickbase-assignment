# Ticket Agent frontend

The browser client of the ticket agent: a login screen that picks a tenant, one chat
per tenant conversation, a trace box for every tool call the model makes, and a
blocking dialog for every tool call that needs the person's answer. It is its own
service, separate from the backend in the parent directory: it has its own server and
port, and the only thing the two share is the HTTP API described in the
[root README](../README.md).

## Requirements

- Node.js 20 or newer and npm.
- The backend running (`make run` in the repository root), or nothing works past the
  login screen.

## Commands

From the repository root, through the Makefile:

```bash
make install        # also installs this package's locked dependencies (npm ci)
make frontend       # build the bundle and serve it on the frontend port
make frontend-dev   # serve from source with hot reload
make frontend-build # build the bundle into frontend/dist without serving it
make lint           # includes this package: eslint, prettier --check, tsc
make format         # includes this package: prettier --write, eslint --fix
```

Or from this directory with npm: `npm run dev`, `npm run build`, `npm run serve`,
`npm run lint`, `npm run format`, `npm run typecheck`.

## Configuration

The frontend reads three variables, from the process environment or the repository's
`.env` file (the same file the backend reads):

| Variable                     | Default     | Purpose                                                          |
| ---------------------------- | ----------- | ---------------------------------------------------------------- |
| `TICKET_AGENT_FRONTEND_PORT` | `5173`      | Port this service listens on, in dev and when serving the bundle |
| `TICKET_AGENT_HOST`          | `127.0.0.1` | Where the backend listens; the same variable the backend uses    |
| `TICKET_AGENT_PORT`          | `8000`      | Port of the backend; the same variable the backend uses          |

The browser talks only to the frontend service. Requests under `/api` are forwarded to
the backend by the frontend's own server, in development and when serving the built
bundle alike (`vite.config.ts`). The backend therefore needs no knowledge of the
frontend, no CORS configuration and no static file mount, and a second frontend can be
run against it the same way.

## How it talks to the backend

Everything the frontend knows about the API is in `src/api/` and `src/constants/`.

- `GET /api/tenants` fills the login screen. Picking a tenant stores its id in
  `sessionStorage`; from then on every request carries it in the `X-Tenant-ID` header.
- `GET /api/chat` fills the list shown after login: the tenant's conversations,
  newest first, each with its start time, a preview of the first message and a mark
  when it waits for an answer to a tool call. Clicking one opens it; "New
  conversation" at the top creates one through `POST /api/chat/new` and opens it.
- The open conversation's id is stored in `sessionStorage`, so a reload reopens the
  same chat and a new tab starts at the login screen. "Conversations" in the chat
  header forgets the id and returns to the list; "Log out" forgets both.
- `GET /api/chat/{id}` is read whenever a conversation is opened. Its stored messages
  are turned into the AI SDK message shape (`storedMessages.ts`), and when the
  conversation is frozen the pending call gets the same response-required part the
  stream would have carried, so the dialog reopens. A 404 (unknown or foreign id)
  drops the stored id and returns to the list.
- `POST /api/chat/{id}` and `POST /api/chat/{id}/tool-calls/{call_id}/response` are
  the two streaming routes. One transport (`ConversationTransport.ts`) serves both: a
  new message posts only that message; an answer to a pending call posts only the
  chosen option. The history is never sent, the backend holds it.

## Generic tool handling

The frontend registers no tool. Whatever the backend's registry holds is traced and
gated from the stream alone:

- The trace box (`src/tools/ToolTrace.tsx`) is assistant-ui's fallback component for
  every tool. It is collapsed by default: the summary line shows the tool name and
  the call's state (running, waiting for your answer, done, failed), and a click
  reveals the arguments from the `tool-input-available` part and the result from
  `tool-output-available`. A result carrying the backend's `error` key is shown in
  red and the state reads "Failed".
- The dialog (`src/tools/ToolResponseModal.tsx`) is driven by the backend's custom
  `data-tool-response-required` part, which names the call, the tool and the options.
  It renders one button per option, so a tool offering options other than approve and
  reject gets the right buttons without a change here. While it is open the composer
  is disabled; the backend would refuse a message anyway with a 409.
- Which call is pending is derived from the messages alone
  (`src/tools/pendingToolResponse.ts`): the newest assistant message has a
  response-required part whose call has no result yet. When the backend streams the
  result, the tool part gains an output and the dialog closes. No separate state.

Adding a tool to the backend therefore needs no frontend change.

## Module layout

```
src/
├── main.tsx                 mounts the application
├── App.tsx                  login, conversation list or chat, from the session
├── styles.css               all styling, hand-written, no CSS framework
├── api/
│   ├── client.ts            fetch calls answered with one JSON body: tenants, list, create, read
│   └── types.ts             the backend's response shapes
├── constants/
│   ├── api.ts               paths, the tenant header, statuses, sessionStorage keys
│   ├── stream.ts            part types and states read from the stream
│   └── ui.ts                every text the person sees that the model did not write
├── session/
│   └── useSession.ts        tenant id and conversation id in sessionStorage
├── layout/
│   └── ScreenHeader.tsx     title, tenant, the screen's buttons and "Log out"
├── login/
│   └── TenantLogin.tsx      one button per tenant
├── conversation/
│   ├── ConversationList.tsx the tenant's conversations and "New conversation"
│   ├── ConversationScreen.tsx  header with the way back, read of the conversation, then the chat
│   ├── Conversation.tsx     the chat: messages, composer, dialog; wraps assistant-ui's
│   │                        thread-named primitives once
│   ├── ConversationTransport.ts  the AI SDK transport: routes each request to one of
│   │                        the two streaming endpoints
│   ├── useConversationRuntime.ts  AI SDK chat with that transport, handed to assistant-ui
│   ├── storedMessages.ts    stored rows from GET /api/chat/{id} to AI SDK messages
│   ├── AssistantMessage.tsx markdown text, trace boxes, error line
│   └── UserMessage.tsx      plain text bubble
└── tools/
    ├── ToolTrace.tsx        generic trace box, the fallback for every tool
    ├── ToolResponseModal.tsx  generic dialog, one button per offered option
    └── pendingToolResponse.ts  finds the pending call in the messages
```

Libraries: React, the Vercel AI SDK (`ai`, `@ai-sdk/react`) for the stream protocol and
chat state, assistant-ui primitives (`@assistant-ui/react`, its AI SDK bridge and its
markdown renderer) for the chat surface. The primitives are unstyled; every style is in
`styles.css`. The vendor SDK is touched in two modules only: the transport and the
runtime hook.

## One protocol detail worth knowing

The AI SDK continues the newest assistant message, instead of appending a new one,
only while the incoming stream's `start` part keeps that message's id. The backend
generates a fresh id per stream. The transport therefore drops the id from the `start`
part on the tool response route, so the continuation (the tool's result and the
model's report) lands in the message that asked, as one block in the chat, both live
and after a reload.
