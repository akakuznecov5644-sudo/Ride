# excel_params.py
# ────────────────────────────────────────────────────────────────────
# Библиотеки
# ────────────────────────────────────────────────────────────────────
from robot.api.deco import keyword
from selenium import webdriver
import re, pandas as pd
import json
import re
import time, datetime
from typing import Union
from datetime import datetime
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from robot.libraries.BuiltIn import BuiltIn
from robot.api.deco import keyword
from selenium.webdriver.common.action_chains import ActionChains    
from selenium.webdriver.common.keys import Keys   
from selenium.common.exceptions import MoveTargetOutOfBoundsException

CSS_DD = ".ant-select-dropdown:not(.ant-select-dropdown-hidden)"
CSS_OPT = f"{CSS_DD} .ant-select-item-option"


_dbg_counter = 0
def _dbg(msg: str):
    """INFO‑лог + screenshot c порядковым номером."""
    global _dbg_counter
    _dbg_counter += 1
    BuiltIn().log(f"[DEBUG‑SEL] {msg}", "INFO")

    folder = Path(__file__).with_name("sel_log")
    folder.mkdir(exist_ok=True)
    fname = folder / f"step_{_dbg_counter:02}_{datetime.now():%H%M%S}.png"

    BuiltIn().get_library_instance("SeleniumLibrary")\
            .capture_page_screenshot(str(fname))
# ─── общие утилиты ─────────────────────────────────────────────────
def _parse(pair):
    m = re.match(r'\s*([\w\-:]+)\s*=\s*["\']?([^\"\']+)["\']?\s*$', pair)
    if not m:
        raise ValueError('нужно attr="value"')
    return m.group(1), m.group(2)

def _get_driver():
    return BuiltIn().get_library_instance("SeleniumLibrary").driver

def _select_root(attr_pair, index):
    a, v = _parse(attr_pair)
    css  = f"[{a}*='{v}']"
    if index:
        locator = (By.XPATH, f"({css})[{index}]")
    else:
        locator = (By.CSS_SELECTOR, css)

    drv  = _get_driver()
    el   = WebDriverWait(drv, 6).until(EC.presence_of_element_located(locator))
    root = el
    while root and "ant-select" not in (root.get_attribute("class") or ""):
        root = drv.execute_script("return arguments[0].parentElement;", root)
    if not root:
        raise AssertionError(f"ant‑select для {attr_pair} не найден")
    return root, drv

def _open_dropdown(root, drv, wait=6):
    # ➊ прокрутка
    _dbg("scrollIntoView .ant-select")
    drv.execute_script(
        "arguments[0].scrollIntoView({block:'center',inline:'center'});", root
    )

    # ➋ mousedown‑mouseup (ActionChains)
    _dbg("ActionChains: move_to_element ▸ click (mousedown+mouseup)")
    try:
        ActionChains(drv).move_to_element(root).pause(0.05).click().perform()
    except MoveTargetOutOfBoundsException:
        _dbg("MoveTargetOutOfBounds → fallback JS‑click по root")
        drv.execute_script("arguments[0].click()", root)

    # ➌ ждём 500 мс появления меню
    try:
        WebDriverWait(drv, 0.5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, CSS_DD))
        )
        _dbg("Dropdown появился после ActionChains‑клика")
        return
    except TimeoutException:
        _dbg("Dropdown НЕ появился → пробуем Space по скрытому input")

    # ➍ fallback: клавиша Space
    try:
        inp = root.find_element(
            By.CSS_SELECTOR,
            "input[role='combobox'], input[type='search'].ant-select-selection-search-input"
        )
        inp.send_keys(Keys.SPACE)
        _dbg("Space отправлен, ждём выпадайку")
    except NoSuchElementException:
        _dbg("Input не найден → JS‑click ещё раз")
        drv.execute_script("arguments[0].click()", root)

    # ➎ финальное ожидание
    WebDriverWait(drv, wait).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, CSS_DD))
    )
    _dbg("Dropdown окончательно открыт")

def _click_option(text, drv, strict=True, wait=6):
    end = time.time() + wait
    while time.time() < end:
        for opt in drv.find_elements(By.CSS_SELECTOR, CSS_OPTION):
            opt_text = (opt.get_attribute("title") or opt.text).strip()
            cond = (opt_text == text) if strict else (text.lower() in opt_text.lower())
            if cond:
                drv.execute_script("arguments[0].click()", opt)
                WebDriverWait(drv, 6).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, CSS_DROPDOWN))
                )
                return
        time.sleep(0.1)
    raise AssertionError(f"Опция «{text}» не найдена за {wait} с")


class HtmlDumpListener:
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.errors_dir = Path(__file__).with_name("errors") / ts
        self.errors_dir.mkdir(parents=True, exist_ok=True)
        self._current_test = None
        self._saved_for_test = False          # флаг: уже сделали дамп?

    # --------------- Robot callbacks ----------------
    def start_test(self, data, result):
        self._current_test = data.name
        self._saved_for_test = False          # сбросить флаг на новый тест

    def end_keyword(self, data, result):
        if result.status == "FAIL" and not self._saved_for_test:
            self._dump_html()

    def end_test(self, data, result):
        # на случай, если ни один keyword не помечен FAIL,
        # а тест развалился тайм-аутом / teardown-ом
        if result.status == "FAIL" and not self._saved_for_test:
            self._dump_html()

    # --------------- helpers ------------------------
    def _dump_html(self):
        rid = self._extract_report_id(self._current_test) or "unknown"
        target = self.errors_dir / f"{rid}.html"
        try:
            drv = BuiltIn().get_library_instance("SeleniumLibrary").driver
        except RuntimeError:
            return  # Selenium ещё не инициализировался

        try:
            html = drv.find_element(
                By.CSS_SELECTOR, "div.ant-drawer-content-wrapper"
            ).get_attribute("outerHTML")
        except NoSuchElementException:
            html = drv.page_source  # fallback

        target.write_text(html, encoding="utf-8")
        self._saved_for_test = True

    @staticmethod
    def _extract_report_id(name: str):
        m = re.search(r"\d+", name or "")
        return m.group(0) if m else None
# ────────────────────────────────────────────────────────────────

ROBOT_LIBRARY_LISTENER = HtmlDumpListener()

# ────────────────────────────────────────────────────────────────────
# 0. Базовая инфраструктура: запуск / остановка браузера и логин
# ────────────────────────────────────────────────────────────────────
@keyword("Browser start")
def browser_start():
    """
    Локальный запуск Chrome + включение CDP + переход на /login.
    """
    sl = BuiltIn().get_library_instance("SeleniumLibrary")

    opts = webdriver.ChromeOptions()
    for arg in (
        "--disable-notifications", "--no-sandbox",
        "--disable-dev-shm-usage", "--ignore-certificate-errors",
        "--disable-gpu"
    ):
        opts.add_argument(arg)
    # ⬇︎ ТОЛЬКО локальный драйвер — Selenium сам найдёт chromedriver
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    sl.create_webdriver("Chrome", options=opts)

    enable_chrome_cdp()
    sl.set_selenium_timeout(BuiltIn().get_variable_value("${SEL_TIMEOUT}", "60 s"))
    clear_perf_log()                                       # сразу чистим лог
    sl.go_to(f"{BuiltIn().get_variable_value('${BASE_URL}')}/login")


