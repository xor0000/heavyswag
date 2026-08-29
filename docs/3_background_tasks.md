---
icon: lucide/workflow
---

# Background tasks

HeavySwag has no `BackgroundTasks`-style primitive built in — on purpose.
An in-memory task lives only inside one process: it vanishes the moment
that process restarts, deploys, or crashes mid-task, with no record it was
ever supposed to run and nothing to retry it. For anything that has to
*actually* happen — a payment, a refund, a notification a user is waiting
on — that's not good enough. The task's existence and progress need to
live somewhere durable, outside any single process, so it can be tracked
and picked back up no matter what happens to the process that started it.

The pattern below offloads the work to a durable workflow engine
([Temporal](https://temporal.io/)) instead: the HTTP handler starts a
workflow and replies immediately; a separate worker process executes it,
retries it on failure, and survives a restart of either side without losing
track of where it was. The same engine covers two related but distinct
needs — [work triggered by a request](#async-tasks) and
[work triggered by a clock](#cron) — covered separately below.

```shell
uv add temporalio
```

___

## Async tasks

### The pieces

Three independent processes, each with one job:

- **the HeavySwag app** — accepts the HTTP request, starts a workflow,
  replies `202 Accepted` with a workflow/run id. Never waits for the work
  itself to finish.
- **the Temporal server** — durably records what workflows exist, what
  state each one is in, and hands work to whichever worker is available.
  Runs as its own service (see [Running it](#running-it) below).
- **the worker** — an independent process, in any language, that runs the
  task code you've registered with it. Scale it independently of the HTTP
  app; run one, or ten of them.

### Defining the work

An **activity** is a single side effect — an API call, a DB write, and so
on. A **workflow** orchestrates a sequence of activities and owns their
retry/failure policy.

```python title="app/tasks.py"
import uuid
from datetime import timedelta
from logging import getLogger

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

TASK_QUEUE = "ton-refund-task-queue"

log = getLogger(__name__)


@activity.defn
async def send_ton(account: str, amount: float) -> str:
    """Sends TON to the user's wallet. Returns the transaction hash."""
    log.info("Sending %.4f TON to account=%s", amount, account)
    tx_hash = f"tx_{uuid.uuid4().hex[:16]}"
    return tx_hash


@activity.defn
async def send_message_to_telegram(chat_id: str, text: str) -> None:
    """Sends a message to the user via Telegram."""
    log.info("Sending Telegram message to chat_id=%s: %r", chat_id, text)


@workflow.defn
class RefundTonWorkflow:
    _RETRY_POLICY = RetryPolicy(
        initial_interval=timedelta(seconds=2),
        backoff_coefficient=2.0,
        maximum_attempts=3,
    )

    @workflow.run
    async def run(self, tg_chat_id: str, account: str, amount: float) -> str:
        try:
            tx_hash = await workflow.execute_activity(
                send_ton,
                args=[account, amount],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=self._RETRY_POLICY,
            )
        except Exception:  # (1)!
            await workflow.execute_activity(
                send_message_to_telegram,
                args=[
                    tg_chat_id,
                    f"❌ Failed to refund {amount} TON to address {account}. "
                    "We're already looking into it and will retry.",
                ],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=self._RETRY_POLICY,
            )
            raise

        await workflow.execute_activity(
            send_message_to_telegram,
            args=[tg_chat_id, f"✅ Refund of {amount} TON completed. Tx: {tx_hash}"],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=self._RETRY_POLICY,
        )
        return tx_hash
```

1.  This is what `RetryPolicy` above already exhausted — `send_ton` has
    been retried `maximum_attempts` times and still failed. Notify the user
    and re-`raise` so the workflow itself shows up as failed in Temporal's
    UI, instead of silently swallowing it.

`RetryPolicy` and `start_to_close_timeout` give every attempt a bounded
number of tries, backoff between them, and a hard per-attempt deadline —
all durably tracked by Temporal, not held in process memory that a crash
would wipe out.

### The connection

Starting a workflow needs a `Client`, and opening one per request would be
wasteful — connect once, reuse it:

```python title="app/starter.py"
from temporalio.client import Client as TemporalClient


class _ClientHolder:
    client: TemporalClient | None = None


_holder = _ClientHolder()


async def get_temporal_client() -> TemporalClient:
    if _holder.client is None:
        _holder.client = await TemporalClient.connect("localhost:7233")

    return _holder.client
```

!!! tip "In a real app, close the client and inject it properly"
    This lazy-holder is fine for a quick example, but it never closes its
    connection and it's a module-level singleton. In a more serious setup,
    take care of both: close the client on shutdown (see
    [Lifespan](index.md#lifespan)) and wire it in through dependency
    injection instead.

### The endpoint

```python title="app/router.py"
import logging
from typing import NamedTuple

from heavyswag import HeavyRouter, HeavySwag, run_app
from heavyswag.specify import Body, Request, Response
from temporalio.exceptions import WorkflowAlreadyStartedError

from app.starter import get_temporal_client
from app.tasks import TASK_QUEUE, RefundTonWorkflow

log = logging.getLogger(__name__)

router = HeavyRouter("/")


class RefundDTO(NamedTuple):
    account: str
    tg_chat_id: Body[str]
    amount: Body[float]


class RefundAccepted(NamedTuple):
    workflow_id: str
    run_id: str


@router.post("/refund/{account}")
async def refund_ton(_: Request, dto: RefundDTO) -> Response[RefundAccepted]:
    client = await get_temporal_client()

    # workflow_id = account makes the endpoint idempotent
    workflow_id = f"refund-ton-{dto.account}" # (1)!

    try:
        handle = await client.start_workflow(
            RefundTonWorkflow.run,
            args=[dto.tg_chat_id, dto.account, dto.amount],
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError:
        log.warning("Refund already in progress: workflow_id=%s", workflow_id)
        return Response(status_code=409)

    return Response(
        status_code=202,
        body=RefundAccepted(workflow_id=handle.id, run_id=handle.result_run_id or ""),
    )


app = HeavySwag(router)
asgi_app = run_app(app)
```

1.  While a refund for this account is already running, Temporal rejects a
    second `start_workflow` with the same id — the repeat request gets a
    `409 Conflict` instead of triggering a second transfer. Pick whatever
    makes a *retry of this specific request* meaningless to run twice; an
    account number, an order id, an idempotency key from a header — not a
    random uuid, which would defeat the point.

The handler never awaits the refund itself — `start_workflow` returns as
soon as Temporal has durably recorded that the workflow exists, typically
in milliseconds, regardless of how long `RefundTonWorkflow` actually takes
to run.

### The worker

A separate, standalone process — not part of the HeavySwag app, doesn't
import `heavyswag` at all:

```python title="app/worker.py"
import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from app.tasks import TASK_QUEUE, RefundTonWorkflow, send_message_to_telegram, send_ton


async def main() -> None:
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[RefundTonWorkflow],
        activities=[send_ton, send_message_to_telegram],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
```

### Running it

Temporal itself needs somewhere to run — locally, that's a `docker-compose`
stack (Temporal server + its Postgres store + the web UI):

```yaml title="docker-compose.yaml"
services:
  postgresql:
    image: postgres:14
    environment:
      POSTGRES_USER: temporal
      POSTGRES_PASSWORD: temporal
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U temporal"]

  temporal:
    image: temporalio/auto-setup:1.29.4
    depends_on:
      postgresql:
        condition: service_healthy
    environment:
      - DB=postgres12
      - DB_PORT=5432
      - POSTGRES_USER=temporal
      - POSTGRES_PWD=temporal
      - POSTGRES_SEEDS=postgresql
    ports:
      - "7233:7233"

  temporal-ui:
    image: temporalio/ui:2.51.0
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
    ports:
      - "8233:8080"
```

```shell
docker compose up -d          # Temporal server + UI on :8233

uv run python -m app.worker & # the worker, in the background

uv run uvicorn app.router:asgi_app --reload
```

```shell
curl -X POST http://127.0.0.1:8000/refund/EQabc...xyz \
  -H "Content-Type: application/json" \
  -d '{"tg_chat_id": "123456", "amount": 4.2}'
# -> 202 {"workflow_id": "refund-ton-EQabc...xyz", "run_id": "..."}
```

Watch it run (retries, failures, everything) at `http://localhost:8233`.

## Cron

Async tasks above are all triggered by an HTTP request. Some work isn't —
a nightly reconciliation pass, a "retry anything still stuck" sweep, a
digest sent every morning. That's a **cron job**: a workflow Temporal
starts on a schedule, on its own, without anything calling `/refund/...`
to kick it off.

Doing this yourself means standing up a separate scheduler (`cron(8)`, a
Kubernetes `CronJob`, Celery beat, ...) that has to know how to reach your
app, plus your own logic for "don't start a second run if the last one is
still going," plus your own alerting for "the scheduler died and nobody
noticed." Temporal folds all of that into the same engine already running
your async tasks — one thing to operate, not two.

### Defining the work

Same shape as an async task — an activity plus a workflow that calls it —
added to the same `app/tasks.py`:

```python title="app/tasks.py (add)"
@activity.defn
async def find_and_retry_stuck_refunds() -> None:
    """Scans for refunds that never completed and retries them."""
    ...


@workflow.defn
class NightlyReconciliationWorkflow:
    @workflow.run
    async def run(self) -> None:
        await workflow.execute_activity(
            find_and_retry_stuck_refunds,
            start_to_close_timeout=timedelta(minutes=5),
        )
```

### Registering it with the worker

A cron workflow runs on the exact same worker as everything else — add it
to the same lists:

```python title="app/worker.py"
from app.tasks import (
    TASK_QUEUE,
    NightlyReconciliationWorkflow,
    RefundTonWorkflow,
    find_and_retry_stuck_refunds,
    send_message_to_telegram,
    send_ton,
)

worker = Worker(
    client,
    task_queue=TASK_QUEUE,
    workflows=[RefundTonWorkflow, NightlyReconciliationWorkflow],
    activities=[send_ton, send_message_to_telegram, find_and_retry_stuck_refunds],
)
```

### Scheduling it

```python
from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec

await client.create_schedule(
    "nightly-refund-reconciliation",
    Schedule(
        action=ScheduleActionStartWorkflow(
            NightlyReconciliationWorkflow.run,
            id="nightly-refund-reconciliation-run",
            task_queue=TASK_QUEUE,
        ),
        spec=ScheduleSpec(cron_expressions=["0 3 * * *"]),  # (1)!
    ),
)
```

1.  Every day at 03:00 UTC — standard 5-field cron syntax. Prefer a fixed
    cadence over a cron string? `ScheduleSpec(intervals=[
    ScheduleIntervalSpec(every=timedelta(hours=6))])` works the same way.

The guarantee that matters: the next run only starts once the previous one
has completed, failed, or hit its timeout — a slow run can never overlap
with itself — and the workflow's own `RetryPolicy` (same idea as
`RefundTonWorkflow` earlier) applies to every scheduled run, not just the
first one.

## Why Temporal

Temporal is the durable-execution engine HeavySwag's docs reach for
whenever "start it now, guarantee it finishes" is the requirement — the
recommended part of the HeavySwag ecosystem for anything background,
scheduled, or long-running, exactly like the refund workflow and the cron
job above. It isn't the only workflow engine out there, but it's the one
the community has converged on for this job: the broadest production
adoption, the most mature multi-language SDK story, and tooling (the Web
UI at `:8233` you've been watching this whole guide) built for actually
debugging a stuck run at 3 AM, not just kicking one off.

**Learn more:** [Temporal documentation](https://docs.temporal.io/)
