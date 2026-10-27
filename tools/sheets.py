"""Discover schedule rows, preview changes and apply them through local OAuth."""

from __future__ import annotations

from datetime import date
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlparse, parse_qs, quote

from .worklog import write_json


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
FIELD_HEADERS = {"end_date": "actual end date", "human_hours": "human hours",
                 "agent_hours": "agent hours", "tokens": "tokens usage",
                 "status": "status", "commit": "final commit id"}


def normalize(value):
    return " ".join(str(value).lower().split())


def config(root):
    value = os.environ.get("METCHU_SCHEDULE_URL", "")
    path = Path(root) / ".env.harness"
    if not value and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, v = line.partition("=")
            if sep and key.strip() == "METCHU_SCHEDULE_URL":
                value = v.strip().strip("\"'")
    parsed = urlparse(value)
    match = re.fullmatch(r"/spreadsheets/d/([\w-]+)(?:/.*)?", parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "docs.google.com" or not match:
        raise ValueError("Set METCHU_SCHEDULE_URL to the Google Sheets URL in .env.harness.")
    params = {**parse_qs(parsed.query), **parse_qs(parsed.fragment)}
    gid = params.get("gid", [None])[0]
    if gid is not None and not gid.isdigit():
        raise ValueError("The URL's gid must be numeric.")
    return match.group(1), int(gid) if gid is not None else None


def column(number):
    result = ""
    while number:
        number, r = divmod(number - 1, 26)
        result = chr(65 + r) + result
    return result


def a1(title, cell):
    return "'" + title.replace("'", "''") + "'!" + cell


def find_row(snapshot, identifier):
    rows = snapshot["values"]
    header_matches = []
    for index, row in enumerate(rows[:10]):
        headers = [normalize(v) for v in row]
        if all(name in headers for name in ("iter", "id", *FIELD_HEADERS.values())):
            if len(set(filter(None, headers))) != len(list(filter(None, headers))):
                raise ValueError("Duplicate header labels; the schedule is ambiguous.")
            header_matches.append((index, headers))
    if len(header_matches) != 1:
        raise ValueError("Expected one schedule header with Iter, ID and the reporting columns.")
    header_index, headers = header_matches[0]
    iteration, item = identifier[1:].split("-")
    matches = []
    for index, row in enumerate(rows[header_index + 1:], header_index + 1):
        padded = row + [""] * max(0, len(headers) - len(row))
        iter_value = padded[headers.index("iter")]
        if isinstance(iter_value, (int, float)) and not isinstance(iter_value, bool) and int(iter_value) == iter_value:
            iter_value = str(int(iter_value))
        if str(iter_value) == iteration and str(padded[headers.index("id")]) == item:
            matches.append((index, padded[:len(headers)]))
    if len(matches) != 1:
        raise ValueError(f"Expected one explicit row for {identifier}, found {len(matches)}. No row inferred.")
    index, row = matches[0]
    return {"row_index": index, "headers": headers, "row": row,
            "assignees": {headers[i]: value for i, value in enumerate(row)
                          if value in ("Worker", "PM", "Participant")}}


def validate_cell(snapshot, col, value):
    rule = snapshot.get("validation_rules", {}).get(str(col))
    allowed = snapshot.get("allowed_values", {}).get(str(col))
    strict = rule.get("strict", False) if rule is not None else True
    condition = (rule or {}).get("condition", {})
    kind = condition.get("type")
    error = None
    if allowed is not None:
        if str(value) not in [str(v) for v in allowed]:
            error = f"Value {value!r} is not allowed by the dropdown."
    elif kind == "DATE_IS_VALID":
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 2958465:
            error = "Expected a valid Sheets date serial."
    elif kind and kind.startswith("NUMBER_"):
        comparators = {"NUMBER_GREATER": lambda a, b: a > b, "NUMBER_GREATER_THAN_EQ": lambda a, b: a >= b,
                       "NUMBER_LESS": lambda a, b: a < b, "NUMBER_LESS_THAN_EQ": lambda a, b: a <= b,
                       "NUMBER_EQ": lambda a, b: a == b, "NUMBER_NOT_EQ": lambda a, b: a != b}
        vals = condition.get("values", [])
        try:
            valid = kind in comparators and comparators[kind](float(value), float(vals[0]["userEnteredValue"]))
        except (ValueError, IndexError, KeyError, TypeError):
            valid = False
        if not valid:
            error = "Value does not satisfy the numeric validation rule."
    elif kind:
        error = f"Unsupported validation {kind}; inspect this field before writing."
    if error and strict:
        raise ValueError(f"Cell validation: {error}")
    return error


def target_fields(task):
    fields = dict(task["fields"])
    usage = task.get("usage")
    if usage and usage["usage_records"] and not usage["warnings"]:
        fields["tokens"] = usage["total_tokens"]
    return {key: fields[key] for key in FIELD_HEADERS if key in fields}


def make_plan(snapshot, task):
    found = find_row(snapshot, task["id"])
    fields = target_fields(task)
    usage = task.get("usage")
    changes, notices = [], []
    for key, header in FIELD_HEADERS.items():
        if key not in fields:
            continue
        col = found["headers"].index(header)
        before, after = found["row"][col], fields[key]
        if key == "end_date":
            after = (date.fromisoformat(after) - date(1899, 12, 30)).days
        if isinstance(before, str) and before.startswith("="):
            raise ValueError(f"Refusing to replace formula in {header}.")
        notice = validate_cell(snapshot, col, after)
        if notice:
            notices.append(f"{header}: {notice} (sheet uses a warning, not strict rejection)")
        number_format = {"type": "NUMBER", "pattern": "#,##0"} if key == "tokens" and not snapshot.get("number_formats", {}).get(str(col)) else None
        if before == after and number_format is None:
            continue
        cell = f"{column(col + 1)}{found['row_index'] + 1}"
        changes.append({"field": key, "cell": cell, "before": before, "after": after})
        if number_format:
            changes[-1]["number_format"] = number_format
    return {"task": task["id"], "contributor": task["owner"],
            "spreadsheet_id": snapshot["spreadsheet_id"], "sheet_id": snapshot["sheet_id"],
            "sheet_title": snapshot["sheet_title"], **found, "changes": changes,
            "task_fields": fields, "validation_rules": snapshot.get("validation_rules", {}),
            "allowed_values": snapshot.get("allowed_values", {}),
            "number_formats": snapshot.get("number_formats", {}),
            "validation_notices": notices,
            "usage_notice": ("Usage with warnings is not copied to the sheet; resolve attribution/coverage first."
                             if usage and usage["warnings"] else None)}


def check_plan(snapshot, plan):
    found = find_row(snapshot, plan["task"])
    if (snapshot["spreadsheet_id"] != plan["spreadsheet_id"] or
        snapshot["sheet_id"] != plan["sheet_id"] or found["headers"] != plan["headers"] or
        found["row_index"] != plan["row_index"]):
        raise ValueError("Schedule layout or row identity changed; run sheet again.")
    expected = list(plan["row"])
    for change in plan["changes"]:
        col = plan["headers"].index(FIELD_HEADERS[change["field"]])
        expected[col] = change["after"]
    formats_match = all(not c.get("number_format") or snapshot.get("number_formats", {}).get(
        str(found["headers"].index(FIELD_HEADERS[c["field"]]))) == c["number_format"] for c in plan["changes"])
    if found["row"] == expected and formats_match:
        return "already_applied"
    if found["row"] != plan["row"]:
        raise ValueError("The schedule row changed since preview; refresh the plan before writing.")
    if (snapshot.get("validation_rules", {}) != plan.get("validation_rules", {}) or
        snapshot.get("allowed_values", {}) != plan.get("allowed_values", {}) or
        snapshot.get("number_formats", {}) != plan.get("number_formats", {})):
        raise ValueError("Cell validation or number format changed; refresh the plan before writing.")
    return "ready"


def login(root, client_secrets):
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as error:
        raise ValueError("Install tools/requirements-sheets.txt in your local environment first.") from error
    flow = InstalledAppFlow.from_client_secrets_file(str(Path(client_secrets).expanduser()), SCOPES)
    credentials = flow.run_local_server(port=0, authorization_prompt_message="Authorize the local harness in your browser.")
    write_json(Path(root) / ".harness" / "google-token.json", json.loads(credentials.to_json()))
    return {"authenticated": True, "scope": SCOPES[0]}


class GoogleSheet:
    def __init__(self, root):
        self.spreadsheet_id, self.gid = config(root)
        token = Path(root) / ".harness" / "google-token.json"
        if not token.exists():
            raise ValueError("No local Google authorization. Run sheet --login <desktop-client.json>, "
                             "or use your agent's connected Sheets tools directly.")
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request, AuthorizedSession
        except ImportError as error:
            raise ValueError("Install tools/requirements-sheets.txt first.") from error
        credentials = Credentials.from_authorized_user_file(str(token), SCOPES)
        if not credentials.valid:
            try:
                credentials.refresh(Request())
            except Exception as error:
                raise ValueError("Google authorization expired or failed; run sheet --login <desktop-client.json> again.") from error
            write_json(token, json.loads(credentials.to_json()))
        self.http = AuthorizedSession(credentials)
        self.base = "https://sheets.googleapis.com/v4/spreadsheets/" + self.spreadsheet_id

    def request(self, method, suffix="", **kwargs):
        try:
            response = self.http.request(method, self.base + suffix, timeout=25, **kwargs)
        except Exception as error:
            raise ValueError("Google request failed. For writes, read back before retrying; outcome may be unknown.") from error
        if not response.ok:
            raise ValueError(f"Google Sheets returned HTTP {response.status_code}. Check account access and API setup.")
        return response.json()

    def values(self, range_):
        return self.request("GET", "/values/" + quote(range_, safe=""),
                            params={"valueRenderOption": "FORMULA", "dateTimeRenderOption": "SERIAL_NUMBER"}).get("values", [])

    def snapshot(self, identifier):
        metadata = self.request("GET", params={"fields": "spreadsheetId,sheets(properties)"})
        candidates = []
        for sheet in metadata["sheets"]:
            props = sheet["properties"]
            if props.get("sheetType") != "GRID" or (self.gid is not None and props["sheetId"] != self.gid):
                continue
            width = min(props["gridProperties"]["columnCount"], 50)
            header = self.values(a1(props["title"], f"A1:{column(width)}10"))
            if any({"iter", "id", "tokens usage"}.issubset({normalize(v) for v in r}) for r in header):
                candidates.append((props, width))
        if len(candidates) != 1:
            raise ValueError("Could not uniquely identify the schedule tab. Supply its gid in the URL.")
        props, width = candidates[0]
        if props["gridProperties"]["rowCount"] * width > 100000:
            raise ValueError("Schedule exceeds the bounded read size; narrow the sheet before using this tool.")
        values = self.values(a1(props["title"], f"A1:{column(width)}{props['gridProperties']['rowCount']}"))
        snapshot = {"spreadsheet_id": self.spreadsheet_id, "sheet_id": props["sheetId"],
                    "sheet_title": props["title"], "values": values, "allowed_values": {}, "validation_rules": {}, "number_formats": {}}
        found = find_row(snapshot, identifier)
        row_number = found["row_index"] + 1
        details = self.request("GET", params={"ranges": a1(props["title"], f"A{row_number}:{column(width)}{row_number}"),
            "includeGridData": "true", "fields": "sheets(data(startColumn,rowData(values(dataValidation,effectiveFormat(numberFormat)))))"})
        for sheet in details.get("sheets", []):
            for data in sheet.get("data", []):
                for row in data.get("rowData", []):
                    for index, cell in enumerate(row.get("values", []), data.get("startColumn", 0)):
                        number_format = cell.get("effectiveFormat", {}).get("numberFormat")
                        if number_format:
                            snapshot["number_formats"][str(index)] = number_format
                        if "dataValidation" not in cell:
                            continue
                        snapshot["validation_rules"][str(index)] = cell["dataValidation"]
                        condition = cell["dataValidation"].get("condition", {})
                        rule, vals = condition.get("type"), condition.get("values", [])
                        if rule == "ONE_OF_LIST":
                            snapshot["allowed_values"][str(index)] = [v["userEnteredValue"] for v in vals]
                        elif rule == "ONE_OF_RANGE":
                            source_range = vals[0]["userEnteredValue"].lstrip("=")
                            snapshot["allowed_values"][str(index)] = [v for row_ in self.values(source_range) for v in row_ if v != ""]
        return snapshot

    def apply(self, task, plan):
        if task["id"] != plan["task"] or target_fields(task) != plan["task_fields"]:
            raise ValueError("Task values changed after preview; run sheet again.")
        snapshot = self.snapshot(task["id"])
        fresh = make_plan(snapshot, task)
        state = check_plan(snapshot, plan)
        if state == "already_applied" and not fresh["changes"]:
            return {"result": "already_applied", "cells": 0}
        if fresh != plan:
            raise ValueError("Preview differs from the current task and sheet; refresh it before writing.")
        requests = []
        for change in fresh["changes"]:
            value = change["after"]
            cell = {"userEnteredValue": {"numberValue": value} if isinstance(value, (int, float)) else {"stringValue": value}}
            fields = "userEnteredValue"
            if change.get("number_format"):
                cell["userEnteredFormat"] = {"numberFormat": change["number_format"]}
                fields += ",userEnteredFormat.numberFormat"
            requests.append({"updateCells": {"start": {"sheetId": snapshot["sheet_id"],
                "rowIndex": fresh["row_index"], "columnIndex": fresh["headers"].index(FIELD_HEADERS[change["field"]])},
                "rows": [{"values": [cell]}], "fields": fields}})
        self.request("POST", ":batchUpdate", json={"requests": requests})
        if check_plan(self.snapshot(plan["task"]), plan) != "already_applied":
            raise ValueError("Write readback differs from the plan; inspect the sheet before retrying.")
        return {"result": "verified", "cells": len(plan["changes"])}