@keyword("Browser stop")
def browser_stop():
    BuiltIn().get_library_instance("SeleniumLibrary").close_all_browsers()


@keyword("Open And Login Once")
def open_and_login_once():
    """
    Высокоуровневый шаг: открыть браузер и залогиниться (один раз для Suite).
    """
    browser_start()
    login()


@keyword("Login")
def login():
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    sl.input_text("id:basic__username", BuiltIn().get_variable_value("${USERNAME}"))
    sl.input_text("id:basic__password", BuiltIn().get_variable_value("${PASSWORD}"))
    sl.click_button("xpath://button[@type='submit' and .//span[.='Login']]")
    sl.wait_until_element_is_visible(
        "xpath://img[contains(@src,'/images/myacp.png')]",
        BuiltIn().get_variable_value("${SEL_TIMEOUT}", "60 s")
    )


@keyword("Screen Error")
def screen_error(name: str = None):
    """
    Делаем скриншот с читаемым именем, если имя не передано.
    """
    if not name:
        name = f"screenshot_{int(time.time())}.png"
    BuiltIn().get_library_instance("SeleniumLibrary") \
        .capture_page_screenshot(name)


# ────────────────────────────────────────────────────────────────────
# 1. Чтение параметров отчёта из Excel
# ────────────────────────────────────────────────────────────────────
@keyword("Get Params For Report")
def get_params_for_report(excel_path: str, sheet_name: str, report_id):
    return get_params_for_report_enhanced(excel_path, sheet_name, report_id)


# ────────────────────────────────────────────────────────────────────
# 2. Chrome CDP / performance-log
# ────────────────────────────────────────────────────────────────────
@keyword("Enable Chrome CDP")
def enable_chrome_cdp():
    """
    Включает прослушку Network.* через CDP.
    """
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    drv = sl.driver
    drv.execute_cdp_cmd("Network.enable", {
        "maxTotalBufferSize":    10_000_000,
        "maxResourceBufferSize": 5_000_000
    })
    drv.execute_cdp_cmd("Page.enable", {})
    drv.execute_cdp_cmd("Log.enable", {})


@keyword("Dump Performance Log")
def dump_performance_log():
    """
    Сбрасывает весь накопленный performance-лог в консоль.
    """
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    for e in sl.driver.get_log("performance"):
        print(e)


@keyword("Clear Perf Log")
def clear_perf_log():
    """
    Мгновенно очищает performance-log: просто вычитываем все записи.
    """
    _ = BuiltIn().get_library_instance("SeleniumLibrary") \
        .driver.get_log("performance")


# ────────────────────────────────────────────────────────────────────
# 3. Проверка XHR-ответов отчётов
# ────────────────────────────────────────────────────────────────────
@keyword("Collect And Check Response Bodies")
def collect_and_check_response_bodies(
    url_pattern: str = "report/data/",
    first_response_timeout: float = 30.0,
    settle_timeout: float = 1.0,
):
    """
    Собирает ВСЕ XHR, чьи URL содержат *url_pattern*,
    подтягивает тела ответов через CDP и ищет: HTTP 4xx/5xx,
    `"success":false`, ORA-ошибки.
    """
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    drv = sl.driver

    # ➊ ждём первый ответ
    start = time.time()
    while time.time() - start < first_response_timeout:
        if drv.get_log("performance"):
            break
        time.sleep(0.2)

    # ➋ ждём «тишину»
    last_change, all_entries = time.time(), []
    while time.time() - last_change < settle_timeout:
        new_entries = drv.get_log("performance")
        if new_entries:
            all_entries.extend(new_entries)
            last_change = time.time()
        time.sleep(0.2)

    # ➌ фильтруем ответы
    responses, errors = {}, []
    for entry in all_entries:
        msg = json.loads(entry["message"])
        if msg["message"]["method"] != "Network.responseReceived":
            continue
        p = msg["message"]["params"]
        url = p["response"]["url"]
        if url_pattern not in url:
            continue
        rid = p["requestId"]
        responses[rid] = {
            "url":    url,
            "status": p["response"]["status"],
        }

    # ➍ получаем тела
    bodies_retrieved = 0
    for rid, meta in responses.items():
        url, status = meta["url"], meta["status"]
        body = None
        for _ in range(10):
            try:
                body = drv.execute_cdp_cmd("Network.getResponseBody",
                                           {"requestId": rid}).get("body", "")
                break
            except Exception:
                time.sleep(0.3)

        if body is None:
            errors.append(f"❌ тело недоступно: {url}")
            continue

        bodies_retrieved += 1
        lbody = body.lower()

        if status >= 400:
            errors.append(f"❌ HTTP {status} at {url}")
        if '"success":false' in lbody:
            errors.append(f"❌ success:false в ответе {url}")
        if re.search(r'ora-\d{5}', lbody):
            for m in re.findall(r'ora-\d{5}[^"]*', lbody):
                errors.append(f"❌ {m} at {url}")

    if errors:
        raise AssertionError("\n".join(errors))

    return {
        "requests_count":   len(responses),
        "bodies_retrieved": bodies_retrieved,
        "errors":           errors,
    }


@keyword("Get Response Body")
def get_response_body(url_pattern="report/data/"):
    """
    Возвращает тело *первого* XHR, чей URL содержит *url_pattern*.
    """
    sl, drv = BuiltIn().get_library_instance("SeleniumLibrary"), None
    drv = sl.driver
    for entry in drv.get_log("performance"):
        try:
            msg = json.loads(entry["message"])
            if msg["message"]["method"] != "Network.responseReceived":
                continue
            p   = msg["message"]["params"]
            url = p["response"]["url"]
            if url_pattern in url:
                rid = p["requestId"]
                return drv.execute_cdp_cmd("Network.getResponseBody",
                                           {"requestId": rid}).get("body", "")
        except Exception:
            continue
    return None


@keyword("Backend Should Be Clean")
def backend_should_be_clean(report_id: int):
    """
    Проверка, что /report/data/{id} отработал без ошибок.
    """
    return collect_and_check_response_bodies(
        f"/report/data/{report_id}",
        first_response_timeout=60
    )


