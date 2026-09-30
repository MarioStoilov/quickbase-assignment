# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## Never reason from "this machine"

Any reviewer must be able to clone the repository and run it with a single command.
Therefore:

- No API key, home directory, absolute path, port that only works here, or host name is
  hard-coded in code, tests, docs or scripts. Secrets come from environment variables and
  the README names each one, what it is for and where to get it.
- The LLM provider is behind one thin adapter. The rest of the code (tools, authorization,
  approval flow, streaming) does not import the vendor SDK. Swapping providers is a change
  to that adapter only.
- Seed data is fictional. Tenant names, ticket titles, e-mail addresses and phone numbers
  in tickets and tests use obviously invented values; the injection payloads are the
  ones the brief describes or close variants, written so that a reader recognises the
  attack at a glance.
- `README.md` is the single source for setup, the run command, the architecture. If a setup step, 
  an environment variable or a design decision is discovered, add it there in the same change.

## Git: never commit or push unless explicitly told to

- Make changes in the working tree and stop. Commit only when the user says "commit";
  push only when the user says "push". A confirmed decision or a finished step is not an
  instruction to commit.
- Commit messages carry no `Co-Authored-By` or other trailer lines. Subject + body only.
- Structure, exactly:

  ```
  add|fix|remove: <brief description, 10-20 words at most>

  <one paragraph, 100-150 words at most, describing the change>
  ```

- Subject: one of the three prefixes, then a lowercase imperative description with no
  trailing period (`add: constants package holding every module-level constant`,
  `fix: reject a foreign ticket before an approval is created`).
- Body: a single paragraph, wrapped at about 72 columns, saying what changed and why
  and naming a decision only when it is not obvious from the diff. A sentence on how it
  was verified may close the paragraph. No lists, no further paragraphs.
- Never rewrite history that has been pushed.

## No placeholder code

Every function, class, module, dependency, test or config entry in the tree is used and
fully implemented at the time it is added. No stubs, no "not implemented yet", no `TODO`
scaffolding, no commands that exit with a message about a later step, no
declared-but-unused dependencies. Add a thing in the same change that makes it work.

## Exceptions to any rule in this file

An exception is made only after asking the user and receiving explicit approval for that
specific case. Never assume an earlier exception extends to a new case.

## References
Start with reading the `README.md` in the project root folder in order to load the project architecture and any relevant
commands or information that would be useful to understand the code.

## Coding standards

Enforced in review. They apply to every language in the tree, to inline helper scripts
and to tests alike. When a file is touched, the whole file is brought up to these
standards in the same change.

### 1. Names

- **Descriptive identifiers only.** Never `v`, `arr`, `m1`, `m2`, `acc`, `tmp`, `res`,
  `ctx`, `cfg`, `s`, `t`, `e`, `req`, `res` or any other abbreviation. Loop variables
  included: `for ticket in tickets`, not `for t in ts`. Callback parameters included.
- A name says what the value *is* for the reader (`caller_tenant_id`,
  `tickets_by_id`, `pending_approval`), not its type or position.
- An accumulator is named after what it becomes for the caller (`tickets_to_show`), not
  after its shape (`result`, `out`, `items`).
- A constant is named after its meaning and role (`TENANT_HEADER_NAME`,
  `APPROVAL_TIMEOUT_MS`), never after its value or a placeholder.
- The only accepted single-letter names: a mathematical index inside a formula, and `_`
  for a value that is intentionally unused.

### 2. Statements

- **One value per line.** Anything that has to be computed before it is used gets its
  own named variable first: a slice bound, a count, a flag used in a condition
  (`is_same_tenant = …`, then `if is_same_tenant`), a string that goes into a message.
- **No long one-line call chains.** A chain of calls, a comprehension or arrow function
  inside a call, or a nested expression is broken into named intermediate steps on
  separate lines. Prefer an explicit loop over a chain that needs more than one step.
- No arithmetic or calls inside subscripts, conditions or template strings beyond a
  plain name or attribute.

### 3. Layout inside a function

- **Blank lines separate logical steps:** setup, blank line, the loop or main
  computation, blank line, the return or throw. Inside a loop body, "prepare this
  iteration's inputs" is separated from "do the work". A `return` is never glued to the
  last line of a loop.
