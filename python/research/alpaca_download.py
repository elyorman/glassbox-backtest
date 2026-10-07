"""Cache public market-data responses for private exploratory research.

Never submits orders or calls account-detail endpoints. Credentials stay in memory.
Raw bodies and non-secret request provenance are retained in ignored storage.
This collector does not assert data completeness or usage rights.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SYMBOLS = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "SPY")


def credentials(env_file):
    values = {}
    for line in env_file.read_text().splitlines():
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
            values[key] = value.strip().strip("\"'")
    values.update({k: os.environ[k] for k in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY") if k in os.environ})
    if not all(values.get(k) for k in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY")):
        raise ValueError("Missing Alpaca market-data credentials")
    return {"APCA-API-KEY-ID": values["APCA_API_KEY_ID"],
            "APCA-API-SECRET-KEY": values["APCA_API_SECRET_KEY"]}


def download(headers, output, name, endpoint, params):
    page, token, seen = 0, None, set()
    while True:
        query = dict(params)
        if token:
            query["page_token"] = token
        url = endpoint + "?" + urlencode(query)
        for attempt in range(4):
            time.sleep(0.35)
            try:
                with urlopen(Request(url, headers=headers), timeout=45) as response:
                    body, status = response.read(), response.status
                break
            except HTTPError as exc:
                body, status = exc.read(), exc.code
                if status not in (429, 500, 502, 503, 504) or attempt == 3:
                    break
                time.sleep(2 ** attempt)
        raw = output / f"{name}.{page:04d}.json"
        with raw.open("xb") as handle:
            handle.write(body)
        metadata = {"endpoint": endpoint, "parameters": query, "status": status,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": hashlib.sha256(body).hexdigest(), "body_file": raw.name}
        with (output / f"{name}.{page:04d}.request.json").open("x") as handle:
            json.dump(metadata, handle, indent=2)
        payload = json.loads(body)
        if status != 200:
            print(json.dumps({"request": name, "status": status,
                              "message": payload.get("message", "Request failed")}))
            return
        print(json.dumps({"request": name, "page": page, "status": status,
                          "counts": {k: len(v) if isinstance(v, (dict, list)) else None
                                     for k, v in payload.items() if k != "next_page_token"}
                                    if isinstance(payload, dict) else {"records": len(payload)}}), flush=True)
        token = payload.get("next_page_token") if isinstance(payload, dict) else None
        if not token:
            return
        if token in seen:
            raise ValueError("Provider repeated a pagination token")
        seen.add(token)
        page += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--mode", choices=("probe", "bars", "issuer"), default="probe")
    parser.add_argument("--end", default="2026-10-02T20:00:00Z")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.mode == "issuer":
        url = "https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx"
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=45) as response:
            body = response.read()
        with (args.output / "issuer-distributions.xlsx").open("xb") as handle:
            handle.write(body)
        with (args.output / "issuer-distributions.request.json").open("x") as handle:
            json.dump({"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                       "sha256": hashlib.sha256(body).hexdigest()}, handle, indent=2)
        print(json.dumps({"request": "issuer-distributions", "bytes": len(body)}))
        return
    headers = credentials(args.env_file)
    if args.mode == "probe":
        download(headers, args.output, "calendar", "https://paper-api.alpaca.markets/v2/calendar",
                 {"start": "2015-01-01", "end": "2026-10-05"})
        download(headers, args.output, "actions", "https://data.alpaca.markets/v1/corporate-actions",
                 {"symbols": ",".join(SYMBOLS), "start": "2015-01-01", "end": "2026-12-31",
                  "limit": 1000, "data_quality": "all"})
    else:
        name = "bars_raw_" + args.end.replace(":", "").replace("-", "")
        download(headers, args.output, name, "https://data.alpaca.markets/v2/stocks/bars",
                 {"symbols": ",".join(SYMBOLS), "timeframe": "1Day", "start": "2015-01-01",
                  "end": args.end, "feed": "sip", "adjustment": "raw", "limit": 10000,
                  "sort": "asc"})


if __name__ == "__main__":
    main()