# ────────────────────────────────────────────────────────────────────
# 4. Универсальные хелперы для Ant Design-форм
# ────────────────────────────────────────────────────────────────────
@keyword("Get Universal XPath By Type And Index")
def get_universal_xpath_by_type_and_index(field_type: str, idx: int):
    mapping = {
        "date":   f"(//input[contains(@class,'ant-picker-input')])[{idx}]",
        "select": f"(//input[contains(@class,'ant-select-selection-search-input')])[{idx}]",
        "number": f"(//input[@type='number' and starts-with(@id,'query_')])[{idx}]",
        "text":   f"(//input[@type='text' and starts-with(@id,'query_')] | //textarea[starts-with(@id,'query_')])[{idx}]",
    }
    return mapping[field_type]




# — ниже четыре «узкоспециализированных» заполнялки ————
@keyword("Fill Antd Date Field By WebElement")
def fill_antd_date_field_by_webelement(element, value):
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    sl.click_element(element)
    time.sleep(0.2)
    sl.press_keys(element, "CTRL+a+DELETE")
    sl.input_text(element, value)
    if ":" in value:                                       # есть время
        sl.wait_until_element_is_visible(
            "css:.ant-picker-panel-container", "5 s")
        BuiltIn().run_keyword_and_ignore_error(
            "Click Button", "css:.ant-picker-ok button")
    else:
        sl.press_keys(element, "ENTER")
    time.sleep(0.3)



@keyword("Fill Antd Number Field By Webelement")
def fill_antd_number_field_by_webelement(field_id: str, number_value: str | int | float):
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    num_el = sl.get_webelement(f"css=input[id='{field_id}']")
    num_el.clear()
    num_el.send_keys(str(number_value))



@keyword("Fill Antd Text Field By Webelement")
def fill_antd_text_field_by_webelement(field_id: str, text: str):
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    input_el = sl.get_webelement(f"css=input[id='{field_id}']")
    input_el.clear()
    input_el.send_keys(text)


@keyword("Fill Antd Field Universal")
def fill_antd_field_universal(field_type, element_or_xpath, value):
    """
    Делегирует нужной «узкой» функции в зависимости от типа поля.
    """
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    if isinstance(element_or_xpath, str):
        element = sl.get_webelement(element_or_xpath)
    else:
        element = element_or_xpath

    fn = {
        "date":   fill_antd_date_field_by_webelement,
        "select": fill_antd_select_field_by_webelement,
        "number": fill_antd_number_field_by_webelement,
        "text":   fill_antd_text_field_by_webelement,
    }.get(field_type, fill_antd_text_field_by_webelement)
    fn(element, value)


# ────────────────────────────────────────────────────────────────────
# 5. Высокоуровневые действия с отчётами
# ────────────────────────────────────────────────────────────────────
@keyword("Run Report From Excel")
def run_report_from_excel(report_id):
    return run_report_from_excel_enhanced(report_id)

@keyword("Check Report Page Opens")
def check_report_page_opens(report_id):
    """
    Быстрая smoke-проверка: страница загрузилась + XHR без ошибок.
    """
    enable_chrome_cdp()
    clear_perf_log()

    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    sl.go_to(f"{BuiltIn().get_variable_value('${BASE_URL}')}/report/page/{report_id}")
    sl.wait_until_page_does_not_contain_element("css:.ant-spin", "30 s")
    sl.wait_until_page_contains_element("css:.ant-table", "30 s")

    ok = BuiltIn().run_keyword_and_return_status(
        "Backend Should Be Clean", report_id)
    if not ok:
        BuiltIn().fail(f"▶ Найдены ошибки в XHR отчёта {report_id}")


@keyword("Check Report For Ora")
def check_report_for_ora(report_id):
    """
    Проверяет страницу отчёта на ORA-ошибки и HTTP 4xx/5xx после загрузки.
    """
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    sl.wait_until_page_does_not_contain_element("css:.ant-spin", "30 s")
    sl.wait_until_page_contains_element("css:.ant-table", "30 s")

    res = collect_and_check_response_bodies(f"report/data/{report_id}")
    if res["errors"]:
        for e in res["errors"]:
            BuiltIn().log(e, console=True)
        BuiltIn().fail("Найдены ошибки в XHR ответах отчёта")


# ────────────────────────────────────────────────────────────────────
# 6. Утилиты для точечного анализа (по необходимости)
# ────────────────────────────────────────────────────────────────────
@keyword("Get Report Response Body")
def get_report_response_body(url_pattern: str = "report/data/"):
    return get_response_body(url_pattern)


@keyword("Check Response Body Contains")
def check_response_body_contains(text, url_pattern: str = "report/data/"):
    body = get_response_body(url_pattern)
    if body is None or text not in body:
        BuiltIn().fail(f"Строка «{text}» не найдена в ответе")


@keyword("Check Response Body Does Not Contain")
def check_response_body_does_not_contain(text, url_pattern: str = "report/data/"):
    body = get_response_body(url_pattern)
    if body is None or text in body:
        BuiltIn().fail(f"Нежелательная строка «{text}» найдена в ответе")




# ─── keyword ──────────────────────────────────────────────────────────
def _visible_text(sel):
    """Возвращает отображаемый текст селекта (item или placeholder)."""
    try:
        el = sel.find_element(
            By.CSS_SELECTOR,
            ".ant-select-selection-item, .ant-select-selection-placeholder",
        )
        return (el.get_attribute("title") or el.text).strip()
    except Exception:
        return ""

def _select_inside_form_by_default_value(driver, default_value: str):
    """
    Находит select элемент по значению по умолчанию (отображаемому тексту)
    """
    # Расширенный поиск select элементов
    selectors = [
        "form#query div.ant-select:not(.ant-select-auto-complete)",
        "form div.ant-select:not(.ant-select-auto-complete)", 
        ".ant-form div.ant-select:not(.ant-select-auto-complete)",
        "div.ant-select:not(.ant-select-auto-complete)",
        "[class*='ant-select']:not([class*='auto-complete'])"
    ]
    
    BuiltIn().log(f"Ищем select с default значением: '{default_value}'", "INFO")
    
    found_selects = []
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for sel in elements:
                if sel.is_displayed():
                    current_text = _visible_text(sel)
                    found_selects.append(f"'{current_text}'")
                    BuiltIn().log(f"Найден select с текстом: '{current_text}'", "DEBUG")
                    
                    # Проверяем точное совпадение
                    if current_text == default_value:
                        BuiltIn().log(f"Найден select с точным совпадением: '{current_text}'", "INFO")
                        return sel
                    
                    # Проверяем частичное совпадение (если точного нет)
                    if default_value.lower() in current_text.lower():
                        BuiltIn().log(f"Найден select с частичным совпадением: '{current_text}' содержит '{default_value}'", "INFO")
                        return sel
        except Exception as e:
            BuiltIn().log(f"Ошибка при поиске с селектором {selector}: {e}", "DEBUG")
            continue
    
    error_msg = f"Не найден select с default значением '{default_value}'. Найденные select'ы: {found_selects}"
    BuiltIn().log(error_msg, "ERROR")
    raise NoSuchElementException(error_msg)