- **A long function made of semi-independent pieces gets a comment above each piece**
  stating what the piece does and why it sits there (ordering constraints, what it
  protects against). The comment opens the block, the blank line closes it. This is
  preferred over splitting into helpers when the pieces share state and only ever run
  in this sequence. Authorization checks in particular carry such a comment: what is
  checked, what happens when it fails, and why it sits before everything else.

### 4. Documentation in code

- **Every function and method has a docstring** in the language's conventional form
  (Google-style for Python, JSDoc for TypeScript). First line: one sentence saying what
  it does. Then, when applicable: a short paragraph of behaviour a caller must know
  (ordering guarantees, empty-input behaviour, what is destructive, what is checked
  before it runs), the parameters, the return value, and each error that can be raised
  and when. Docstrings describe inputs, outputs and guarantees, not the implementation.
- **Every setting has a comment directly above it** saying what it controls, its unit
  where one applies, what changing it does, and what an empty value or the default
  means. **Every module-level constant** gets the same.
- Classes and components have a docstring stating what one instance represents or
  manages.
- The system prompt is a named constant in one module with a comment saying what each
  paragraph of it is for. It is not a security boundary and the comment says so.

### 5. Types, tooling, configuration

- Type annotations on every function signature; in TypeScript, `strict` is on and `any`
  is not used.
- The formatter and linter must be clean; their settings live in the root config file of
  the chosen stack.
- Configuration values come from one settings module only. A new setting is added in the
  same change as the code that reads it, with its comment.
- **Every module-level constant lives in the `constants` package** (`src/ticket_agent/
  constants/`), grouped by topic with one module each (`auth.py`, `tickets.py`, ...),
  each constant with its comment. Code modules import from there and define no
  constants of their own: no limits, header names, allowed values, messages, exit codes
  or command hints inline. Not constants: routers, type aliases, the version string,
  and data tables such as the seed rows, which stay with the module that owns them.
- No placeholder code, no unused dependencies (see "No placeholder code" above).

### Reference shape

```python
def mutate_ticket(ticket_id: str, action: str, caller_tenant_id: str) -> Ticket:
    """Apply `action` to the ticket with `ticket_id` on behalf of `caller_tenant_id`.

    The tenant check runs before the action is looked at, so a ticket from another
    tenant is rejected identically for update and delete and no information about the
    ticket leaks in the error. Callers are expected to have obtained approval already;
    this function does not ask.

    Args:
        ticket_id: identifier as returned by `search_tickets`.
        action: `"update"` or `"delete"`.
        caller_tenant_id: tenant taken from the request, never from model output.

    Returns:
        The ticket after the change; for a delete, the ticket as it was.

    Raises:
        TicketNotFound: no ticket with `ticket_id` exists in the caller's tenant.
        UnknownAction: `action` is neither update nor delete.
    """
    ticket = self._tickets_by_id.get(ticket_id)
    is_known_ticket = ticket is not None
    is_same_tenant = is_known_ticket and ticket.tenant_id == caller_tenant_id

    # A foreign ticket and a missing ticket produce the same error so that the model
    # cannot probe for the existence of other tenants' tickets.
    if not is_same_tenant:
        raise TicketNotFound(ticket_id)

    ...
```

## Conventions

- Verify each change by running the app end to end (start it with the single run
  command, send a message, watch the tool trace and the approval modal) and state the
  observed outcome. A change to authorization or approval is additionally verified with
  the adversarial cases below.
- Every change comes with its tests, in the layer that fits: a pure function gets a unit
  test; a tool gets a test that calls it directly with a foreign tenant; the endpoint
  gets a test that drives it with a fake model whose tool calls are scripted, so that
  the security rules are checked without a live LLM. The test suite is green before a
  change is reported done, and it runs without network access or an API key.
- The adversarial cases: One well-reasoned case per category, each named after the attack it checks
  (`test_injected_delete_all_is_not_executed_without_approval`,
  `test_search_never_returns_other_tenant_tickets`), each with a docstring saying what
  the attacker controls, what they try, and which rule stops them.
- Dependency versions are pinned in the lock file. Bumps are deliberate changes with
  their own commit.
