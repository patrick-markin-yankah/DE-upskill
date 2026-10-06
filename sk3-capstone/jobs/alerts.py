"""Post a FinCore Slack message and keep a JSON copy under alerts/out.

Scaffold check: python alerts.py --test
Event posts write the JSON file even when Slack is not configured.
A failed Slack post is logged and does not replace the original task failure.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path("/opt/airflow/alerts/out")


def post_slack(text: str) -> None:
    from airflow.providers.slack.hooks.slack_webhook import SlackWebhookHook

    SlackWebhookHook(slack_webhook_conn_id="slack_webhook").send(text=text)


def write_copy(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"[alerts] wrote {path}")


def deliver(text: str, path: Path, payload: dict) -> None:
    body = {"text": text, "posted_at": datetime.now(timezone.utc).isoformat(), **payload}
    write_copy(path, body)
    try:
        post_slack(text)
        print("[alerts] posted to Slack")
    except Exception as exc:
        print(f"[alerts] Slack post failed: {exc}", file=sys.stderr)


def send_test() -> None:
    post_slack("FinCore Slack is connected")
    print("posted test message to Slack")


def message_for(event: str, args: argparse.Namespace) -> str:
    if event == "task_failed":
        return (
            "FinCore task failed. "
            f"task={args.task} date={args.ds} attempt={args.try_number} log={args.log_url}"
        )
    if event == "missing_source":
        return f"Missing source: {args.source} for {args.ds}. Run aborted."
    if event == "quality_gate":
        return (
            "Quality gate failed. "
            f"date={args.ds} reject_rate={args.reject_rate} limit={args.limit_rate} "
            f"unresolvable={args.unresolvable} limit={args.limit_unresolvable}. Load skipped."
        )
    if event == "dbt_advisory":
        return (
            "dbt tests failed (advisory). "
            f"date={args.ds} log={args.log_url} Data was not rolled back."
        )
    if event == "sla_page":
        return f"PAGE. Pipeline missed the 6-hour SLA. date={args.ds} log={args.log_url}"
    raise SystemExit(f"unknown event {event}")


def copy_path(event: str, args: argparse.Namespace) -> Path:
    if event == "sla_page":
        return OUT_DIR / f"page_{args.ds}.json"
    task = args.task or args.source or event
    return OUT_DIR / f"{args.ds}_{task}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="FinCore Slack alerts")
    parser.add_argument("--test", action="store_true", help="Post the scaffold check and nothing else")
    parser.add_argument(
        "--event",
        choices=["task_failed", "missing_source", "quality_gate", "dbt_advisory", "sla_page"],
    )
    parser.add_argument("--ds", default="")
    parser.add_argument("--task", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--try-number", type=int, default=0)
    parser.add_argument("--log-url", default="")
    parser.add_argument("--reject-rate", default="")
    parser.add_argument("--unresolvable", default="")
    parser.add_argument("--limit-rate", default="0.02")
    parser.add_argument("--limit-unresolvable", default="100")
    args = parser.parse_args()

    if args.test:
        try:
            send_test()
        except Exception as exc:
            print(
                "Slack test did not post. Set SLACK_WEBHOOK_URL in .env, then recreate "
                f"airflow-init so the slack_webhook connection exists. Detail: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        return

    if not args.event or not args.ds:
        raise SystemExit("usage: alerts.py --test | alerts.py --event EVENT --ds YYYY-MM-DD")

    text = message_for(args.event, args)
    deliver(
        text,
        copy_path(args.event, args),
        {
            "event": args.event,
            "ds": args.ds,
            "task": args.task,
            "source": args.source,
            "try_number": args.try_number,
            "log_url": args.log_url,
            "reject_rate": args.reject_rate,
            "unresolvable": args.unresolvable,
        },
    )


if __name__ == "__main__":
    main()