def _select_from_element(el):
    """Находит ant-select элемент от заданного элемента"""
    # Стратегия 1: сам элемент является ant-select
    if "ant-select" in el.get_attribute("class"):
        return el
    
    # Стратегия 2: ищем ant-select среди предков
    ancestor_selectors = [
        "ancestor-or-self::div[contains(@class,'ant-select')]",
        "ancestor-or-self::*[contains(@class,'ant-select')]"
    ]
    
    for selector in ancestor_selectors:
        try:
            candidates = el.find_elements(By.XPATH, selector)
            for cand in candidates:
                if ("ant-select" in cand.get_attribute("class") and 
                    "ant-select-auto-complete" not in cand.get_attribute("class")):
                    return cand
        except NoSuchElementException:
            continue
    
    # Стратегия 3: ищем ant-select среди потомков
    descendant_selectors = [
        "div.ant-select:not(.ant-select-auto-complete)",
        ".ant-select:not(.ant-select-auto-complete)",
        "*[contains(@class,'ant-select')]:not([contains(@class,'ant-select-auto-complete')])"
    ]
    
    for selector in descendant_selectors:
        try:
            return el.find_element(By.CSS_SELECTOR, selector)
        except NoSuchElementException:
            continue
    
    # Стратегия 4: ищем через form-item
    try:
        form_item_selectors = [
            "ancestor::div[contains(@class,'ant-form-item')]",
            "ancestor::*[contains(@class,'form-item')]",
            "../.."  # простой подъем на два уровня вверх
        ]
        
        for fi_selector in form_item_selectors:
            try:
                fi = el.find_element(By.XPATH, fi_selector)
                for desc_selector in descendant_selectors:
                    try:
                        return fi.find_element(By.CSS_SELECTOR, desc_selector)
                    except NoSuchElementException:
                        continue
            except NoSuchElementException:
                continue
    except Exception:
        pass
    
    # Стратегия 5: поиск по близости (siblings)
    try:
        siblings = el.find_elements(By.XPATH, "following-sibling::*[contains(@class,'ant-select')] | preceding-sibling::*[contains(@class,'ant-select')]")
        for sibling in siblings:
            if "ant-select-auto-complete" not in sibling.get_attribute("class"):
                return sibling
    except Exception:
        pass
    
    raise NoSuchElementException("Не найден ant-select внутри формы отчёта.")

@keyword("Fill Antd Select Field By Default Value")
def fill_antd_select_field_by_default_value(default_value: str, target_value: str, *, wait_sec: int = 10):
    """
    Заполняет Ant Design Select, найдя его по значению по умолчанию
    default_value - текущее отображаемое значение в select
    target_value - значение, которое нужно выбрать
    """
    drv = BuiltIn().get_library_instance("SeleniumLibrary").driver
    
    BuiltIn().log(f"SELECT: ищем по default '{default_value}' → выбираем '{target_value}'", "INFO")
    
    try:
        # Находим select по значению по умолчанию
        root = _select_inside_form_by_default_value(drv, default_value.strip())
        
        # Используем существующую логику заполнения
        return _fill_select_element(drv, root, target_value.strip(), wait_sec)
        
    except Exception as e:
        BuiltIn().log(f"Ошибка при заполнении select с default '{default_value}': {str(e)}", "ERROR")
        # Делаем скриншот для отладки
        try:
            BuiltIn().get_library_instance("SeleniumLibrary").capture_page_screenshot(
                f"select_by_default_error_{int(time.time())}.png"
            )
        except Exception:
            pass
        raise

def _fill_select_element(driver, root_element, target_value: str, wait_sec: int = 10):
    """
    Общая логика заполнения select элемента
    """
    # Проверяем, что элемент видим и активен
    if not root_element.is_displayed():
        raise Exception("Select элемент не видим")
    
    if not root_element.is_enabled():
        raise Exception("Select элемент не активен")

    # Ищем input элемент для взаимодействия
    input_selectors = [
        "input.ant-select-selection-search-input",
        ".ant-select-selector input",
        "input[role='combobox']", 
        "input"
    ]
    
    inp = None
    for input_selector in input_selectors:
        try:
            inp = root_element.find_element(By.CSS_SELECTOR, input_selector)
            if inp.is_displayed():
                break
        except NoSuchElementException:
            continue
    
    if inp is None:
        # Если не нашли input, пробуем кликнуть по самому селекту
        driver.execute_script("arguments[0].click()", root_element)
        time.sleep(0.5)
    else:
        # Фокусируемся на input и открываем dropdown
        driver.execute_script("arguments[0].focus()", inp)
        time.sleep(0.2)
        
        # Пробуем разные способы открыть dropdown
        try:
            inp.send_keys(Keys.SPACE)
        except Exception:
            try:
                inp.click()
            except Exception:
                root_element.click()
        
        time.sleep(0.3)

    # Ждем появления dropdown
    dropdown_selectors = [
        ".ant-select-dropdown:not(.ant-select-dropdown-hidden)",
        ".ant-select-dropdown[style*='display: block']",
        ".ant-select-dropdown.ant-select-dropdown-placement-bottomLeft",
        ".ant-select-dropdown"
    ]
    
    dropdown_visible = False
    for dropdown_selector in dropdown_selectors:
        try:
            WebDriverWait(driver, wait_sec).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, dropdown_selector))
            )
            dropdown_visible = True
            BuiltIn().log(f"Dropdown открылся с селектором: {dropdown_selector}", "DEBUG")
            break
        except TimeoutException:
            continue
    
    if not dropdown_visible:
        raise Exception("Dropdown не открылся")

    # Ищем элементы в dropdown
    item_selectors = [
        ".ant-select-dropdown .ant-select-item-option[title]",
        ".ant-select-dropdown .ant-select-item-option",
        ".ant-select-dropdown .ant-select-item",
        ".ant-select-dropdown [role='option']"
    ]
    
    items = []
    for item_selector in item_selectors:
        try:
            items = driver.find_elements(By.CSS_SELECTOR, item_selector)
            if items:
                BuiltIn().log(f"Найдено {len(items)} элементов с селектором: {item_selector}", "DEBUG")
                break
        except Exception:
            continue
    
    if not items:
        raise Exception("Не найдены элементы в dropdown")

    # Ищем нужный элемент
    target_item = None
    available_values = []
    
    for item in items:
        item_text = (item.get_attribute("title") or 
                    item.get_attribute("label") or 
                    item.text or "").strip()
        
        available_values.append(item_text)
        BuiltIn().log(f"Доступный элемент: '{item_text}'", "DEBUG")
        
        if item_text == target_value:
            target_item = item
            BuiltIn().log(f"Найден точный элемент: '{item_text}'", "DEBUG")
            break
    
    if target_item is None:
        # Если не нашли точное совпадение, попробуем частичное
        for item in items:
            item_text = (item.get_attribute("title") or 
                        item.get_attribute("label") or 
                        item.text or "").strip()
            
            if target_value.lower() in item_text.lower():
                target_item = item
                BuiltIn().log(f"Найден элемент с частичным совпадением: '{item_text}'", "DEBUG")
                break
    
    if target_item is None:
        raise AssertionError(f"Пункт «{target_value}» не найден; доступно: {available_values}")

    # Кликаем по найденному элементу
    try:
        driver.execute_script("arguments[0].click()", target_item)
        BuiltIn().log(f"Клик по элементу через JavaScript: '{target_value}'", "DEBUG")
    except Exception:
        target_item.click()
        BuiltIn().log(f"Обычный клик по элементу: '{target_value}'", "DEBUG")

    # Ждем закрытия dropdown
    time.sleep(0.5)
    
    # Проверяем, что dropdown закрылся
    for dropdown_selector in dropdown_selectors:
        try:
            WebDriverWait(driver, 3).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, dropdown_selector))
            )
            break
        except TimeoutException:
            continue
    
    time.sleep(0.2)
    BuiltIn().log(f"Успешно выбран элемент: {target_value}", "INFO")
    return True

