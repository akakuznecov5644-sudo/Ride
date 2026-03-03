#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List

from robot.libraries.BuiltIn import BuiltIn
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from libs import excel_params

BASE_URL = "https://192.168.84.200"
BUILDER_URL = f"{BASE_URL}/report/builder"
REPORT_URL_TMPL = f"{BASE_URL}/report/page/{{report_id}}"


@dataclass
class ReportResult:
    report_id: str
    ok: bool
    reasons: List[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=4)
    parser.add_argument("--per-session", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def build_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    for arg in (
        "--disable-notifications",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--ignore-certificate-errors",
        "--disable-gpu",
        "--start-maximized",
    ):
        options.add_argument(arg)
    options.set_capability("goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"})
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Page.enable", {})
    driver.execute_cdp_cmd("Log.enable", {})
    return driver


def keyword_login(driver: webdriver.Chrome, timeout: float) -> None:
    # Прямое обращение к keyword Login из libs/excel_params.py
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    sl.driver = driver
    excel_params.login()
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))


def keyword_wait_until_page_has_report_parameters(driver: webdriver.Chrome, timeout: float) -> bool:
    # Аналог keyword Wait Until Page Has из libs/excel_params.py
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.XPATH, "//span[contains(., 'Report parameters')]")
            )
        )
        return True
    except TimeoutException:
        return False


def collect_report_ids(driver: webdriver.Chrome, timeout: float) -> List[str]:
    driver.get(BUILDER_URL)
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    rows = driver.find_elements(By.XPATH, "//tr[td]")
    ids: List[str] = []

    for row in rows:
        cells = row.find_elements(By.XPATH, "./td")
        for c in cells:
            txt = c.text.strip()
            if re.fullmatch(r"\d+", txt):
                ids.append(txt)
                break

    seen = set()
    uniq = []
    for rid in ids:
        if rid not in seen:
            seen.add(rid)
            uniq.append(rid)
    return uniq


def clear_logs(driver: webdriver.Chrome) -> None:
    _ = driver.get_log("browser")
    _ = driver.get_log("performance")


def extract_errors(driver: webdriver.Chrome) -> List[str]:
    errors: List[str] = []

    for entry in driver.get_log("browser"):
        msg = entry.get("message", "")
        lower = msg.lower()
        if entry.get("level") == "SEVERE" or "ora" in lower or "500" in lower or "date.error.range_format" in lower:
            errors.append(f"console: {msg}")

    for entry in driver.get_log("performance"):
        try:
            raw = json.loads(entry["message"])["message"]
        except Exception:
            continue

        method = raw.get("method", "")
        params = raw.get("params", {})

        if method == "Network.responseReceived":
            response = params.get("response", {})
            url = response.get("url", "")
            status = int(response.get("status", 0) or 0)
            req_id = params.get("requestId")

            if status >= 500 or "ora" in url.lower():
                errors.append(f"network: {status} {url}")

            if "/report/data/" in url and req_id:
                try:
                    body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": req_id}).get("body", "")
                except Exception:
                    body = ""
                low_body = body.lower()
                if "success" in low_body and "false" in low_body and "date.error.range_format" in low_body:
                    errors.append(f"network-body: {url} => {body[:300]}")
                if "ora" in low_body or "500" in low_body:
                    errors.append(f"network-body: {url} => {body[:300]}")

    return errors


def process_report(driver: webdriver.Chrome, report_id: str, timeout: float) -> ReportResult:
    result = ReportResult(report_id=report_id, ok=True)

    driver.execute_script("window.open('about:blank','_blank');")
    driver.switch_to.window(driver.window_handles[-1])
    driver.get(REPORT_URL_TMPL.format(report_id=report_id))

    if ":3443" in driver.current_url:
        result.ok = False
        result.reasons.append("url contains :3443")
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return result

    if not keyword_wait_until_page_has_report_parameters(driver, timeout):
        result.ok = False
        result.reasons.append("missing Report parameters block")
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return result

    clear_logs(driver)

    rp = driver.find_element(By.XPATH, "//span[contains(., 'Report parameters')]")
    rp.click()

    show_btn = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, "//button[.//span[contains(., 'Show')] or contains(., 'Show')]") )
    )
    show_btn.click()

    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    errors = extract_errors(driver)
    if errors:
        result.ok = False
        result.reasons.extend(errors)

    driver.close()
    driver.switch_to.window(driver.window_handles[0])
    return result


def run_session(session_index: int, ids: List[str], timeout: float) -> List[ReportResult]:
    driver = build_driver()
    try:
        if not ids:
            return []

        # Первый отчет: логин в рамках сеанса
        first_url = REPORT_URL_TMPL.format(report_id=ids[0])
        driver.get(first_url)
        keyword_login(driver, timeout)

        results = [process_report(driver, ids[0], timeout)]
        for rid in ids[1:]:
            results.append(process_report(driver, rid, timeout))
        return results
    finally:
        driver.quit()


def chunk_ids(ids: List[str], sessions: int, per_session: int) -> List[List[str]]:
    batches = []
    limit = sessions * per_session
    selected = ids[:limit]
    for i in range(sessions):
        start = i * per_session
        end = start + per_session
        batches.append(selected[start:end])
    return batches


def main() -> int:
    args = parse_args()

    bootstrap = build_driver()
    try:
        bootstrap.get(BUILDER_URL)
        keyword_login(bootstrap, args.timeout)
        ids = collect_report_ids(bootstrap, args.timeout)
    finally:
        bootstrap.quit()

    batches = chunk_ids(ids, args.sessions, args.per_session)

    all_results: List[ReportResult] = []
    with ThreadPoolExecutor(max_workers=args.sessions) as ex:
        futures = [
            ex.submit(run_session, i, batch, args.timeout)
            for i, batch in enumerate(batches)
            if batch
        ]
        for f in futures:
            all_results.extend(f.result())

    failed = [r for r in all_results if not r.ok]

    print(f"Всего ID: {len(ids)}")
    print(f"Обработано: {len(all_results)}")
    print(f"Ошибок: {len(failed)}")
    for item in failed:
        print(f"- ID {item.report_id}: {' | '.join(item.reasons)}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
