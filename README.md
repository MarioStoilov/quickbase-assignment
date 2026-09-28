## Commands

The stack has not been chosen yet. Once it is, this section lists, in this order: the
one-line install, the formatter and linter, the test runner, the single command that runs
the whole thing, and any debugging helper worth knowing. Each line carries a trailing
comment saying what it does. The README's setup section says the same in prose.

## Architecture

Filled in as the code is written, in the same change that introduces each part. It
describes: the request path from the chat UI through the streaming endpoint to the model
and back; where the tenant is read from the request (the fake `X-Tenant-ID` header) and
how it reaches each tool; how a tool call that needs approval is paused, surfaced in the
UI and resumed or rejected; the module layout with one line per module saying what it
owns; and the test layout. A reader of this section should be able to answer "where would
a cross-tenant leak have to happen, and why can't it?" without opening the code.