@keyword("Debug Select Elements")
def debug_select_elements():
    """
    Отладочная функция для анализа всех select элементов на странице
    """
    drv = BuiltIn().get_library_instance("SeleniumLibrary").driver
    
    print("=== ОТЛАДКА SELECT ЭЛЕМЕНТОВ ===")
    
    selectors_to_check = [
        ".ant-select",
        "div[class*='ant-select']",
        "form .ant-select",
        "form div[class*='select']",
        "[role='combobox']",
        "select"
    ]
    
    for i, selector in enumerate(selectors_to_check):
        try:
            elements = drv.find_elements(By.CSS_SELECTOR, selector)
            print(f"\n{i+1}. Селектор: {selector}")
            print(f"   Найдено элементов: {len(elements)}")
            
            for j, el in enumerate(elements):
                print(f"   Элемент {j+1}:")
                print(f"     - Видим: {el.is_displayed()}")
                print(f"     - Активен: {el.is_enabled()}")
                print(f"     - Классы: {el.get_attribute('class')}")
                print(f"     - Текст: {_visible_text(el)}")
                print(f"     - Расположение: {el.location}")
                
        except Exception as e:
            print(f"Ошибка с селектором {selector}: {e}")

def run_report_from_excel_enhanced(report_id: int):
    """
    1. Открывает страницу отчёта /report/page/<report_id>.
    2. Нажимает «Report parameters», ждёт Drawer-форму.
    3. Заполняет поля по данным из Excel (select, text, date, number).
    4. Жмёт «Show» и дожидается закрытия Drawer’а.

    Поддерживаются ячейки Excel:
        select(Default)(Target)
        text(Default)(New)
        date(01.01.2025)
        number(10)
        text(СвободныйТекст)   — индексный режим
    """
    # ── базовые объекты Selenium/Robot ────────────────────────────────
    sl  = BuiltIn().get_library_instance("SeleniumLibrary")
    drv = sl.driver

    # ── URL отчёта ────────────────────────────────────────────────────
    base_url   = BuiltIn().get_variable_value("${BASE_URL}",
                                              "https://192.168.84.200")
    report_url = f"{base_url}/report/page/{report_id}"
    BuiltIn().log(f"Открываем отчёт: {report_url}", "INFO")
    drv.get(report_url)

    # ── жмём кнопку «Report parameters» ───────────────────────────────
    try:
        btn = WebDriverWait(drv, 6).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[.//span[normalize-space()='Report parameters']]"
            ))
        )
        drv.execute_script("arguments[0].click();", btn)
    except TimeoutException:
        raise AssertionError("Кнопка «Report parameters» не найдена/не кликабельна")

    # ── ждём появления Drawer-формы ───────────────────────────────────
    WebDriverWait(drv, 12).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "form#query"))
    )

    # ── читаем параметры из Excel ─────────────────────────────────────
    excel_path = BuiltIn().get_variable_value("${EXCEL_PATH}")
    sheet_name = BuiltIn().get_variable_value("${EXCEL_SHEET}", 0)
    params     = get_params_for_report_enhanced(excel_path, sheet_name, report_id)
    BuiltIn().log(f"Найдено параметров: {len(params)}", "INFO")

    # ── собираем индексные поля (старый режим) ────────────────────────
    date_i = text_i = number_i = 0
    date_fields   = drv.find_elements(By.CSS_SELECTOR, "form#query div.ant-picker input")
    text_fields   = drv.find_elements(By.CSS_SELECTOR, "form#query input[type='text'], form#query textarea")
    number_fields = drv.find_elements(By.CSS_SELECTOR, "form#query input[type='number']")

    # ── заполняем поля ────────────────────────────────────────────────
    for p in params:
        typ = p["type"]

        if typ == "select":
            BuiltIn().log(f"select: '{p['default']}' → '{p['value']}'", "DEBUG")
            fill_antd_select_field_by_webelement(p["default"], p["value"])

        elif typ == "text2":     # text(Default)(New)
            BuiltIn().log(f"text:   '{p['default']}' → '{p['value']}'", "DEBUG")
            fill_antd_text_field_by_webelement(p["default"], p["value"])

        elif typ == "date":
            fill_antd_date_field_by_webelement(date_fields[date_i], p["value"])
            date_i += 1

        elif typ == "number":
            fld = number_fields[number_i]
            if fld.is_displayed():
                fill_antd_number_field_by_webelement(fld, p["value"])
            else:
                BuiltIn().log("number-field скрыт – пропущено", "INFO")
            number_i += 1

        elif typ == "text":      # однострочный старый режим
            fld = text_fields[text_i]
            if fld.is_displayed():
                fill_antd_text_field_by_webelement(fld, p["value"])
            else:
                BuiltIn().log("text-field скрыт – пропущено", "INFO")
            text_i += 1

        else:
            BuiltIn().log(f"Неизвестный тип '{typ}' – пропуск", "WARN")

        time.sleep(0.1)          # маленькая пауза для стабильности

    # ── кликаем «Show» и ждём закрытия Drawer ─────────────────────────
    show_btn = WebDriverWait(drv, 6).until(
        EC.element_to_be_clickable((
            By.XPATH, "//button[.//span[normalize-space()='Show']]"
        ))
    )
    drv.execute_script("arguments[0].click();", show_btn)

    WebDriverWait(drv, 10).until(
        EC.invisibility_of_element_located((By.CSS_SELECTOR, ".ant-drawer-mask"))
    )
        
       
