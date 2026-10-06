"""Create the MinIO and Slack connections. Safe to re-run."""
import json
import os

from airflow.models import Connection
from airflow.settings import Session


def upsert(session: Session, conn: Connection) -> None:
    existing = session.query(Connection).filter(Connection.conn_id == conn.conn_id).one_or_none()
    if existing is not None:
        session.delete(existing)
        session.flush()
    session.add(conn)
    print(f"connection ready: {conn.conn_id}")


def main() -> None:
    session = Session()
    try:
        upsert(
            session,
            Connection(
                conn_id="minio_s3",
                conn_type="aws",
                extra=json.dumps(
                    {
                        "aws_access_key_id": os.environ["MINIO_ACCESS_KEY"],
                        "aws_secret_access_key": os.environ["MINIO_SECRET_KEY"],
                        "endpoint_url": os.environ["MINIO_ENDPOINT"],
                        "region_name": "us-east-1",
                    }
                ),
            ),
        )

        webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
        if not webhook:
            print("SLACK_WEBHOOK_URL is empty; slack_webhook connection was not created")
        else:
            prefix = "https://hooks.slack.com/services"
            marker = prefix + "/"
            if not webhook.startswith(marker):
                raise SystemExit(
                    "SLACK_WEBHOOK_URL must start with https://hooks.slack.com/services/"
                )
            upsert(
                session,
                Connection(
                    conn_id="slack_webhook",
                    conn_type="slackwebhook",
                    host=prefix,
                    password=webhook[len(marker):],
                ),
            )
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    main()