def get_params_for_report_enhanced(excel_path: str, sheet_name: str, report_id):
    """
    Читает строку с ID отчёта и формирует список параметров.

    Поддерживаемые форматы ячеек
    ────────────────────────────────────────────────────────────────────
    • date(01.01.2025)               → {"type":"date",   "value":"01.01.2025"}
    • number(10)                     → {"type":"number", "value":"10"}
    • select(Default)(Target)        → {"type":"select", "default":"Default",
                                                        "value":"Target"}
    • text(Default)(New)             → {"type":"text2",  "default":"Default",
                                                        "value":"New"}
    • СвободныйТекст                 → {"type":"text",   "value":"СвободныйТекст"}
    Если хотя бы одна скобка пуста, параметр трактуется как обычный текст.
    """
    # читаем лист без заголовков
    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, dtype=str)

    # ищем строку отчёта по первому столбцу
    idx = df[df.iloc[:, 0].astype(str).str.strip() == str(report_id).strip()].index
    if idx.empty:
        return []

    row = df.iloc[idx[0], 1:]                    # всё, что правее ID
    params = []

    # тип(знач1)  или  тип(знач1)(знач2)
    rx = re.compile(r"(\w+)\(([^()]*)\)(?:\(([^()]*)\))?$")

    for cell in row:
        cell = str(cell).strip() if pd.notna(cell) else ""
        if not cell:
            continue

        m = rx.match(cell)
        if not m:                                # свободный текст
            params.append({"type": "text", "value": cell})
            continue

        ptype, v1, v2 = [(m.group(i) or "").strip() for i in (1, 2, 3)]
        ptype = ptype.lower()

        # ── select с двумя непустыми скобками ─────────────────────────
        if ptype == "select" and v1 and v2:
            params.append({"type": "select",
                           "default": v1,
                           "value":   v2})

        # ── text(default)(new)  →  type text2 ─────────────────────────
        elif ptype == "text" and v1 and v2:
            params.append({"type": "text2",
                           "default": v1,
                           "value":   v2})

        # ── обычный шаблон  тип(значение) ─────────────────────────────
        elif v1:
            params.append({"type": ptype, "value": v1})

        # пустые скобки → игнорируем, т. к. считаем строку некорректной

    return params
    
    
# ────────────────────────────────────────────────────────────────────
# 1. Основной дирижёр
# ────────────────────────────────────────────────────────────────────
@keyword("Fill Antd Select Field By WebElement")
def fill_antd_select_field_by_webelement(field_id: str,
                                         target_txt: str,
                                         *, wait_sec: int = 8):
    """
    Универсальный кейворд для Ant Design-селектов внутри открытого Drawer.
    • field_id  – значение из Excel (может быть 'query_location_id' или 'rc_select_4');
    • target_txt – нужная опция (точное совпадение по title / тексту).
    """

    sl  = BuiltIn().get_library_instance("SeleniumLibrary")
    drv = sl.driver
    field_id, target_txt = field_id.strip(), target_txt.strip()

    # ── 1. ждём открытие Drawer (класс ant-drawer-open) ───────────────
    WebDriverWait(drv, wait_sec).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "div.ant-drawer-open")
    )

    # ── 2. ищем <input type=search> (seed) без риска stale ────────────
    def _find_seed(d):
        """возвращает seed или False, чтобы WebDriverWait продолжал ожидание"""
        sel_chain = [
            f"div.ant-drawer-open input#{field_id}",                                # точный id
            f"div.ant-drawer-open input[aria-controls*='{field_id}_list']",         # aria-controls (searchable)
            (f"div.ant-drawer-open label[for='{field_id}'] ~ "
             f"div.ant-select input[type='search']"),                               # через label
            (f"div.ant-drawer-open input#{field_id}[type='text'] ~ "
             f"div.ant-select input[type='search']"),                               # скрытый text-input
        ]
        for css in sel_chain:
            try:
                return d.find_element(By.CSS_SELECTOR, css)
            except (NoSuchElementException, StaleElementReferenceException):
                continue
        return False

    seed = WebDriverWait(drv, wait_sec).until(lambda d: _find_seed(d))

    # ── 3. определяем тип селекта ─────────────────────────────────────
    root = seed.find_element(
        By.XPATH,
        (
            "ancestor::div[contains(concat(' ',normalize-space(@class),' '),"
            " ' ant-select ')][not(contains(@class,'ant-select-selector'))][1]"
        )
    )
    root_cls = root.get_attribute("class") or ""
    editable = not seed.get_attribute("readonly")
    searchable = "ant-select-auto-complete" in root_cls and editable

    BuiltIn().log(
        f"[{field_id}] class='{root_cls}', editable={editable} → "
        f"{'SEARCHABLE' if searchable else 'PLAIN'}", "INFO"
    )

    # ── 4. делегируем заполнение ──────────────────────────────────────
    if searchable:
        fill_searchable_select(root, target_txt, wait_sec)
    else:
        fill_plain_select(seed, root, target_txt, wait_sec)


# ────────────────────────────────────────────────────────────────────
# 2. Кейворд для searchable-селекта
# ────────────────────────────────────────────────────────────────────
# ────────────────────────────────────────────────────────────────────
# 2. Исправленный кейворд для searchable-селекта
# ────────────────────────────────────────────────────────────────────
@keyword("Fill Searchable Select")
def fill_searchable_select(root, target_txt: str, wait_sec: int = 15):
    drv      = BuiltIn().get_library_instance("SeleniumLibrary").driver
    css_dd   = ".ant-select-dropdown:not(.ant-select-dropdown-hidden)"
    css_opt  = f"{css_dd} .ant-select-item-option"
    css_cal  = ".ant-picker-dropdown:not(.ant-picker-dropdown-hidden)"

    # 0️⃣ дождаться закрытия календарных попапов
    try:
        WebDriverWait(drv, 3).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, css_cal))
        )
    except:
        pass  # игнорируем если календаря нет

    # 1️⃣ Активируем селект - переводим из :visited в :focus/:active состояние
    selector = root.find_element(By.CSS_SELECTOR, ".ant-select-selector")
    
    # Сначала кликаем по селектору
    drv.execute_script("arguments[0].click()", selector)
    time.sleep(0.2)
    
    # 2️⃣ Находим input и активируем его для редактирования
    inp = root.find_element(By.CSS_SELECTOR, "input[type='search']")
    
    # Переводим input в активное состояние редактирования
    drv.execute_script("arguments[0].focus()", inp)
    time.sleep(0.1)
    
    # Дополнительный клик по input для активации
    drv.execute_script("arguments[0].click()", inp)
    time.sleep(0.2)
    
    # Имитируем начало ввода, чтобы селект перешёл в режим поиска
    inp.send_keys("")  # пустая строка для активации
    time.sleep(0.1)
    
    # 3️⃣ Очищаем поле от текущего значения (включая пробел)
    current_value = inp.get_attribute("value")
    if current_value:
        # Выделяем весь текст
        drv.execute_script("arguments[0].select()", inp)
        time.sleep(0.1)
        
        # Удаляем выделенный текст
        inp.send_keys(Keys.DELETE)
        time.sleep(0.1)
    
    # Дополнительная очистка через JavaScript
    drv.execute_script("arguments[0].value = '';", inp)
    drv.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", inp)
    time.sleep(0.1)

    # 4️⃣ Вводим целевой текст посимвольно
    for char in target_txt:
        inp.send_keys(char)
        time.sleep(0.05)  # небольшая задержка между символами
    
    # Дополнительно запускаем событие input для Ant Design
    drv.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", inp)
    time.sleep(0.5)  # даём время на появление выпадающего списка

    # 5️⃣ ждём пункт-совпадение
    def base(t: str) -> str: 
        return t.split("(")[0].strip()
    
    end, opt = time.time() + wait_sec, None
    while time.time() < end:
        try:
            options = drv.find_elements(By.CSS_SELECTOR, css_opt)
            for o in options:
                option_text = o.text.strip()
                if base(option_text) == target_txt or option_text == target_txt:
                    opt = o
                    break
            if opt: 
                break
        except:
            pass
        time.sleep(0.2)
    
    if not opt:
        raise AssertionError(f"«{target_txt}» не найдено за {wait_sec} с")

    # 6️⃣ кликаем пункт и ждём закрытия меню
    drv.execute_script("arguments[0].click()", opt)
    
    # Ждём закрытия выпадающего списка
    try:
        WebDriverWait(drv, wait_sec).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, css_dd))
        )
    except:
        pass  # если список уже закрыт
    
    time.sleep(0.2)





# ────────────────────────────────────────────────────────────────────
# 3. Кейворд для plain-селекта
# ────────────────────────────────────────────────────────────────────
@keyword("Fill Plain Select")
def fill_plain_select(seed, root, target_txt: str, wait_sec: int = 9):
    drv    = root.parent
    css_dd = ".ant-select-dropdown:not(.ant-select-dropdown-hidden)"

    # 1 — клик по .ant-select-selector через JS
    drv.execute_script(
        "arguments[0].click()",
        root.find_element(By.CSS_SELECTOR, ".ant-select-selector")
    )

    # ждём появления списка
    WebDriverWait(drv, wait_sec).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, css_dd))
    )

    # 2 — выбираем нужную опцию
    for opt in drv.find_elements(By.CSS_SELECTOR, f"{css_dd} .ant-select-item-option"):
        txt = (opt.get_attribute("title") or opt.text).strip()
        if txt == target_txt:
            drv.execute_script("arguments[0].click()", opt)
            break
    else:
        raise AssertionError(f"Опция «{target_txt}» не найдена")

    # 3 — ждём закрытия дроп-дауна
    WebDriverWait(drv, wait_sec).until(
        EC.invisibility_of_element_located((By.CSS_SELECTOR, css_dd))
    )
    time.sleep(0.2)
    
    
    



# ────────────────────────────────────────────────────────────────────
# 7. Универсальный клик по атрибуту
# ────────────────────────────────────────────────────────────────────
@keyword("Click By Attr")
def click_by_attr(attr_pair: str,
                  timeout: float = 5.0,
                  *,
                  index: int | None = None,
                  js_fallback: bool = True):
    """
    Нажимает на элемент, чей атрибут *содержит* указанную подстроку.

    ▸ attr_pair  – строка вида  attr="value"  (кавычки любые).  
      Пример:  data-menu-id="jackpotManager"
    ▸ timeout    – ожидание появления (сек).  
    ▸ index      – номер совпадения, если элементов несколько (1‑based).  
    ▸ js_fallback – при обычном WebDriver‑клике ловим ошибку и повторяем
      JavaScript‑кликом (полезно, если элемент перекрыт маской).

    Использование в Robot Framework:

        Click By Attr    data-menu-id="jackpotManager"
        Click By Attr    aria-label="Delete"    index=2
    """
    attr, val = re.match(r'\s*([\w\-:]+)\s*=\s*["\']?([^"\']+)["\']?\s*$', attr_pair).groups()
    css_repr = f'css:[{attr}*="{val}"]'
    # BuiltIn().log(f"Clicking element '{css_repr}'", "INFO")
    # ➊ разбираем пару attr="value"
    m = re.match(r'\s*([\w\-:]+)\s*=\s*["\']?([^"\']+)["\']?\s*$', attr_pair)
    if not m:
        raise ValueError('Ожидается строка вида attr="value"')
    attr, val = m.group(1), m.group(2)

    # ➋ строим CSS‑локатор «атрибут содержит подстроку»
    css = f'[{attr}*="{val}"]'
    locator = f'css:{css}'
    if index:
        locator = f'xpath:(({css}))[{index}]'

    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    drv = sl.driver

    sl.wait_until_element_is_visible(locator, f"{timeout} s")

    try:
        sl.click_element(locator)
    except Exception:
        if not js_fallback:
            raise
        el = sl.get_webelement(locator)
        drv.execute_script(
            "arguments[0].scrollIntoView({block:'center',inline:'center'});", el)
        drv.execute_script("arguments[0].click();", el)


@keyword("Open Url")
@keyword("Open Url")
def open_url(url: str,
             timeout: str = "30 s"):
    """
    Открывает страницу в текущем браузере SeleniumLibrary.

    ▸ url       – абсолютный (`https://…`) или относительный (`/login`) путь.  
    ▸ timeout   – сколько ждать появления <body> (по умолчанию 30 с).

    Примеры:
        Open Url    https://192.168.84.200/report/125
        Open Url    /players/list
    """
    sl   = BuiltIn().get_library_instance("SeleniumLibrary")
    base = BuiltIn().get_variable_value("${BASE_URL}", "")

    # относительный → абсолютный
    if not re.match(r"^https?://", url, re.I):
        if not base:
            raise AssertionError("BASE_URL не задан, а ссылка относительная.")
        url = base.rstrip("/") + "/" + url.lstrip("/")

    # INFO‑строка в стиле SeleniumLibrary
    BuiltIn().log(f"Opening url '{url}'", "INFO")

    sl.go_to(url)
    # ждём появление тега <body>, чтобы страница точно загрузилась
    sl.wait_until_page_contains_element("css:body", timeout)
    
    

@keyword("Click By Text")
def click_by_text(
    text: str,
    timeout: float = 6.0,
    *,
    index: int | None = None,
    exact: bool = False,
    js_fallback: bool = True,
    ):
    """
    Нажимает на <button>/<a>/<input> **с потомком‑<span>**, чей текст
    содержит (или точно равен) *text*.

        Click By Text    Report parameters
        Click By Text    Delete            index=2
    """
    BuiltIn().log(f"Clicking element with text \"{text}\"", "INFO")
    sl, drv = (
        BuiltIn().get_library_instance("SeleniumLibrary"),
        BuiltIn().get_library_instance("SeleniumLibrary").driver,
    )

    safe = text.replace('"', '\\"')
    # кнопка или ссылка, в которой есть <span> (или любой узел) с текстом
    if exact:
        xpath = (
            f"(//button|//a|//input)"
            f"[descendant::*[normalize-space(.)=\"{safe}\"]]"
        )
    else:
        xpath = (
            f"(//button|//a|//input)"
            f"[descendant::*[contains(normalize-space(.), \"{safe}\")]]"
        )

    if index:
        xpath = f"({xpath})[{index}]"

    locator = (By.XPATH, xpath)

    # ➊ ждём кликабельность (Ant Design любит маски)
    target = WebDriverWait(drv, timeout).until(
        EC.element_to_be_clickable(locator)
    )

    # ➋ сначала обычный click; при ошибке — JS‑клик
    try:
        target.click()
    except Exception:
        if not js_fallback:
            raise
        drv.execute_script(
            "arguments[0].scrollIntoView({block:'center',inline:'center'});", target
        )
        drv.execute_script("arguments[0].click();", target)


@keyword("Fill By Attr")
def fill_by_attr(attr_pair: str,
                 text: str,
                 timeout: float = 5.0,
                 *,
                 clear: bool = True,
                 index: int | None = None):
    """
    Вводит *text* в <input> / <textarea>, чей атрибут содержит указанную подстроку.

    ▸ **attr_pair** – строка вида  attr="value_part" .  
      Пример:  placeholder="Search"  или  data-test="login-input"
    ▸ **text**      – вводимое значение.  
    ▸ **timeout**   – ожидание появления элемента (сек).  
    ▸ **clear**     – True → очищаем поле перед вводом.  
    ▸ **index**     – N‑й элемент, если совпадений несколько (1‑based).

    Пример использования:

        Fill By Attr    name="username"        test_admin
        Fill By Attr    data-test="search"     Gaming   clear=${FALSE}
    """

    m = re.match(r'\s*([\w\-:]+)\s*=\s*["\']?([^"\']+)["\']?\s*$', attr_pair)
    if not m:
        raise ValueError('строка должна быть вида  attr="value"')
    attr, val = m.groups()
    css_repr = f'css:[{attr}*="{val}"]'
    BuiltIn().log(f"Typing text '{text}' into element '{css_repr}'", "INFO")

    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    sl.wait_until_page_contains_element(css_repr, timeout)
    elems = sl.get_webelements(css_repr)
    field = elems[index - 1] if index else elems[0]

    # выделяем всё, удаляем, вводим новый текст
    field.send_keys(Keys.CONTROL, "a", Keys.DELETE, text)
    

# ────────────────────────────────────────────────────────────────────
@keyword("Select By Attr")
def select_by_attr(attr_pair: str,
                   option_text: str,
                   *,
                   index: int | None = None,
                   wait_sec: int = 6):
    _dbg(f"START Select By Attr → {attr_pair=} {option_text=}")

    root, drv = _select_root(attr_pair, index)
    _dbg("Root ant‑select найден")

    _open_dropdown(root, drv)
    _dbg("Dropdown ОТКРЫТ")

    # поиск и клик опции
    end = time.time() + wait_sec
    while time.time() < end:
        for opt in drv.find_elements(By.CSS_SELECTOR, CSS_OPT):
            txt = (opt.get_attribute("title") or opt.text).strip()
            if txt == option_text:
                _dbg(f"Найдена опция «{txt}» – кликаем")
                drv.execute_script("arguments[0].click()", opt)
                # ждём закрытие
                WebDriverWait(drv, 6).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, CSS_DD))
                )
                _dbg("Dropdown ЗАКРЫТ – выбор завершён")
                return
        time.sleep(0.1)

    _dbg(f"ОШИБКА: «{option_text}» не найдено")
    raise AssertionError(f"Опция «{option_text}» не найдена за {wait_sec} с")

@keyword("Searchable Select By Attr")
def searchable_select_by_attr(attr_pair: str,
                              option_text: str,
                              *,
                              index: int | None = None,
                              wait_sec: int = 10):
    root, drv = _select_root(attr_pair, index)
    _open_dropdown(root, drv)
    attr, val = _parse(attr_pair)
    css_repr  = f'css:[{attr}*="{val}"]'
    BuiltIn().log(
        f"Selecting option '{option_text}' in searchable '{css_repr}'", "INFO"
    )
    # 💡 универсальный поиск input
    search = root.find_element(
        By.CSS_SELECTOR,
        "input[role='combobox'], input[type='search'].ant-select-selection-search-input"
    )

    drv.execute_script("arguments[0].value = '';", search)
    search.send_keys(Keys.CONTROL, "a", Keys.DELETE, option_text)

    _click_option(option_text, drv, strict=False, wait=wait_sec)
    
    
@keyword("Wait Until Page Has")
def wait_until_page_has(locator: str,
                        timeout: str = "10 s",
                        error: str | None = None):
    """
    INFO‑лог + оригинальный Wait Until Page Contains Element.

        Wait Until Page Has    xpath://span[.='Report parameters']
    """
    BuiltIn().log(f"Waiting for element '{locator}'", "INFO")
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    sl.wait_until_page_contains_element(locator, timeout, error)
    
    
@keyword("Fill Date By Attr")
def fill_date_by_attr(attr_pair: str,
                      value: str,
                      *,
                      index: int | None = None,
                      timeout: float = 8.0):
    """
    Заполняет одно поле AntD RangePicker, не открывая календарь.

        Fill Date By Attr    placeholder="Start date"    22.07.2024
    """
    # ── locate контейнер ───────────────────────────────────────────
    m = re.match(r'\s*([\w\-:]+)\s*=\s*["\']?([^"\']+)["\']?\s*$', attr_pair)
    if not m:
        raise ValueError('нужно attr="value"')
    attr, val = m.groups()
    loc = f'css:[{attr}*="{val}"]'
    BuiltIn().log(f"Typing date '{value}' into element '{loc}'", "INFO")

    sl  = BuiltIn().get_library_instance("SeleniumLibrary")
    drv = sl.driver

    sl.wait_until_page_contains_element(loc, timeout)
    boxes = sl.get_webelements(loc)
    box   = boxes[index-1] if index else boxes[0]

    # ── клик → ищем скрытый input внутри ───────────────────────────
    box.click()

    hidden = WebDriverWait(drv, 2).until(
        lambda d: box.find_element(By.CSS_SELECTOR, "input[type='text']")
    )

    # ── Ctrl+A Delete + ввод + Enter ───────────────────────────────
    hidden.send_keys(Keys.CONTROL, "a", Keys.DELETE, value, Keys.ENTER)

    # ── ждём, пока value применится ────────────────────────────────
    WebDriverWait(drv, timeout).until(
        lambda d: hidden.get_attribute("value") == value
    )