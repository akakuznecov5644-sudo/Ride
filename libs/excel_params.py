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
import oracledb
from typing import Literal
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
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
from robot.api.deco import library


CSS_DD = ".ant-select-dropdown:not(.ant-select-dropdown-hidden)"
CSS_OPT = f"{CSS_DD} .ant-select-item-option"


_dbg_counter = 0
def _class_token_pred(val: str) -> str:
    # собираем XPath-предикат по токенам класса: ' foo ' внутри нормализованного @class
    tokens = [t for t in (val or "").split() if t]
    return " and ".join(
        [f"contains(concat(' ', normalize-space(@class), ' '), ' {t} ')" for t in tokens]
    ) or "false()"

def _xp_literal(s: str) -> str:
    # безопасная строковая константа для XPath
    if '"' not in s:
        return f'"{s}"'
    if "'" not in s:
        return f"'{s}'"
    parts = s.split('"')
    return "concat(" + ", '\"', ".join([f'"{p}"' for p in parts]) + ")"

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

def _open_filter_auto(value: str, *, index: int | None = None, exact: bool = False, timeout: float = 8.0):
    """
    Открывает иконку фильтра в заголовке колонки.
    Поддержка:
      • Текст заголовка (exact/contains)
      • Пара атрибутов: name="value" (для class — токенный матч)
    Делает обязательный горизонтальный скролл к колонке перед кликом.
    """

    def _drv():
        sl = BuiltIn().get_library_instance("SeleniumLibrary")
        return sl.driver

    def _xp_literal(s: str) -> str:
        if '"' not in s:
            return f'"{s}"'
        if "'" not in s:
            return f"'{s}'"
        parts = s.split('"')
        return "concat(" + ", '\"', ".join([f'"{p}"' for p in parts]) + ")"

    def _class_token_pred(val: str) -> str:
        tokens = [t for t in (val or "").split() if t]
        if not tokens:
            return "false()"
        return " and ".join(
            [f"contains(concat(' ', normalize-space(@class), ' '), ' {t} ')" for t in tokens]
        )

    def _parse_attr_pair(s: str):
        s = (s or "").strip()
        eq = s.find("=")
        if eq < 0:
            return None
        name = s[:eq].strip()
        rest = s[eq+1:].strip()
        if len(rest) >= 2 and rest[0] in ('"', "'") and rest[-1] == rest[0]:
            val = rest[1:-1]
        else:
            val = rest.strip().strip('"').strip("'")
        if not name:
            return None
        return name, val

    def _scroll_horiz_to_header(drv, header_el):
        js = r"""
        (function(th){
          if(!th) return;
          th = th.closest('th') || th;
          var container = th.closest('.ant-table-container');
          if(!container){ th.scrollIntoView({block:'center', inline:'center'}); return; }
          var headerWrap = container.querySelector('.ant-table-header') || container;
          var bodyWrap   = container.querySelector('.ant-table-body') ||
                           container.querySelector('.ant-table-content') ||
                           container.querySelector('.ant-table-body-inner') || container;

          var left = th.offsetLeft - (container.clientWidth/2);
          if (left < 0) left = 0;

          if (headerWrap && headerWrap.scrollLeft !== undefined) headerWrap.scrollLeft = left;
          if (bodyWrap   && bodyWrap.scrollLeft   !== undefined) bodyWrap.scrollLeft   = left;

          // финальный ensure для видимости конкретной иконки
          th.scrollIntoView({block:'center', inline:'center'});
        })(arguments[0]);
        """
        drv.execute_script(js, header_el)

    drv = _drv()

    # 1) Построить XPath для самого TH (заголовка колонки)
    attr_pair = _parse_attr_pair(value)
    if attr_pair:
        attr = attr_pair[0].strip().lower()
        val  = attr_pair[1]
        if attr == "class":
            pred = _class_token_pred(val)
            xp_header = ("//th[contains(@class,'ant-table-cell') or contains(@class,'ant-table-filter-column')]"
                         f"[.//*[{pred}] or {pred}]")
        else:
            lit = _xp_literal(val)
            xp_header = ("//th[contains(@class,'ant-table-cell') or contains(@class,'ant-table-filter-column')]"
                         f"[.//*[contains(@{attr}, {lit})] or contains(@{attr}, {lit})]")
    else:
        txt = value.strip()
        lit = _xp_literal(txt)
        if exact:
            elem_pred = f"(normalize-space(@title)={lit} or normalize-space(.)={lit})"
            all_pred  = f"normalize-space(string(.))={lit}"
        else:
            elem_pred = f"(contains(normalize-space(@title), {lit}) or contains(normalize-space(.), {lit}))"
            all_pred  = f"contains(normalize-space(string(.)), {lit})"
        xp_header = ("//th[contains(@class,'ant-table-cell') or contains(@class,'ant-table-filter-column')]"
                     f"[ .//span[{elem_pred}] or .//div[{elem_pred}] or {all_pred} ]")

    # 2) Дождаться сам заголовок и сделать горизонтальный скролл к нему
    header_el = WebDriverWait(drv, timeout).until(
        EC.presence_of_element_located((By.XPATH, xp_header))
    )
    _scroll_horiz_to_header(drv, header_el)

    # 3) Найти триггер фильтра внутри этого заголовка и кликнуть
    xp_trigger_inside = ".//span[contains(@class,'ant-table-filter-trigger')]"
    trig = WebDriverWait(drv, timeout).until(
        EC.element_to_be_clickable((By.XPATH, f"({xp_header}){xp_trigger_inside}"))
        if not hasattr(header_el, "find_element")
        else EC.element_to_be_clickable(header_el.find_element(By.XPATH, xp_trigger_inside))
    )

    try:
        drv.execute_script("arguments[0].scrollIntoView({block:'center',inline:'center'});", trig)
        trig.click()
    except Exception:
        try:
            ActionChains(drv).move_to_element(header_el).pause(0.05).move_to_element(trig).pause(0.05).perform()
            drv.execute_script("arguments[0].click()", trig)
        except Exception:
            drv.execute_script("arguments[0].click()", trig)

    # 4) Ожидание выпадения меню фильтра
    try:
        _wait_filter_dropdown(drv, timeout)
    except Exception:
        WebDriverWait(drv, timeout).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".ant-dropdown, .ant-popover, .ant-table-filter-dropdown")
            )
        )


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
    #_dbg("scrollIntoView .ant-select")
    time.sleep(0.5)
    drv.execute_script(
        "arguments[0].scrollIntoView({block:'center',inline:'center'});", root
    )

    # ➋ mousedown‑mouseup (ActionChains)
    #_dbg("ActionChains: move_to_element ▸ click (mousedown+mouseup)")
    try:
        ActionChains(drv).move_to_element(root).pause(0.05).click().perform()
    except MoveTargetOutOfBoundsException:
        #_dbg("MoveTargetOutOfBounds → fallback JS‑click по root")
        drv.execute_script("arguments[0].click()", root)

    # ➌ ждём 500 мс появления меню
    try:
        WebDriverWait(drv, 0.5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, CSS_DD))
        )
        #_dbg("Dropdown появился после ActionChains‑клика")
        return
    except TimeoutException:
        pass#_dbg("Dropdown НЕ появился → пробуем Space по скрытому input")

    # ➍ fallback: клавиша Space
    try:
        inp = root.find_element(
            By.CSS_SELECTOR,
            "input[role='combobox'], input[type='search'].ant-select-selection-search-input"
        )
        inp.send_keys(Keys.SPACE)
        #_dbg("Space отправлен, ждём выпадайку")
    except NoSuchElementException:
        #_dbg("Input не найден → JS‑click ещё раз")
        drv.execute_script("arguments[0].click()", root)

    # ➎ финальное ожидание
    WebDriverWait(drv, wait).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, CSS_DD))
    )
    #_dbg("Dropdown окончательно открыт")

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
        "--disable-gpu",
        "--start-maximized"
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
        val_esc = val.replace('"', '\\"')
        locator = f'xpath:(//*[contains(@{attr}, "{val_esc}")])[{index}]'

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


@keyword("Click Switch By Text")
def click_switch_by_text(text: str,
                         timeout: float = 8.0,
                         *,
                         js_fallback: bool = True):
    """
    Кликает по текстовому переключателю (segmented / tabs-like / radio-like),
    который часто используется вместо стандартного ant-select.

    Примеры:
        Click Switch By Text    Fixed Prize
        Click Switch By Text    Progressive
    """
    BuiltIn().log(f"Clicking switch element with text \"{text}\"", "INFO")
    drv = BuiltIn().get_library_instance("SeleniumLibrary").driver

    # Один способ поиска: кликабельный пункт переключателя в модалке по точному тексту.
    xpath = (
        "//div[contains(@class,'ant-modal-container')]"
        "//*[contains(@class,'ant-segmented-item') or contains(@class,'ant-radio-button-wrapper') "
        "or contains(@class,'ant-btn') or @role='button' or self::button or self::label or self::span or self::div]"
        f"[normalize-space(.)='{text}']"
    )

    target = WebDriverWait(drv, timeout).until(
        EC.element_to_be_clickable((By.XPATH, xpath))
    )

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
    Вводит *text* в <input>/<textarea>, найденный по паре атрибутов.
    ▸ attr_pair: строка вида  attr="value"  (напр. id="query_mach_id" или placeholder="Search")
    ▸ text:      вводимое значение
    ▸ timeout:   ожидание элемента
    ▸ clear:     очищать поле перед вводом
    ▸ index:     1-based индекс, если совпадений несколько
    """

    m = re.match(r'\s*([\w\-:]+)\s*=\s*["\']?([^"\']+)["\']?\s*$', attr_pair)
    if not m:
        raise ValueError('строка должна быть вида  attr="value"')
    attr, val = m.groups()

    # Для id используем строгий селектор #id, иначе — подстрочный совпадитель [attr*="val"]
    raw_css = f'#{val}' if attr == 'id' else f'[{attr}*="{val}"]'
    css_repr = f'css:{raw_css}'

    BuiltIn().log(f"Typing text '{text}' into element '{css_repr}'", "INFO")
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    drv = sl.driver

    # Ждем появление+кликабельность
    sl.wait_until_page_contains_element(css_repr, timeout)
    WebDriverWait(drv, timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, raw_css)))

    elems = sl.get_webelements(css_repr)
    if not elems:
        raise AssertionError(f"Элемент не найден: {css_repr}")
    field = elems[index - 1] if index else elems[0]

    # Фокус
    try:
        drv.execute_script("arguments[0].click();", field)
    except Exception:
        pass

    # Очистка при необходимости
    if clear:
        try:
            field.send_keys(Keys.CONTROL, "a")
            field.send_keys(Keys.DELETE)
        except Exception:
            pass

    # Нативная установка значения в контролируемый React-инпут + события
    try:
        drv.execute_script("""
            const el = arguments[0];
            const val = String(arguments[1]);
            const tag = (el.tagName || '').toLowerCase();
            const proto = tag === 'textarea' ? HTMLTextAreaElement.prototype
                                             : HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new InputEvent('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
        """, field, str(text))
    except Exception as e:
        BuiltIn().log(f"[Fill By Attr] JS set failed: {e}", "WARN")

    # Принудительный blur (часто нужен для AntD, чтобы закоммитить state)
    try:
        drv.execute_script("arguments[0].blur && arguments[0].blur();", field)
    except Exception:
        pass

    # Верификация установленного значения с небольшим ожиданием
    end = time.time() + max(0.5, min(2.0, timeout))
    ok = False
    exp = str(text).strip()
    while time.time() < end:
        try:
            cur = (field.get_attribute("value") or "").strip()
            if cur == exp:
                ok = True
                break
        except Exception:
            pass
        time.sleep(0.1)

    # Фолбэк: печатаем «по-старинке» и снова шлём change (если вдруг React не схватил)
    if not ok:
        try:
            drv.execute_script("arguments[0].click();", field)
            field.send_keys(Keys.CONTROL, "a")
            field.send_keys(Keys.DELETE)
            field.send_keys(str(text))
            drv.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles:true}))", field)
            drv.execute_script("arguments[0].blur && arguments[0].blur();", field)
            ok = ((field.get_attribute("value") or "").strip() == exp)
        except Exception as e:
            BuiltIn().log(f"[Fill By Attr] fallback failed: {e}", "WARN")

    BuiltIn().log(f"[Fill By Attr] {'OK' if ok else 'NOT SET'} {attr_pair} -> \"{text}\"", "INFO")



# ────────────────────────────────────────────────────────────────────
@keyword("Select By Attr")
def select_by_attr(attr_pair: str,
                   option_text: str,
                   *,
                   index: int | None = None,
                   wait_sec: int = 6):
    #_dbg(f"START Select By Attr → {attr_pair=} {option_text=}")

    root, drv = _select_root(attr_pair, index)
    #_dbg("Root ant‑select найден")

    _open_dropdown(root, drv)
#_dbg("Dropdown ОТКРЫТ")

    # поиск и клик опции
    end = time.time() + wait_sec
    while time.time() < end:
        for opt in drv.find_elements(By.CSS_SELECTOR, CSS_OPT):
            txt = (opt.get_attribute("title") or opt.text).strip()
            if txt == option_text:
                #_dbg(f"Найдена опция «{txt}» – кликаем")
                drv.execute_script("arguments[0].click()", opt)
                # ждём закрытие
                WebDriverWait(drv, 6).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, CSS_DD))
                )
                #_dbg("Dropdown ЗАКРЫТ – выбор завершён")
                return
        time.sleep(0.1)

    #_dbg(f"ОШИБКА: «{option_text}» не найдено")
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
                        timeout: str = "20 s",
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
                      date_text: str,
                      *,
                      index: int | None = None,
                      timeout: float = 8.0,
                      press_enter: bool = True):
    drv = _drv()
    a, v = _parse_attr(attr_pair)

    # 1) если открыт фильтр — целимся только в него (как было)
    dd = _last_visible_filter(drv)
    if dd:
        xp = f".//input[not(@type='hidden') and not(@readonly) and contains(@{a}, \"{v}\")]"
        try:
            field = WebDriverWait(dd, timeout).until(
                EC.visibility_of_element_located((By.XPATH, xp))
            )
        except Exception:
            field = WebDriverWait(dd, timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ".ant-picker .ant-picker-input input:not([type='hidden'])"))
            )
    else:
        # 2) режим «по странице», но сначала сузим область до видимого drawer, если он есть
        try:
            scope = WebDriverWait(drv, 0.6).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "div.ant-drawer-content-wrapper"))
            )
        except Exception:
            scope = drv

        css = f'[{a}*="{v}"]'

        def _visible_inputs(root):
            try:
                elems = root.find_elements(By.CSS_SELECTOR, css)
            except Exception:
                elems = []
            return [e for e in elems if e.is_displayed()]

        # Ждём хотя бы ОДИН видимый инпут по заданному атрибуту внутри scope
        WebDriverWait(drv, timeout).until(lambda d: _visible_inputs(scope))
        elems = _visible_inputs(scope)

        # index = 1-based, как и раньше
        el = elems[(index - 1) if index else 0]
        field = el if el.tag_name.lower() == "input" else el.find_element(
            By.CSS_SELECTOR, "input:not([type='hidden'])"
        )

    # 3) ввод значения
    field.click()
    field.send_keys(Keys.CONTROL, "a")
    field.send_keys(Keys.DELETE)
    field.send_keys(date_text)
    if press_enter:
        field.send_keys(Keys.ENTER)



def _scroll_to_header(title_or_attr: str, *, exact: bool, index: int | None, timeout: float):
    drv = BuiltIn().get_library_instance("SeleniumLibrary").driver
    bi = BuiltIn()

    def _class_token_pred(val: str) -> str:
        tokens = [t for t in val.split() if t]
        preds = [f"contains(concat(' ', normalize-space(@class), ' '), ' {t} ')" for t in tokens]
        return " and ".join(preds) if preds else "false()"

    q = (title_or_attr or "").strip()
    is_attr = ("=" in q)

    if is_attr:
        a, v = q.split("=", 1)
        a = a.strip()
        v = v.strip().strip('"').strip("'")
        if a.lower() == "class":
            pred = _class_token_pred(v)
        else:
            v_esc = v.replace('"', '\\"')
            pred = f'contains(@{a}, "{v_esc}")'
        header_xp = f"//div[contains(@class,'ant-table')]//thead//th[contains(@class,'ant-table-cell')][.//*[{pred}] or {pred}]"
        any_xp    = f"//div[contains(@class,'ant-table')]//*[self::th or self::td or self::span or self::div][{pred}]"
    else:
        t = q.replace('"','\\"')
        text_pred = f'normalize-space(.)=\"{t}\"' if exact else f'contains(normalize-space(.), \"{t}\")'
        header_xp = f"//div[contains(@class,'ant-table')]//thead//th[contains(@class,'ant-table-cell')]//*[self::span or self::div][{text_pred}]"
        any_xp    = f"//div[contains(@class,'ant-table')]//*[self::th or self::td or self::span or self::div][{text_pred}]"

    if index:
        header_xp = f"({header_xp})[{int(index)}]"
        any_xp    = f"({any_xp})[{int(index)}]"

    try:
        el = WebDriverWait(drv, timeout).until(EC.presence_of_element_located((By.XPATH, header_xp)))
    except Exception:
        el = WebDriverWait(drv, timeout).until(EC.presence_of_element_located((By.XPATH, any_xp)))

    # целимся в ближайший <th>, если он есть
    try:
        th = el.find_element(By.XPATH, "self::th|ancestor::th[1]")
    except Exception:
        th = el

    # собираем текстовые кандидаты
    cand = [
        (th.text or "").strip(),
        (th.get_attribute("title") or "").strip(),
        (th.get_attribute("aria-label") or "").strip(),
        (th.get_attribute("data-title") or "").strip(),
    ]
    if not any(cand):
        try:
            desc = th.find_element(By.XPATH, ".//*[normalize-space(text())!=''][1]")
            cand.append((desc.text or "").strip())
        except Exception:
            pass

    anchor = next((c for c in cand if c), "")

    if not anchor:
        # если вообще ничего не нашли — не мешаем дальнейшей логике
        return

    # дергаем готовый кейворд скролла (сигнатура может быть разной — пробуем безопасно)
    try:
        bi.run_keyword("Scroll X By Text", anchor)
    except Exception:
        # если у тебя вариант с точным совпадением/индексом — раскомментируй подходящую строку
        # bi.run_keyword("Scroll X By Text", anchor, exact)
        # bi.run_keyword("Scroll X By Text", anchor, exact, index or 1)
        bi.run_keyword("Scroll X By Text", anchor)


@keyword("Open Text Filter")
def open_text_filter(title: str,
                     *,
                     index: int | None = None,
                     exact: bool = False,
                     timeout: float = 8.0):
    _scroll_to_header(title, exact=exact, index=index, timeout=timeout)
    _open_filter_auto(title, index=index, exact=exact, timeout=timeout)

@keyword("Open Multiselect Filter")
def open_multiselect_filter(title: str,
                            *,
                            index: int | None = None,
                            exact: bool = False,
                            timeout: float = 8.0):
    _scroll_to_header(title, exact=exact, index=index, timeout=timeout)
    _open_filter_auto(title, index=index, exact=exact, timeout=timeout)

@keyword("Open Date Filter")
def open_date_filter(title: str,
                     *,
                     index: int | None = None,
                     exact: bool = False,
                     timeout: float = 8.0):
    _scroll_to_header(title, exact=exact, index=index, timeout=timeout)
    _open_filter_auto(title, index=index, exact=exact, timeout=timeout)

@keyword("Open DateTime Filter")
def open_datetime_filter(title_or_attr: str, *, index: int | None = None, exact: bool = False, timeout: float = 8.0):
    val = (title_or_attr or "").strip()
    if ("=" in val) and (("'" in val) or ('"' in val)):
        open_filter_by_attr(val, index=index, timeout=timeout)
        return
    # режим по заголовку (как было)
    drv = _drv()
    safe = val.replace('"', '\\"')
    pred = f'normalize-space(.)="{safe}"' if exact else f'contains(normalize-space(.), "{safe}")'
    xp = ("//th[contains(@class,'ant-table-cell')]"
          "[.//span[contains(@class,'ant-table-column-title')]"
          f"//*[self::span or self::div][{pred}]]"
          "//span[contains(@class,'ant-table-filter-trigger')]")
    if index:
        xp = f"({xp})[{int(index)}]"
    trig = WebDriverWait(drv, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
    drv.execute_script("arguments[0].scrollIntoView({block:'center',inline:'center'});", trig)
    drv.execute_script("arguments[0].click()", trig)
    _wait_filter_dropdown(drv, timeout)

@keyword("Open Numeric Filter")
def open_numeric_filter(title: str,
                        *,
                        index: int | None = None,
                        exact: bool = False,
                        timeout: float = 8.0):
    _scroll_to_header(title, exact=exact, index=index, timeout=timeout)
    _open_filter_auto(title, index=index, exact=exact, timeout=timeout)

@keyword("Step Screenshot")
def step_screenshot(message: str = "manual"):
    """
    Делает отладочный скриншот в стиле Fill Date By Attr:
    пишет INFO-лог и сохраняет PNG в папку sel_log с порядковым номером.
        Пример:
            Step Screenshot    перед вводом даты
    """
    _dbg(f"SNAPSHOT: {message}")


@keyword("Click By Text On Filter")
def click_by_text_on_filter(
    text: str,
    timeout: float = 6.0,
    *,
    index: int | None = None,
    exact: bool = False,
    js_fallback: bool = True,
    ):
    """
    Находит элемент с указанным текстом на странице, поднимается по DOM до родительского div фильтра
    и проверяет отсутствие класса "ant-dropdown-hidden". Если фильтр открыт, кликает по элементу.

    Пример:
        Click By Text On Filter    Reset
    """
    BuiltIn().log(f"Clicking element with text \"{text}\" inside the open filter", "INFO")

    sl, drv = (
        BuiltIn().get_library_instance("SeleniumLibrary"),
        BuiltIn().get_library_instance("SeleniumLibrary").driver,
    )

    # Ждем появления dropdown фильтра (предполагаем, что он уже открыт)
    WebDriverWait(drv, timeout).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, ".ant-dropdown:not(.ant-dropdown-hidden)"))
    )

    # Escape text for JS
    text_js = json.dumps(text)

    cond = f"elText === {text_js}" if exact else f"elText.indexOf({text_js}) !== -1"

    script = f"""
    var dropdown = document.querySelector('.ant-dropdown:not(.ant-dropdown-hidden)');
    if (dropdown) {{
        var elements = dropdown.querySelectorAll('button, a, input, li, label');
        var matching = [];
        for (var el of elements) {{
            var elText = (el.textContent || el.innerText || '').trim().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
            if ({cond}) {{
                matching.push(el);
            }}
        }}
        return matching;
    }}
    return [];
    """

    matching = drv.execute_script(script)

    if not matching:
        raise AssertionError(f"Элемент с текстом '{text}' не найден в открытом фильтре")

    if index:
        if index < 1 or index > len(matching):
            raise IndexError("Индекс вне диапазона")
        target = matching[index - 1]
    else:
        target = matching[0]

    # Клик
    try:
        target.click()
    except Exception:
        if not js_fallback:
            raise
        drv.execute_script(
            "arguments[0].scrollIntoView({block:'center',inline:'center'});", target
        )
        drv.execute_script("arguments[0].click();", target)


@keyword("Fill Text On Filter")
def fill_text_on_filter(
    text: str,
    timeout: float = 6.0,
    *,
    clear: bool = True,
    press_enter: bool = True,
    js_fallback: bool = True,
):
    BuiltIn().log(f'Filling text "{text}" into the input inside the open filter', "INFO")
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    drv = sl.driver

    # ждём ВИДИМЫЙ дропдаун фильтра
    WebDriverWait(drv, timeout).until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, ".ant-dropdown:not(.ant-dropdown-hidden) .ant-table-filter-dropdown")
        )
    )

    # 1) numeric сначала, если есть
    xp_num = (
        "//div[contains(@class,'ant-dropdown') and not(contains(@class,'ant-dropdown-hidden'))]"
        "//div[contains(@class,'ant-table-filter-dropdown')]"
        "//input[@inputmode='numeric' and not(@readonly)]"
    )
    # 2) иначе обычный input, НО не hidden/readonly и НЕ внутри ant-select (оператора)
    xp_txt = (
        "//div[contains(@class,'ant-dropdown') and not(contains(@class,'ant-dropdown-hidden'))]"
        "//div[contains(@class,'ant-table-filter-dropdown')]"
        "//input[not(@type='hidden') and not(@readonly) and "
        "      not(ancestor::*[contains(@class,'ant-select')])]"
    )

    try:
        field = WebDriverWait(drv, 1.0).until(EC.element_to_be_clickable((By.XPATH, xp_num)))
    except Exception:
        field = WebDriverWait(drv, timeout).until(EC.element_to_be_clickable((By.XPATH, xp_txt)))

    # ввод
    try:
        field.click()
        if clear:
            field.send_keys(Keys.CONTROL, "a", Keys.DELETE)
        field.send_keys(text)
        if press_enter:
            field.send_keys(Keys.ENTER)
    except Exception:
        if not js_fallback:
            raise
        drv.execute_script("arguments[0].scrollIntoView({block:'center',inline:'center'});", field)
        if clear:
            drv.execute_script("arguments[0].value='';", field)
        drv.execute_script("arguments[0].value = arguments[1];", field, text)
        drv.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles:true}));", field)
        if press_enter:
            drv.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key:'Enter',bubbles:true}))", field)


@keyword("Fill Date On Filter")
def fill_date_on_filter(date_text: str, timeout: float = 6.0, *, js_fallback: bool = True):
    BuiltIn().log(f'Filling date "{date_text}" into the date input inside the open filter', "INFO")
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    drv = sl.driver

    # ждём открытый фильтр
    WebDriverWait(drv, timeout).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, ".ant-dropdown:not(.ant-dropdown-hidden)"))
    )

    # правильный локатор: берем input внутри ant-picker(/ant-picker-input), но не hidden
    xpath = (
        "//div[contains(@class,'ant-dropdown') and not(contains(@class,'ant-dropdown-hidden'))]"
        "//div[contains(@class,'ant-table-filter-dropdown')]"
        "//div[contains(@class,'ant-picker')]//input[not(@type='hidden')]"
    )
    target = WebDriverWait(drv, timeout).until(
        EC.visibility_of_element_located((By.XPATH, xpath))
    )

    # ввод
    try:
        target.click()
        target.send_keys(Keys.CONTROL, "a", Keys.DELETE, date_text, Keys.ENTER)
    except Exception:
        if not js_fallback:
            raise
        drv.execute_script("arguments[0].scrollIntoView({block:'center',inline:'center'});", target)
        drv.execute_script("arguments[0].focus();", target)
        drv.execute_script("arguments[0].value = arguments[1];", target, date_text)
        drv.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles:true}));", target)
        drv.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key:'Enter'}));", target)

    # мягкая валидация: сравнение по цифрам (без разделителей), чтобы пережить форматирование AntD
    import re as _re
    expect_digits = _re.sub(r"\D", "", date_text or "")
    def _ok():
        v = (target.get_attribute("value") or "")
        got_digits = _re.sub(r"\D", "", v)
        return got_digits.startswith(expect_digits) or got_digits.endswith(expect_digits)

    WebDriverWait(drv, timeout).until(lambda d: _ok())


@keyword("Click By Attr On Filter")
def click_by_attr_on_filter(
    attr_pair: str,
    timeout: float = 6.0,
    *,
    index: int | None = None,
    js_fallback: bool = True,
    ):
    """
    Нажимает на элемент внутри уже открытого фильтра, чей атрибут *содержит* указанную подстроку.

    ▸ attr_pair  – строка вида  attr="value"  (кавычки любые).
      Пример:  aria-label="check-circle"
    ▸ timeout    – ожидание появления (сек).
    ▸ index      – номер совпадения, если элементов несколько (1‑based).
    ▸ js_fallback – при обычном WebDriver‑клике ловим ошибку и повторяем
      JavaScript‑кликом (полезно, если элемент перекрыт маской).

    Использование в Robot Framework:

        Click By Attr On Filter    aria-label="check-circle"
    """
    BuiltIn().log(f"Clicking element with attr \"{attr_pair}\" inside the open filter", "INFO")

    # ➊ разбираем пару attr="value"
    m = re.match(r'\s*([\w\-:]+)\s*=\s*["\']?([^"\']+)["\']?\s*$', attr_pair)
    if not m:
        raise ValueError('Ожидается строка вида attr="value"')
    attr, val = m.group(1), m.group(2)

    safe = val.replace('"', '\\"')

    sl, drv = (
        BuiltIn().get_library_instance("SeleniumLibrary"),
        BuiltIn().get_library_instance("SeleniumLibrary").driver,
    )

    # Ждем появления dropdown фильтра
    WebDriverWait(drv, timeout).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, ".ant-dropdown:not(.ant-dropdown-hidden)"))
    )

    # XPath для поиска элемента с атрибутом внутри видимого ant-dropdown
    xpath = (
        f"//div[contains(@class,'ant-dropdown') and not(contains(@class,'ant-dropdown-hidden'))]//"
        f"*[contains(@{attr}, \"{safe}\")]"
    )

    if index:
        xpath = f"({xpath})[{index}]"

    locator = (By.XPATH, xpath)

    # Ждём кликабельность
    target = WebDriverWait(drv, timeout).until(
        EC.element_to_be_clickable(locator)
    )

    # Клик
    try:
        target.click()
    except Exception:
        if not js_fallback:
            raise
        drv.execute_script(
            "arguments[0].scrollIntoView({block:'center',inline:'center'});", target
        )
        drv.execute_script("arguments[0].click();", target)


def _drv():
    return BuiltIn().get_library_instance("SeleniumLibrary").driver

def _scroll_root_js():
    return "return document.scrollingElement || document.documentElement || document.body;"

def _visible(el):
    try:
        return el.is_displayed()
    except Exception:
        return False

def _parse_attr(pair: str):
    a, v = pair.split("=", 1)
    return a.strip(), v.strip().strip('"').strip("'")

def _last_visible_filter(drv, timeout: float = 0.5):
    try:
        dds = [e for e in drv.find_elements(By.CSS_SELECTOR, "div.ant-dropdown") if e.is_displayed()]
        for dd in reversed(dds):
            if dd.find_elements(By.CSS_SELECTOR, ".ant-table-filter-dropdown"):
                return dd
    except Exception:
        pass
    return None

@keyword("Scroll X Page By")
def scroll_x_page_by(px: int):
    drv = _drv()
    BuiltIn().log(f"Scroll X Page By {px}", "INFO")
    drv.execute_script("""
        const el = document.scrollingElement || document.documentElement || document.body;
        el.scrollLeft = (el.scrollLeft || 0) + arguments[0];
    """, int(px))

@keyword("Scroll X Page To")
def scroll_x_page_to(pos: str):
    drv = _drv()
    pos = (pos or "").strip().lower()
    BuiltIn().log(f"Scroll X Page To {pos}", "INFO")
    drv.execute_script("""
        const el = document.scrollingElement || document.documentElement || document.body;
        if (arguments[0]==='left')   el.scrollLeft = 0;
        else if (arguments[0]==='right')  el.scrollLeft = el.scrollWidth;
        else if (arguments[0]==='center') el.scrollLeft = Math.max(0, (el.scrollWidth - el.clientWidth)/2);
        else el.scrollLeft = (el.scrollLeft || 0);
    """, pos)

def _parse(attr_pair: str):
    # если у тебя уже есть _parse(attr_pair) — используй его и удали этот мини-парсер
    a, v = attr_pair.split("=", 1)
    return a.strip(), v.strip().strip('"').strip("'")

@keyword("Scroll X By Attr")
def scroll_x_by_attr(attr_pair: str,
                     by: int | None = None,
                     to: str | None = None,
                     *,
                     index: int | None = None,
                     timeout: float = 8.0):
    """
    Скроллит горизонтально контейнер, найденный по attr="value_part".
    Примеры:
      Scroll X By Attr    class="ant-table-body"    by=400
      Scroll X By Attr    class="ant-table-body"    to=right
    """
    drv = _drv()
    a, v = _parse(attr_pair)
    css = f'[{a}*="{v}"]'

    # ждём контейнер и берём по index (1-based)
    WebDriverWait(drv, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))
    elems = drv.find_elements(By.CSS_SELECTOR, css)
    if not elems:
        raise AssertionError(f"Element not found by {css}")
    el = elems[(index-1) if index else 0]

    if to:
        to = to.strip().lower()
        BuiltIn().log(f'Scroll X By Attr {a}*="{v}" → to={to}', "INFO")
        drv.execute_script("""
            const el = arguments[0];
            if (arguments[1]==='left')   el.scrollLeft = 0;
            else if (arguments[1]==='right')  el.scrollLeft = el.scrollWidth;
            else if (arguments[1]==='center') el.scrollLeft = Math.max(0, (el.scrollWidth - el.clientWidth)/2);
        """, el, to)
    else:
        delta = int(by if by is not None else 300)
        BuiltIn().log(f'Scroll X By Attr {a}*="{v}" → by={delta}', "INFO")
        drv.execute_script("arguments[0].scrollLeft = (arguments[0].scrollLeft||0) + arguments[1];", el, delta)

@keyword("Scroll X By Text")
def scroll_x_by_text(text: str,
                     to: str = "center",
                     *,
                     exact: bool = False,
                     index: int = 1,
                     timeout: float = 8.0,
                     container_attr: str | None = None):
    """
    Без JS. Горизонтально скроллит контейнер до ячейки с текстом и выравнивает по to=left|center|right.
    """
    drv = _drv()

    # 1) целевая ячейка
    safe = (text or "").replace('"', '\\"')
    pred = f'normalize-space(.)="{safe}"' if exact else f'contains(normalize-space(.), "{safe}")'
    xp = f"(//table//*[self::td or self::th or self::span or self::div][{pred}])[{int(index)}]"
    cell = WebDriverWait(drv, timeout).until(EC.presence_of_element_located((By.XPATH, xp)))

    # 2) контейнер
    if container_attr:
        a, v = _parse_attr(container_attr)
        css = f'[{a}*="{v}"]'
        cont = WebDriverWait(drv, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))
    else:
        try:
            cont = cell.find_element(By.XPATH, "ancestor::*[contains(@class,'ant-table-body')][1]")
        except Exception:
            cont = drv.find_element(By.TAG_NAME, "body")

    origin = ScrollOrigin.from_element(cont)
    chains = ActionChains(drv)
    to = (to or "center").lower()

    # 3) функции измерения «ошибки» (в пикселях экрана)
    def _diff():
        cr, wr = cell.rect, cont.rect
        if to == "left":
            return (cr['x'] - wr['x']) - 8
        if to == "right":
            return (cr['x'] + cr['width']) - (wr['x'] + wr['width']) + 8
        return (cr['x'] + cr['width']/2) - (wr['x'] + wr['width']/2)  # center

    # 4) адаптивные шаги от ширины контейнера
    w = max(200, int(cont.rect.get("width", 800)))
    STEP_MAX   = int(max(40, min(w * 0.50, 600)))  # большой шаг
    STEP_MID   = int(max(20, min(w * 0.25, 300)))  # средний
    STEP_MICRO = 10                                 # микрошаг возле цели
    DEADZONE   = 4                                  # считаем, что попали

    last = None
    for _ in range(24):  # защита от вечного цикла
        d = _diff()
        if abs(d) <= DEADZONE:
            break

        # выбор шага без перелётов
        if abs(d) > w * 0.50:
            dx = STEP_MAX if d > 0 else -STEP_MAX
        elif abs(d) > w * 0.15:
            dx = STEP_MID if d > 0 else -STEP_MID
        else:
            # аккуратная подводка
            dx = int(d) if abs(d) < STEP_MID else (STEP_MICRO if d > 0 else -STEP_MICRO)

        chains.scroll_from_origin(origin, int(dx), 0).pause(0.03).perform()

        # демпфер: если стало хуже (|d| не уменьшился), уменьшаем шаг
        new_d = _diff()
        if last is not None and abs(new_d) >= abs(d):
            tiny = int(max(3, min(STEP_MICRO, abs(d)/2)))
            fix = tiny if d > 0 else -tiny
            chains.scroll_from_origin(origin, int(fix), 0).pause(0.02).perform()
        last = new_d


@keyword("Open Filter By Attr")
def open_filter_by_attr(attr_pair: str, index: int | None = None, timeout: float = 8.0):
    """
    Открывает фильтр по паре атрибутов:  name="value"
    Спецкейс: name == class → токенный матч (' foo ' внутри @class),
    чтобы class=" TICKET_IN" не совпадал с PROMO_TICKET_IN.
    """
    import re

    def _drv():
        sl = BuiltIn().get_library_instance("SeleniumLibrary")
        return sl.driver

    def _xp_literal(s: str) -> str:
        if '"' not in s:
            return f'"{s}"'
        if "'" not in s:
            return f"'{s}'"
        parts = s.split('"')
        return "concat(" + ", '\"', ".join([f'"{p}"' for p in parts]) + ")"

    def _class_token_pred(val: str) -> str:
        tokens = [t for t in (val or "").split() if t]
        if not tokens:
            return "false()"
        return " and ".join(
            [f"contains(concat(' ', normalize-space(@class), ' '), ' {t} ')" for t in tokens]
        )

    m = re.match(r'^\s*([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*([\'"])(.*?)\2\s*$', attr_pair)
    if not m:
        raise AssertionError(f'Ожидалась строка формата name="value", получено: {attr_pair!r}')

    attr = m.group(1).strip().lower()
    val  = m.group(3)

    if attr == "class":
        pred = _class_token_pred(val)
    else:
        lit  = _xp_literal(val)
        pred = f"contains(@{attr}, {lit})"

    xp_header = (
        "//th[contains(@class,'ant-table-cell') or contains(@class,'ant-table-filter-column')]"
        f"[.//*[{pred}] or {pred}]"
    )
    xp_trigger = f"{xp_header}//span[contains(@class,'ant-table-filter-trigger')]"
    if index:
        xp_trigger = f"({xp_trigger})[{int(index)}]"

    drv = _drv()
    trig = WebDriverWait(drv, timeout).until(EC.element_to_be_clickable((By.XPATH, xp_trigger)))

    drv.execute_script("arguments[0].scrollIntoView({block:'center',inline:'center'});", trig)
    try:
        trig.click()
    except Exception:
        try:
            ActionChains(drv).move_to_element(trig).pause(0.05).perform()
            drv.execute_script("arguments[0].click()", trig)
        except Exception:
            drv.execute_script("arguments[0].click()", trig)

    try:
        _wait_filter_dropdown(drv, timeout)
    except Exception:
        WebDriverWait(drv, timeout).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".ant-dropdown, .ant-popover, .ant-table-filter-dropdown")
            )
        )




# ─────────────────────────── Главный кейворд ───────────────────────────

@keyword("Check Report Filters")
def check_report_filters(
    report_id: int | str,
    *flags,
    start_date: str | None = None,
    end_date: str | None = None,
    single_date: str | None = None,
    location: str | None = None,
    flags_to_check=None,
    params_extra=None,
    params_max_attempts: int = 3,
    params_retry_delay: float = 1.0,
    row_index: int = 1,
    max_columns: int | Literal["all"] | None = None,
    timeout: float = 20.0,
    open_order: str = "text,numeric,datetime,multiselect",
    allow_fallback_clicks: bool = False,
    console_check_kw: str | None = None,
    console_check_args=None,
    network_check_kw: str | None = None,
    network_check_args=None,
    checks_when: str = "after_params,per_column,final",
    fail_on_check: bool = True,
    **kwargs
):
    bi = BuiltIn()

    # ── нормализация ───────────────────────────────────────────────────────────
    _norm = lambda s: str(s).lower().replace("_", "").replace("-", "").replace(" ", "")
    flag_tokens = [_norm(t) for t in flags if str(t).strip()]
    open_params_flag = any(t in ("reportparameters",) for t in flag_tokens)

    flags_list = _to_list(flags_to_check)
    params_max_attempts = _to_int(params_max_attempts, 3)
    params_retry_delay = _to_float(params_retry_delay, 1.0)
    row_index = _to_int(row_index, 1)
    max_columns = _to_max_columns(max_columns)
    timeout = _to_float(timeout, 20.0)
    order_list = _normalize_open_order(open_order)
    checks_when_set = _normalize_checks_when(checks_when)
    _console_args = _to_list(console_check_args)
    _network_args = _to_list(network_check_args)
    wants_params = bool(open_params_flag)

    # ── сбор всех params_extra*, поддержка ; и переводов строк ────────────────
    def _split_specs(s: str) -> list[str]:
        if not isinstance(s, str):
            return []
        out, buf, q = [], [], None
        for ch in s:
            if q:
                if ch == q:
                    q = None
                buf.append(ch)
            else:
                if ch in "\"'":
                    q = ch
                    buf.append(ch)
                elif ch in ";\n":
                    item = "".join(buf).strip()
                    if item:
                        out.append(item)
                    buf = []
                else:
                    buf.append(ch)
        item = "".join(buf).strip()
        if item:
            out.append(item)
        return out

    merged_extras: list[str] = []
    if params_extra:
        merged_extras += _split_specs(params_extra) if isinstance(params_extra, str) else list(params_extra)
    for _k, _v in kwargs.items():
        if _k.startswith("params_extra") and _k != "params_extra" and _v:
            if isinstance(_v, str):
                merged_extras += _split_specs(_v)
            elif isinstance(_v, (list, tuple)):
                merged_extras += list(_v)

    _log(f"Open report: {report_id}")
    bi.run_keyword("Login")
    bi.run_keyword("Open Url", f"/report/page/{report_id}")

    if "before_params" in checks_when_set:
        _maybe_run_check(console_check_kw, _console_args, fail_on_check, "before_params")
        _maybe_run_check(network_check_kw, _network_args, fail_on_check, "before_params")

    _log(
        f"Params -> location={'<skip>' if not location else location}, "
        f"start_date={'<skip>' if not start_date else start_date}, "
        f"end_date={'<skip>' if not end_date else end_date}, "
        f"single_date={'<skip>' if not single_date else single_date}, "
        f"flags={flags_list if flags_list else '<skip>'}, "
        f"report_parameters_flag={'ON' if open_params_flag else 'OFF'}"
    )
    if (location or start_date or end_date or single_date) and not wants_params:
        _log("[PARAMS] values provided but report_parameters flag is OFF — values will be ignored", level="WARN")
    _log(f"Columns limit: {'ALL' if max_columns is None else max_columns}")

    # ── report parameters (строго по флагу) ───────────────────────────────────
    if wants_params:
        _apply_params_with_retry(
            location=location,
            start_date=start_date,
            end_date=end_date,
            single_date=single_date,
            flags_to_check=flags_list,
            max_attempts=params_max_attempts,
            retry_delay=params_retry_delay,
            timeout=timeout,
            params_extra=merged_extras or None,
        )
    else:
        _log("[PARAMS] skipped — explicit flag not passed; do not open Report parameters")
        if _wait_table_rows_safe(timeout=timeout):
            _log("[PARAMS] table appeared without opening params")
        else:
            _log("[PARAMS] table did not appear", level="WARN")

    if "after_params" in checks_when_set:
        _maybe_run_check(console_check_kw, _console_args, fail_on_check, "after_params")
        _maybe_run_check(network_check_kw, _network_args, fail_on_check, "after_params")

    # ── Колонки и фильтры ─────────────────────────────────────────────────────
    _wait_table_rows(timeout=timeout)

    # открыть фильтры в указанном порядке
    _open_filters_by_order(order_list, allow_fallback_clicks=allow_fallback_clicks, timeout=timeout)

    if "per_column" in checks_when_set:
        _maybe_run_check(console_check_kw, _console_args, fail_on_check, "per_column")
        _maybe_run_check(network_check_kw, _network_args, fail_on_check, "per_column")

    # собрать заголовки
    headers = _get_table_headers()
    if not headers:
        raise AssertionError("Table headers not found")

    processed = 0
    sorter_clicked = False
    for th in headers:
        if max_columns is not None and processed >= max_columns:
            break

        anchor = _header_anchor_text(th)
        if not anchor:
            continue

        col_idx = _header_colindex(th)
        _log(f"[COLUMN] {anchor} (index {col_idx}) — start")

        # 🔎 НОВОЕ: проверка ПРИСУТСТВИЯ триггера фильтра в заголовке (без учета видимости)
        trigger = _find_header_filter_control(th)
        if trigger is None:
            _log(f"[COLUMN] {anchor} — no filter control", level="WARN")
            continue

        # открыть дропдаун
        try:
            _open_header_filter_dropdown(th, timeout=timeout)
        except Exception as e:
            _log(f"[COLUMN] {anchor} — cannot open filter dropdown: {type(e).__name__}: {e}", level="WARN")
            continue

        # подтип фильтра (по DOM)
        ftype = _resolve_filter_type()
        _log(f"[COLUMN] {anchor} — filter type: {ftype}")

        # общий smoke для UI + минимальный интеракшн (внутри _smoke_filter_ui)
        try:
            _smoke_filter_ui(anchor, ftype, row_index=row_index)

            if not sorter_clicked:
                if _click_header_sorter_multiple_times(th, anchor, times=4, timeout=timeout):
                    sorter_clicked = True
                else:
                    _log(f"[COLUMN] {anchor} — sorter control not available", level="DEBUG")
        except Exception as e:
            _log(f"[COLUMN] {anchor} — filter smoke failed: {type(e).__name__}: {e}", level="WARN")
        finally:
            _clear_all_filters_if_present()

        processed += 1
        _log(f"[COLUMN] {anchor} — done")

    # ── финальные проверки ────────────────────────────────────────────────────
    if "final" in checks_when_set:
        _maybe_run_check(console_check_kw, _console_args, fail_on_check, "final")
        _maybe_run_check(network_check_kw, _network_args, fail_on_check, "final")





# ─────────────────────────── Report parameters ───────────────────────────
@keyword("Assert Console Has No Errors")
def assert_console_has_no_errors(forbidden_levels: str = "SEVERE,ERROR", ignore_substrings: str = ""):
    """
    Проваливает тест, если в консоли браузера есть сообщения заданных уровней.
    forbidden_levels: строка уровней через запятую (напр. "SEVERE,ERROR,WARNING")
    ignore_substrings: игнорировать сообщения, если содержат любую из подстрок (через запятую)
    """
    bi = BuiltIn()
    drv = bi.get_library_instance("SeleniumLibrary").driver

    def _to_list(s):
        if s is None: return []
        return [p.strip() for p in str(s).replace(";", ",").split(",") if p.strip()]

    levels = {lvl.upper() for lvl in _to_list(forbidden_levels)}
    ignores = _to_list(ignore_substrings)

    try:
        entries = drv.get_log("browser")
    except Exception as e:
        bi.log(f"[CHECK][console] browser logs unavailable: {type(e).__name__}: {e}", level="WARN")
        return

    bad = []
    for e in entries:
        level = (e.get("level") or "").upper()
        msg = e.get("message") or ""
        if levels and level not in levels:
            continue
        if any(ig in msg for ig in ignores):
            continue
        bad.append(f"{level}: {msg}")

    if bad:
        bi.log("[CHECK][console] failures:\n" + "\n".join(bad[:50]), level="ERROR")
        raise AssertionError(f"Console has {len(bad)} error(s) at levels {sorted(levels)}")
    else:
        bi.log("[CHECK][console] no forbidden console messages", level="INFO")


@keyword("Assert No Failed Requests")
def assert_no_failed_requests(min_status: int | str = 400, ignore_substrings: str = ""):
    """
    Проваливает тест, если есть сетевые ответы со статусом >= min_status.
    min_status: число или строка вида 'status>=400'
    ignore_substrings: игнорировать URL, если содержит любую из подстрок (через запятую)
    """
    bi = BuiltIn()
    drv = bi.get_library_instance("SeleniumLibrary").driver

    # парсим статус из строки 'status>=XXX' или просто 'XXX'
    try:
        m = re.search(r"(\d+)", str(min_status))
        threshold = int(m.group(1)) if m else 400
    except Exception:
        threshold = 400

    def _to_list(s):
        if s is None: return []
        return [p.strip() for p in str(s).replace(";", ",").split(",") if p.strip()]

    ignores = _to_list(ignore_substrings)

    try:
        perf = drv.get_log("performance")
    except Exception as e:
        bi.log(f"[CHECK][network] performance logs unavailable: {type(e).__name__}: {e}", level="WARN")
        return

    fails = []
    for row in perf:
        try:
            msg = json.loads(row.get("message", "{}")).get("message", {})
            if msg.get("method") != "Network.responseReceived":
                continue
            resp = msg.get("params", {}).get("response", {})
            status = int(resp.get("status", 0))
            url = resp.get("url", "")
            if not url or url.startswith("data:"):
                continue
            if any(ig in url for ig in ignores):
                continue
            if status >= threshold:
                fails.append(f"{status} {url}")
        except Exception:
            continue

    if fails:
        bi.log("[CHECK][network] failed responses:\n" + "\n".join(fails[:100]), level="ERROR")
        raise AssertionError(f"Found {len(fails)} network response(s) with status >= {threshold}")
    else:
        bi.log(f"[CHECK][network] no responses with status >= {threshold}", level="INFO")

def _apply_params_with_retry(
    *,
    location: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    single_date: str | None = None,
    flags_to_check: list[str] | None = None,
    # поддерживаем старый dict-формат и новый строковый/списочный
    extra_params=None,
    params_extra=None,
    max_attempts: int = 3,
    retry_delay: float = 1.0,
    timeout: float = 20.0,
):
    """Открывает Report parameters, проставляет значения и жмёт Show.

    extra_params:
        - dict: {"Machine": "200"}  -> заполняется по label
        - str|list[str]: спецификации как в params_extra

    params_extra:
        - str:  "text|label=\"Machine\"|200"
        - list: ["text|label=\"Machine\"|200", "click|attr=\"data-foo=bar\"|"]
    """
    from robot.libraries.BuiltIn import BuiltIn
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import re, time

    bi = BuiltIn()
    sl = bi.get_library_instance("SeleniumLibrary")
    drv = sl.driver

    flags_to_check = flags_to_check or []

    # ---- helpers -------------------------------------------------------------
    def _open_params_panel():
        locs = [
            "xpath://*[self::button or self::span][contains(normalize-space(.), 'Report parameters')]",
        ]
        for loc in locs:
            try:
                sl.wait_until_page_contains_element(loc, timeout=timeout)
                try:
                    sl.click_element(loc)
                except Exception:
                    try:
                        xp = loc.replace("xpath:", "")
                        btn = drv.find_element(By.XPATH, f"{xp}/ancestor::button[1]")
                        btn.click()
                    except Exception:
                        pass
                return
            except Exception:
                continue
        # допускаем, что панель уже открыта

    def _fill_date_by_attr(attr: str, value: str) -> bool:
        try:
            BuiltIn().run_keyword("Fill Date By Attr", attr, value)
            return True
        except Exception:
            try:
                BuiltIn().run_keyword("Fill By Attr", attr, value)
                return True
            except Exception:
                return False

    def _fill_date_range(start: str | None, end: str | None):
        if start:
            for attr in ['date-range="start"', 'placeholder="Start date"', 'aria-label="Start date"']:
                if _fill_date_by_attr(attr, start):
                    _log(f'[PARAMS] set Start date via Attr ({attr}) -> "{start}"')
                    break
            else:
                _log("[PARAMS] cannot set Start date", level="WARN")
        if end:
            for attr in ['date-range="end"', 'placeholder="End date"', 'aria-label="End date"']:
                if _fill_date_by_attr(attr, end):
                    _log(f'[PARAMS] set End date via Attr ({attr}) -> "{end}"')
                    break
            else:
                _log("[PARAMS] cannot set End date", level="WARN")

    def _fill_single_date(value: str):
        for attr in ['placeholder="Select date"', 'placeholder="Date"', 'aria-label="Date"', 'date-range="start"']:
            if _fill_date_by_attr(attr, value):
                _log(f'[PARAMS] set Single date via Attr ({attr}) -> "{value}"')
                return
        _log("[PARAMS] cannot set Single date", level="WARN")

    def _set_location(val: str):
        for attr in [
            'id="query_location_id"',
            'placeholder="Select location"',
            'aria-label="Location"',
            'name="location"',
            'id="location"',
            'placeholder="Location"',
        ]:
            try:
                BuiltIn().run_keyword("Select By Attr", attr, val)
                _log(f'[PARAMS] set Location via Select By Attr ({attr}) -> "{val}"')
                return
            except Exception:
                continue
        _log("[PARAMS] Location not set (no known locator matched)", level="WARN")

    def _ensure_flag_on(label_text: str):
        try:
            xp_lbl = f"//label[normalize-space()='{label_text}']"
            xp_ctrl = xp_lbl + "/following::*[self::input[@type='checkbox'] or self::button[contains(@class,'ant-switch')]][1]"
            el = WebDriverWait(drv, 6).until(EC.presence_of_element_located((By.XPATH, xp_ctrl)))
            is_on = el.tag_name.lower() == "input" and el.is_selected()
            if el.tag_name.lower() != "input":
                cls = el.get_attribute("class") or ""
                is_on = "ant-switch-checked" in cls or "checked" in cls
            if not is_on:
                try:
                    sl.click_element(xp_lbl)
                except Exception:
                    sl.click_element(xp_ctrl)
                _log(f"[PARAMS] check flag: {label_text}")
        except Exception:
            _log(f"[PARAMS] cannot toggle flag '{label_text}'", level="WARN")

    def _fill_by_label(label_text: str, value: str):
        try:
            lab = drv.find_element(By.XPATH, f"//label[normalize-space()='{label_text}']")
            for_id = lab.get_attribute("for")
            if for_id:
                attr = f'id="{for_id}"'
                try:
                    BuiltIn().run_keyword("Fill By Attr", attr, value)
                    _log(f'[PARAMS] set "{label_text}" via Fill By Attr ({attr}) -> "{value}"')
                    return
                except Exception:
                    pass
            # fallback — первый input/textarea после label
            xp = f"//label[normalize-space()='{label_text}']/following::*[self::input[not(@type='hidden')] or self::textarea][1]"
            el = WebDriverWait(drv, 8).until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click()
            el.send_keys(Keys.CONTROL, "a")
            el.send_keys(Keys.DELETE)
            el.send_keys(value)
            _log(f'[PARAMS] set "{label_text}" via label-xpath -> "{value}"')
        except Exception as e:
            _log(f'[PARAMS] "{label_text}" set failed: {type(e).__name__}: {e}', level="WARN")

    def _iter_specs(src):
        """Возвращает кортежи (kind, label, attr, value) из строк спецификаций."""
        if not src:
            return
        if isinstance(src, str):
            seq = [src]
        elif isinstance(src, (list, tuple)):
            seq = list(src)
        else:
            return
        for spec in seq:
            parts = [p.strip() for p in re.split(r"\|", str(spec), maxsplit=2)]
            if len(parts) < 3:
                continue
            kind = parts[0].lower()
            target = parts[1]
            value = parts[2]
            m_label = re.search(r'label\s*=\s*"([^"]+)"|label\s*=\s*\'([^\']+)\'', target)
            m_attr  = re.search(r'attr\s*=\s*"([^"]+)"|attr\s*=\s*\'([^\']+)\'', target)
            label = (m_label.group(1) or m_label.group(2)) if m_label else None
            attr  = (m_attr.group(1)  or m_attr.group(2))  if m_attr  else None
            yield kind, label, attr, value

    def _apply_extra_params():
        # 1) старый dict-формат
        if isinstance(extra_params, dict):
            for lbl, val in extra_params.items():
                if isinstance(lbl, str) and str(val).strip():
                    _fill_by_label(lbl.strip(), str(val).strip())
        elif isinstance(extra_params, (str, list, tuple)):
            # трактуем как строковые спецификации (как params_extra)
            for kind, label, attr, value in _iter_specs(extra_params):
                _apply_one_spec(kind, label, attr, value)

        # 2) новый params_extra
        for kind, label, attr, value in _iter_specs(params_extra):
            _apply_one_spec(kind, label, attr, value)

    def _apply_one_spec(kind: str, label: str | None, attr: str | None, value: str):
        if kind == "text":
            if label:
                _fill_by_label(label, value)
            elif attr:
                try:
                    BuiltIn().run_keyword("Fill By Attr", attr, value)
                    _log(f'[PARAMS] set by attr ({attr}) -> "{value}"')
                except Exception as e:
                    _log(f"[PARAMS] fill by attr failed: {e}", level="WARN")
        elif kind == "select":
            if attr:
                try:
                    BuiltIn().run_keyword("Select By Attr", attr, value)
                    _log(f'[PARAMS] select by attr ({attr}) -> "{value}"')
                except Exception as e:
                    _log(f"[PARAMS] select by attr failed: {e}", level="WARN")
            elif label:
                # нет отдельного селектора по label — пробуем как текстовое поле
                _fill_by_label(label, value)
        elif kind == "click":
            if attr:
                try:
                    BuiltIn().run_keyword("Click By Attr", attr)
                    _log(f'[PARAMS] click by attr ({attr})')
                except Exception as e:
                    _log(f"[PARAMS] click by attr failed: {e}", level="WARN")

    def _click_show_and_wait():
        _log("[PARAMS] click Show")
        try:
            BuiltIn().run_keyword("Click By Text", "Show")
        except Exception:
            try:
                sl.click_element("xpath://*[(self::button or self::span) and normalize-space(.)='Show']")
            except Exception:
                pass
        if not _wait_table_rows_safe(timeout=timeout):
            _log("Report table did not appear after Show", level="WARN")

    # ---- main loop -----------------------------------------------------------
    for attempt in range(1, int(max_attempts) + 1):
        _log(f"[PARAMS] attempt {attempt}/{max_attempts}")
        try:
            _open_params_panel()

            if isinstance(location, str) and location.strip():
                _set_location(location.strip())

            if single_date and (start_date or end_date):
                _log("[PARAMS] both single_date and range provided — using single_date", level="WARN")

            if single_date:
                _fill_single_date(single_date.strip())
            else:
                _fill_date_range(
                    start_date.strip() if start_date else None,
                    end_date.strip() if end_date else None,
                )

            for flag in flags_to_check:
                name = str(flag).strip()
                if name:
                    _ensure_flag_on(name)

            _apply_extra_params()
            _click_show_and_wait()
            return
        except Exception as e:
            _log(f"[PARAMS] error on attempt {attempt}: {type(e).__name__}: {e}", level="WARN")
            if attempt < int(max_attempts):
                time.sleep(float(retry_delay))

    _log("[PARAMS] failed after all attempts — continue test anyway", level="WARN")



def _open_params_panel():
    bi = BuiltIn()
    try:
        bi.run_keyword("Wait Until Page Has", "xpath://span[contains(., 'Report parameters')]")
        _log("[PARAMS] open drawer")
        bi.run_keyword("Click By Text", "Report parameters")
    except Exception:
        pass
    try:
        drv = _drv()
        WebDriverWait(drv, 6).until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div.ant-drawer .ant-drawer-body form#query, div.ant-drawer .ant-drawer-body form.ant-form")
        ))
        _log("[PARAMS] drawer is ready", level="DEBUG")
    except Exception:
        pass


def _smart_fill_params(*, location: str | None,
                       start_date: str | None,
                       end_date: str | None,
                       single_date: str | None,
                       flags_to_check: list[str]):
    """Локация, чекбоксы, диапазон дат или одиночная дата. Все действия мягкие + логи."""
    bi = BuiltIn()

    if location:
        try:
            _log(f"[PARAMS] set location: {location}")
            bi.run_keyword("Select By Attr", 'id="query_location_id"', location)
        except Exception:
            _log("[PARAMS] location select not present", level="DEBUG")

    for flag in flags_to_check or []:
        try:
            _log(f"[PARAMS] check flag: {flag}")
            _set_checkbox_in_params(flag, value=True)
        except Exception:
            _log(f"[PARAMS] flag not found: {flag}", level="DEBUG")

    placed = False
    if start_date or end_date:
        if start_date:
            for ph in ('placeholder="Start date"', 'placeholder="Start Date"', 'placeholder="From date"', 'placeholder="From Date"'):
                try:
                    _log(f"[PARAMS] set start date ({ph}): {start_date}")
                    bi.run_keyword("Fill Date By Attr", ph, start_date)
                    placed = True
                    break
                except Exception:
                    continue
        if end_date:
            for ph in ('placeholder="End date"', 'placeholder="End Date"', 'placeholder="To date"', 'placeholder="To Date"'):
                try:
                    _log(f"[PARAMS] set end date ({ph}): {end_date}")
                    bi.run_keyword("Fill Date By Attr", ph, end_date)
                    placed = True
                    break
                except Exception:
                    continue

    if not placed and (single_date or start_date):
        s1 = single_date or start_date
        for ph in ('placeholder="Select date"', 'placeholder="Select Date"', 'placeholder="Date"', 'placeholder="Дата"', 'placeholder="Выберите дату"'):
            try:
                _log(f"[PARAMS] set single date ({ph}): {s1}")
                bi.run_keyword("Fill Date By Attr", ph, s1)
                placed = True
                break
            except Exception:
                continue


def _click_show_in_params():
    bi = BuiltIn()
    drv = _drv()
    try:
        bi.run_keyword("Click By Text", "Show")
        return
    except Exception:
        pass
    # Фолбэк — допустим для кнопки Show
    try:
        btn = drv.find_element(By.XPATH, "//div[contains(@class,'ant-drawer')]//button[.//span[normalize-space()='Show']]")
        try:
            btn.click()
        except Exception:
            drv.execute_script("arguments[0].click()", btn)
    except Exception:
        pass


def _set_checkbox_in_params(label_text: str, value: bool = True):
    """Ставит/снимает чекбокс в Report parameters по тексту ярлыка."""
    drv = _drv()
    root = _params_root()
    if root is None:
        return

    candidates = [
        ".//label[contains(@class,'ant-checkbox-wrapper')][.//*[normalize-space(text())=%s]]",
        ".//*[contains(@class,'ant-checkbox-wrapper')][.//*[normalize-space(text())=%s]]",
        ".//div[contains(@class,'ant-form-item')][.//*[normalize-space(text())=%s]]//label[contains(@class,'ant-checkbox-wrapper')]",
        ".//div[contains(@class,'ant-form-item')][.//*[normalize-space(text())=%s]]//span[contains(@class,'ant-checkbox')]",
    ]
    wrap = None
    for xp in candidates:
        try:
            wrap = root.find_element(By.XPATH, xp % _xpath_quote(label_text))
            break
        except Exception:
            continue
    if wrap is None:
        return

    def _is_checked(element):
        try:
            cb = element.find_element(By.XPATH, ".//span[contains(@class,'ant-checkbox')]")
            cls = cb.get_attribute("class") or ""
            return "ant-checkbox-checked" in cls
        except Exception:
            return False

    cur = _is_checked(wrap)
    if (value and not cur) or ((not value) and cur):
        try:
            wrap.click()
        except Exception:
            drv.execute_script("arguments[0].click()", wrap)


def _params_root():
    drv = _drv()
    try:
        return drv.find_element(By.XPATH, "//div[contains(@class,'ant-drawer') and contains(@class,'open')]")
    except Exception:
        try:
            return drv.find_element(By.XPATH, "//div[contains(@class,'ant-drawer')][not(contains(@class,'close'))]")
        except Exception:
            return None


def _adjust_datetime_value(src: str | None, attempt: int) -> str | None:
    """Добавляем время/секунды на последующих попытках, если поле их требует."""
    if not src:
        return None
    s = str(src).strip()
    if attempt == 0:
        return s
    if attempt == 1:
        if len(s) == 10 and s[2] == "." and s[5] == ".":
            return s + " 00:00"
        return s
    if len(s) >= 16 and s[13] == ":" and s.count(":") == 1:
        return s + ":00"
    if len(s) == 10 and s[2] == "." and s[5] == ".":
        return s + " 00:00:00"
    return s


# ─────────────────────────── Таблица ───────────────────────────

def _wait_table_rows(timeout: float = 20.0):
    drv = _drv()
    def _has_rows(d):
        try:
            table = d.find_element(By.CSS_SELECTOR, "div.ant-table")
        except Exception:
            return False
        rows = table.find_elements(By.XPATH, ".//tbody/tr[not(contains(@class,'ant-table-placeholder'))]")
        return any(_visible(r) for r in rows)
    WebDriverWait(drv, timeout).until(_has_rows)


def _wait_table_rows_safe(timeout: float = 20.0) -> bool:
    try:
        _wait_table_rows(timeout=timeout)
        return True
    except Exception:
        return False


def _all_headers():
    drv = _drv()
    headers = drv.find_elements(
        By.XPATH,
        "//div[contains(@class,'ant-table')]//thead//th[contains(@class,'ant-table-cell')]"
    )
    out = []
    for h in headers:
        cls = h.get_attribute("class") or ""
        # пропускаем служебную «скроллбар»-ячейку
        if "ant-table-cell-scrollbar" in cls:
            continue
        out.append(h)
    return out



def _header_anchor_text(th):
    cand = [
        (th.get_attribute("data-title") or "").strip(),
        (th.get_attribute("title") or "").strip(),
        (th.get_attribute("aria-label") or "").strip(),
        (th.text or "").strip(),
    ]
    for c in cand:
        if c:
            return c
    try:
        desc = th.find_element(By.XPATH, ".//*[normalize-space(text())!=''][1]")
        return (desc.text or "").strip()
    except Exception:
        return ""


def _header_colindex(th):
    idx = th.get_attribute("aria-colindex")
    if idx and str(idx).isdigit():
        return int(idx)
    drv = _drv()
    return drv.execute_script("""
        var th = arguments[0];
        th = th.closest('th') || th;
        var row = th.parentElement;
        var i = 1;
        for (var n=row.firstElementChild; n; n=n.nextElementSibling){
            if (n===th) return i;
            i++;
        }
        return i;
    """, th)


def _pick_cell_value(col_index: int, row_index: int = 1, max_scan_rows: int = 10):
    """
    Возвращает текст ячейки [row_index, col_index], игнорируя служебные строки
    (ant-table-measure-row / aria-hidden / placeholder). Если в указанной
    строке пусто, сканирует следующие до max_scan_rows и берёт первое непустое.
    """
    drv = _drv()

    rows = drv.find_elements(
        By.XPATH,
        "//div[contains(@class,'ant-table')]//tbody"
        "/tr[not(contains(@class,'ant-table-placeholder'))"
        " and not(contains(@class,'ant-table-measure-row'))"
        " and not(@aria-hidden='true')]"
    )
    if not rows:
        return None

    target_idx = max(1, int(row_index))
    target_idx = min(target_idx, len(rows))

    def _cell_text(r):
        try:
            tds = r.find_elements(By.XPATH, "./td")
            if 1 <= int(col_index) <= len(tds):
                td = tds[int(col_index) - 1]
                txt = (td.text or td.get_attribute("textContent") or td.get_attribute("innerText") or "").strip()
                return txt if txt else None
        except Exception:
            return None

    val = _cell_text(rows[target_idx - 1])
    if val:
        return val

    end = min(len(rows), target_idx - 1 + int(max_scan_rows))
    for i in range(target_idx, end):
        val = _cell_text(rows[i])
        if val:
            return val

    end = min(len(rows), int(max_scan_rows))
    for i in range(0, end):
        val = _cell_text(rows[i])
        if val:
            return val

    return None


# ─────────────── Открытие фильтра ЧЕРЕЗ КЕЙВОРДЫ + логи ───────────────

def _try_open_filter_with_keywords(anchor: str, order_list: list[str], timeout: float = 6.0) -> str | None:
    """Перебирает кейворды открытия по порядку, логирует попытки, ждёт оверлей."""
    bi = BuiltIn()
    drv = _drv()

    for kind in order_list:
        try:
            if kind == "text":
                _log(f"Open filter from \"{anchor}\" column via Open Text Filter")
                bi.run_keyword("Open Text Filter", anchor)
            elif kind == "numeric":
                _log(f"Open filter from \"{anchor}\" column via Open Numeric Filter")
                bi.run_keyword("Open Numeric Filter", anchor)
            elif kind == "datetime":
                _log(f"Open filter from \"{anchor}\" column via Open DateTime Filter")
                bi.run_keyword("Open DateTime Filter", anchor)
            elif kind == "multiselect":
                _log(f"Open filter from \"{anchor}\" column via Open Multiselect Filter")
                bi.run_keyword("Open Multiselect Filter", anchor)
            else:
                continue
        except Exception as e:
            _log(f"Open filter via {kind} — failed: {type(e).__name__}", level="DEBUG")
            continue

        if _wait_filter_dropdown_silent(drv, timeout=1.5):
            detected = _detect_filter_type()
            _log(f"Filter dropdown opened — detected: {detected}")
            return detected if detected != "unknown" else kind

    _log(f"Open filter from \"{anchor}\" column — all keyword attempts failed", level="DEBUG")
    return None


# ─────────────────────────── (Необязательный) фолбэк ───────────────────────────
# Используется ТОЛЬКО если allow_fallback_clicks=True в главном кейворде.

def _find_header_filter_control(th):
    """
    Найти элемент-триггер фильтра внутри заголовка столбца <th>.
    Проверка выполняется только по DOM (никаких проверок видимости и скроллов).
    Возвращает WebElement или None, если триггера нет.
    """
    if th is None:
        return None

    # Сначала ищем каноничный триггер AntD
    xpaths = [
        # Вариант: триггер внутри контейнера .ant-table-filter-column
        ".//*[contains(@class,'ant-table-filter-column')]//*[contains(@class,'ant-table-filter-trigger')]",
        # Фолбэк: триггер где угодно в th
        ".//*[contains(@class,'ant-table-filter-trigger')]",
        # Если по каким-то причинам триггера нет, но отрисована иконка фильтра/поиска — вернём её (кликер разберётся)
        ".//*[contains(@class,'ant-table-filter-column')]//*[contains(@class,'anticon-filter') or contains(@class,'anticon-search')]",
        ".//*[contains(@class,'anticon-filter') or contains(@class,'anticon-search')]",
    ]

    for xp in xpaths:
        els = th.find_elements(By.XPATH, xp)
        if els:
            return els[0]

    return None


def _open_filter_by_trigger(trig, timeout: float = 6.0) -> bool:
    drv = _drv()
    try:
        _scroll_el_into_view(trig)
        WebDriverWait(drv, timeout).until(EC.element_to_be_clickable(trig))
    except Exception:
        pass
    for _ in range(3):
        try:
            trig.click()
        except Exception:
            try:
                ActionChains(drv).move_to_element(trig).pause(0.05).click().perform()
            except Exception:
                try:
                    drv.execute_script("arguments[0].click()", trig)
                except Exception:
                    continue
        if _wait_filter_dropdown_silent(drv, 1.2):
            return True
    return _wait_filter_dropdown_silent(drv, timeout)


def _wait_filter_dropdown(drv, timeout: float = 4.0):
    sels = [".ant-table-filter-dropdown", ".ant-dropdown", ".ant-popover", ".ant-select-dropdown"]
    return WebDriverWait(drv, timeout).until(lambda d: _last_visible_overlay(d, sels))


def _wait_filter_dropdown_silent(drv, timeout: float = 4.0) -> bool:
    try:
        _wait_filter_dropdown(drv, timeout)
        return True
    except TimeoutException:
        return False


def _last_visible_overlay(drv, selector_list: list[str]):
    for sel in selector_list:
        try:
            nodes = drv.find_elements(By.CSS_SELECTOR, sel)
            vis = [n for n in nodes if _visible(n)]
            if vis:
                return vis[-1]
        except Exception:
            continue
    return None


def _last_visible_filter(drv, timeout: float = 0.5):
    sels = [".ant-table-filter-dropdown", ".ant-dropdown", ".ant-popover", ".ant-select-dropdown"]
    return _last_visible_overlay(drv, sels)


def _detect_filter_type():
    drv = _drv()
    dd = _last_visible_filter(drv, timeout=0.5)
    if not dd:
        return "unknown"

    selector_priority = [
        ".ant-table-filter-dropdown",
        ".ant-dropdown",
        ".ant-popover",
        ".ant-select-dropdown",
    ]

    def _collect_visible_filters():
        panels = []
        seen_ids: set[str] = set()
        for sel in selector_priority:
            try:
                nodes = drv.find_elements(By.CSS_SELECTOR, sel)
            except Exception:
                continue
            for node in nodes:
                try:
                    node_id = getattr(node, "id", None)
                except Exception:
                    node_id = None
                if node_id and node_id in seen_ids:
                    continue
                if not _visible(node):
                    continue
                if node_id:
                    seen_ids.add(node_id)
                panels.append(node)
        try:
            if dd in panels:
                panels.remove(dd)
        except Exception:
            pass
        panels.insert(0, dd)
        return panels

    checkbox_selectors = [
        "input[type='checkbox']",
        ".ant-checkbox",
        ".ant-checkbox-wrapper",
    ]

    def _has_checkboxes(wait: float = 0.0) -> bool:
        deadline = time.time() + max(0.0, wait)
        while True:
            for panel in _collect_visible_filters():
                try:
                    if any(panel.find_elements(By.CSS_SELECTOR, sel) for sel in checkbox_selectors):
                        return True
                except StaleElementReferenceException:
                    continue
            if time.time() >= deadline:
                return False
            time.sleep(0.1)

    try:
        if dd.find_elements(By.CSS_SELECTOR, ".ant-picker .ant-picker-input input"):
            texts = [
                i.get_attribute("value") or ""
                for i in dd.find_elements(By.CSS_SELECTOR, ".ant-picker .ant-picker-input input")
            ]
            has_time = any(":" in t for t in texts)
            return "datetime" if has_time else "date"

        if _has_checkboxes(wait=1.0):
            return "checkbox-list"

        if dd.find_elements(By.CSS_SELECTOR, "input[inputmode='numeric'], input[type='number']"):
            # если чекбоксы подгружаются с задержкой, даём им шанс проявиться
            if _has_checkboxes(wait=0.6):
                return "checkbox-list"
            return "numeric"
        if dd.find_elements(By.XPATH, ".//input[not(@type='hidden') and not(@readonly) and not(ancestor::*[contains(@class,'ant-select')])]"):
            return "text"
    except Exception:
        pass
    return "unknown"


def _click_ok_in_filter():
    bi = BuiltIn()
    # Всегда подтверждаем твоими кейвордами
    try:
        bi.run_keyword("Click By Text On Filter", "OK")
        return
    except Exception:
        pass
    try:
        bi.run_keyword("Click By Attr On Filter", 'aria-label="check-circle"')
        return
    except Exception:
        pass
    try:
        bi.run_keyword("Click By Text On Filter", "Apply")
    except Exception:
        pass


def _click_header_sorter_multiple_times(th, anchor: str, *, times: int = 4, timeout: float = 4.0, delay: float = 0.1) -> bool:
    """Кликает по сортировщику в заголовке несколько раз, с учётом возможного DOM-обновления."""
    if times <= 0:
        return False

    drv = _drv()
    anchor = (anchor or "").strip()

    def _resolve_th():
        nonlocal th
        try:
            _ = th.tag_name
            return th
        except StaleElementReferenceException:
            th = None
        except Exception:
            pass
        if th is not None:
            return th
        if anchor:
            refreshed = _header_by_title(anchor)
            if refreshed is not None:
                th = refreshed
                return refreshed
        return None

    def _find_sorter(target_th):
        if target_th is None:
            return None
        try:
            return target_th.find_element(By.CSS_SELECTOR, ".ant-table-column-sorter")
        except Exception:
            return None

    for _ in range(times):
        end_time = time.time() + max(timeout, 0.5)
        while True:
            target_th = _resolve_th()
            sorter = _find_sorter(target_th)
            if sorter is None:
                return False
            try:
                drv.execute_script("arguments[0].scrollIntoView({block:'center',inline:'center'});", sorter)
            except Exception:
                pass
            try:
                sorter.click()
                break
            except StaleElementReferenceException:
                th = None
            except Exception:
                try:
                    drv.execute_script("arguments[0].click();", sorter)
                    break
                except Exception:
                    pass

            if time.time() > end_time:
                return False
            time.sleep(0.1)

        time.sleep(delay)

    _log(
        f"[COLUMN] {anchor or '#'} — sorter clicked {times}x",
        level="DEBUG",
    )
    return True


def _clear_all_filters_if_present():
    # Сначала пробуем общий кейворд (если есть)
    try:
        BuiltIn().run_keyword("Click By Attr", 'title="Clear all filters"')
        return
    except Exception:
        pass
    # Фолбэк — прямым драйвером
    drv = _drv()
    try:
        btns = drv.find_elements(By.CSS_SELECTOR, '[title*="Clear all filters"], [aria-label="clear-all-filters"]')
        for b in btns:
            if _visible(b):
                try:
                    b.click()
                except Exception:
                    drv.execute_script("arguments[0].click()", b)
                return
    except Exception:
        pass
    try:
        btn = drv.find_element(By.XPATH, "//*[self::button or self::span][normalize-space(text())='Clear all filters']")
        if _visible(btn):
            try:
                btn.click()
            except Exception:
                drv.execute_script("arguments[0].click()", btn)
    except Exception:
        pass


# ─────────────────────────── Вспомогательные утилиты ───────────────────────────

def _try_select_option_with_keywords(value: str) -> bool:
    """
    Мультиселекты: сначала пробуем Click By Text On Filter,
    если не нашли — вычисляем data-menu-id по тексту и кликаем
    строго форматом data-menu-id="...".
    """
    bi = BuiltIn()
    target = str(value).strip()

    # 1) По тексту
    try:
        _log(f'Try select by text: "{target}"')
        bi.run_keyword("Click By Text On Filter", target)
        return True
    except Exception:
        pass

    # 2) По data-menu-id (ровно в формате data-menu-id="…")
    dm_id = _resolve_data_menu_id_for_option(target)
    if dm_id:
        attr = f'data-menu-id="{dm_id}"'
        _log(f'Try select by attr: {attr}')
        try:
            bi.run_keyword("Click By Attr On Filter", attr)
            return True
        except Exception:
            # иногда попадает в общий контейнер
            try:
                bi.run_keyword("Click By Attr", attr)
                return True
            except Exception:
                return False

    _log("Option not found by text nor data-menu-id", level="DEBUG")
    return False

def _resolve_data_menu_id_for_option(display_text: str) -> str | None:
    """
    В открытом выпадающем списке ищет пункт по видимому тексту
    и возвращает его значение атрибута data-menu-id.
    """
    drv = _drv()
    dd = _last_visible_filter(drv, timeout=0.7)
    if not dd:
        return None

    target = _norm(display_text)

    # а) прямой перебор элементов с data-menu-id
    try:
        nodes = dd.find_elements(By.CSS_SELECTOR, "*[data-menu-id]")
        for n in nodes:
            if not _visible(n):
                continue
            txt = _norm(n.text or n.get_attribute("textContent") or "")
            if txt == target or (target and target in txt):
                val = n.get_attribute("data-menu-id")
                if val:
                    return val
    except Exception:
        pass

    # б) ищем по тексту и поднимаемся к ближайшему предку с data-menu-id
    xp = f".//*[normalize-space(.)={_xpath_quote(display_text)}]"
    try:
        node = dd.find_element(By.XPATH, xp)
        cur = node
        # поднимаемся максимум 6 уровней
        for _ in range(6):
            if cur is None:
                break
            val = cur.get_attribute("data-menu-id")
            if val:
                return val
            try:
                cur = cur.find_element(By.XPATH, "./..")
            except Exception:
                break
    except Exception:
        pass

    return None


def _norm(s: str) -> str:
    """Нормализуем пробелы/nbsp, подрезаем."""
    if s is None:
        return ""
    return " ".join(str(s).replace("\xa0", " ").split()).strip()

def _drv():
    return BuiltIn().get_library_instance("SeleniumLibrary").driver

def _visible(el) -> bool:
    try:
        if not el.is_displayed():
            return False
        rect = el.rect or {}
        return float(rect.get("width", 0)) > 0 and float(rect.get("height", 0)) > 0
    except Exception:
        return False

def _scroll_el_into_view(el):
    drv = _drv()
    try:
        drv.execute_script("arguments[0].scrollIntoView({block:'center',inline:'center'});", el)
    except Exception:
        pass

def _xpath_quote(text: str) -> str:
    t = str(text)
    if "'" not in t:
        return f"'{t}'"
    if '"' not in t:
        return f'"{t}"'
    parts = t.split("'")
    return "concat(" + ", \"'\", ".join([f"'{p}'" for p in parts]) + ")"

def _normalize_open_order(s: str) -> list[str]:
    if not s:
        return ["text", "numeric", "datetime", "multiselect"]
    s = s.replace(";", ",").replace("|", ",")
    parts = [p.strip().lower() for p in s.split(",") if p.strip()]
    valid = {"text", "numeric", "datetime", "multiselect"}
    out = [p for p in parts if p in valid]
    return out or ["text", "numeric", "datetime", "multiselect"]

def _to_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).strip()
    if not s:
        return []
    for sep in ("|", ";"):
        s = s.replace(sep, ",")
    parts = [p.strip() for p in s.split(",")]
    return [p for p in parts if p]

def _to_int(v, default=None):
    try:
        return int(str(v).strip())
    except Exception:
        return default

def _to_int_or_none(v):
    if v in (None, "", "None"):
        return None
    return _to_int(v, None)

def _to_float(v, default=None):
    try:
        return float(str(v).replace(",", ".").strip())
    except Exception:
        return default

def _log(message: str, level: str = "INFO"):
    """Единая точка логирования в RF."""
    try:
        BuiltIn().log(str(message), level=level)
    except Exception:
        pass


def _to_max_columns(v):
    """
    Разрешены только: число (ограничение) или 'all' (без лимита).
    None трактуем как 'all'.
    Иначе — ValueError.
    """
    if v is None:
        return None  # по умолчанию без лимита
    s = str(v).strip().lower()
    if s == "all":
        return None
    try:
        return int(s)
    except Exception:
        raise ValueError("max_columns must be an integer or 'all'")



def _fill_date_in_filter(value: str):
    """
    Для фильтров даты/даты-времени вводим значение исключительно через
    твой кейворд Fill Date By Attr с placeholder="Select date".
    Если этот placeholder не найден (нестандартная локализация/верстка),
    пробуем короткие фолбэки, но приоритет — ровно "Select date".
    """
    bi = BuiltIn()
    # 1) Требуемый способ
    try:
        bi.run_keyword("Fill Date By Attr", 'placeholder="Select date"', value)
        return
    except Exception as e:
        _log(f'[FILTER-DATE] primary placeholder failed: {type(e).__name__}', level="DEBUG")

    # 2) Аккуратные фолбэки (на всякий случай; можно убрать, если хочешь только один вариант)
    fallbacks = (
        'placeholder="Select Date"',
        'placeholder="Дата"',
        'placeholder="Выберите дату"',
    )
    for ph in fallbacks:
        try:
            bi.run_keyword("Fill Date By Attr", ph, value)
            return
        except Exception:
            continue

    # 3) Ничего не подошло — бросаем, чтобы верхний try/except залогировал WARN
    raise RuntimeError("Date input inside filter not found by placeholder")

def _normalize_checks_when(s: str) -> set[str]:
    """
    Разрешённые точки: before_params, after_params, per_column, final.
    По умолчанию: after_params, per_column, final.
    """
    default = {"after_params", "per_column", "final"}
    if not s:
        return default
    parts = [p.strip().lower() for p in str(s).replace(";", ",").split(",") if p.strip()]
    allowed = {"before_params", "after_params", "per_column", "final"}
    out = {p for p in parts if p in allowed}
    return out or default


def _maybe_run_check(keyword_name: str | None, args: list[str] | None, fail: bool, hook: str):
    """
    Аккуратно вызывает пользовательский кейворд проверки.
    Если fail=True — пробрасывает исключение (роняет тест).
    Иначе — только WARN в лог.
    """
    if not keyword_name:
        return
    bi = BuiltIn()
    try:
        _log(f"[CHECK] {keyword_name} at {hook} args={args or []}", level="DEBUG")
        if args:
            bi.run_keyword(keyword_name, *args)
        else:
            bi.run_keyword(keyword_name)
    except Exception as e:
        if fail:
            raise
        _log(f"[CHECK] {keyword_name} failed at {hook}: {type(e).__name__}: {e}", level="WARN")



def _get_table_headers():
    """Тонкая обёртка: берём заголовки через уже существующий _all_headers()."""
    try:
        return _all_headers()
    except Exception:
        return []

def _open_header_filter_dropdown(th, timeout: float = 8.0) -> bool:
    """
    Открывает дропдаун фильтра по конкретному <th>.
    1) ищет триггер внутри th и жмёт его (_open_filter_by_trigger)
    2) фолбэк — по якорному тексту заголовка через _open_filter_auto
    """
    trig = _find_header_filter_control(th)
    if trig and _open_filter_by_trigger(trig, timeout=timeout):
        return True
    # фолбэк по тексту заголовка
    anchor = _header_anchor_text(th) or ""
    if anchor:
        _open_filter_auto(anchor, exact=True, timeout=timeout)
        try:
            drv = _drv()
            WebDriverWait(drv, timeout).until(
                lambda d: _last_visible_filter(d, timeout=0.1) is not None
            )
            return True
        except Exception:
            return False
    return False


def _resolve_filter_type() -> str:
    """
    Сопоставление к ожидаемым именам из check_report_filters:
      checkbox-list -> multiselect
      date -> datetime (чтобы не плодить ветки)
    """
    t = _detect_filter_type()
    if t == "checkbox-list":
        return "multiselect"
    if t == "date":
        return "datetime"
    return t or "unknown"

def _is_attr_pair(s: str) -> bool:
    if not isinstance(s, str):
        return False
    s = s.strip()
    return ('="' in s and s.endswith('"')) or ("='" in s and s.endswith("'"))

def _header_index_by_title(title: str):
    for th in _all_headers():
        if _header_anchor_text(th) == title:
            return _header_colindex(th)
    return None

def _header_by_title(title: str):
    for th in _all_headers():
        if _header_anchor_text(th) == title:
            return th
    return None

def _close_filter_dropdown_by_type(detected: str):
    # мягкое закрытие — без Reset для text/numeric/datetime
    drv = _drv()
    try:
        drv.switch_to.active_element.send_keys(Keys.ESCAPE)
    except Exception:
        pass

def _resolve_filter_type_without_open(anchor: str) -> str:
    """Определяет тип БЕЗ открытия: по <th> и/или по attr-паре."""
    a = str(anchor or "")
    if _is_attr_pair(a):
        # Частый кейс: class="PRINT_DATE" / class="TICKET_IN" → угадываем по токенам
        up = a.upper()
        if "DATE" in up or "TIME" in up or "DATETIME" in up or "EXPIRATION" in up or "REDEEM" in up or "SESSION" in up:
            return "datetime"
        if any(tok in up for tok in ["AMOUNT","BET","BILLS","TICKET","NUMBER","TOTAL","SUM","QTY"]):
            return "numeric"
        # атрибут на айди/энуме/справочнике — считаем multiselect
        if any(tok in up for tok in ["_ID","ID=","CLASS=\"CURRENCY","CLASS=\"LOCATION","STATUS","MACH","POSITION"]):
            return "multiselect"
        return "text"

    th = _header_by_title(a)
    if th is None:
        return "text"
    classes = (th.get_attribute("class") or "").upper()
    title   = (_header_anchor_text(th) or "").upper()

    if ("DATE" in classes or "TIME" in classes or _DATE_TITLE_RX.search(title)):
        return "datetime"
    if any(tok in classes for tok in ["AMOUNT","BET","BILLS","TICKET","NUMBER","TOTAL","SUM","QTY"]) or _NUM_TITLE_RX.search(title):
        return "numeric"
    if any(tok in classes for tok in ["SELECT","ENUM","LOCATION","CURRENCY","STATUS","MACH","POSITION"]):
        return "multiselect"
    return "text"

def _smoke_filter_ui(anchor: str, ftype: str | None = None, row_index: int = 1):
    """
    1) Определяем тип БЕЗ открытия.
    2) Открываем строго соответствующим кейвордом Open * Filter (по title или по attr-паре).
    3) Вызываем профильный run_*_filter_smoke, который работает ТОЛЬКО в открытом фильтре.
    4) Здесь НИЧЕГО НЕ ЗАКРЫВАЕМ.
    """
    bi = BuiltIn()
    drv = _drv()

    # Если фильтр уже открыт (например, его только что открыл вызывающий код),
    # не трогаем его повторным кликом. Иначе AntD закроет выпадашку и дальнейшие
    # действия (ввод значения) упадут из-за отсутствующего инпута.
    reuse_open_filter = _last_visible_filter(drv, timeout=0.2) is not None

    # 1) тип без открытия
    t = (ftype or _resolve_filter_type_without_open(anchor) or "").lower()
    if t in ("checkbox-list","checkbox"): t = "multiselect"
    if t == "date": t = "datetime"

    # 2) открыть правильным Open * Filter, только если дропдаун ещё не открыт
    if not reuse_open_filter:
        if t == "text":
            bi.run_keyword("Open Text Filter", anchor)
        elif t in ("numeric","number","int","float"):
            bi.run_keyword("Open Numeric Filter", anchor)
        elif t in ("datetime","date"):
            bi.run_keyword("Open DateTime Filter", anchor)
        elif t == "multiselect":
            bi.run_keyword("Open Multiselect Filter", anchor)
        else:
            _log(f"[SMOKE] '{anchor}': unknown type '{t}', fallback Open Text Filter", level="WARN")
            bi.run_keyword("Open Text Filter", anchor)

    # 3) выполнить профильную ветку (внутри открытого фильтра)
    if t == "text":
        _run_text_filter_smoke(anchor, row_index=row_index)
    elif t in ("numeric","number","int","float"):
        _run_numeric_filter_smoke(anchor, row_index=row_index)
    elif t in ("datetime","date"):
        _run_datetime_filter_smoke(anchor, row_index=row_index)
    elif t == "multiselect":
        _run_multiselect_filter_smoke(anchor, row_index=row_index)

def _run_text_filter_smoke(anchor: str, row_index: int = 1):
    """Как в примере: просто вводим текст; подтверждение не жмём."""
    idx = _header_index_by_title(anchor) if not _is_attr_pair(str(anchor)) else _header_index_by_title(str(anchor))
    # если anchor — attr-пара, индекс по title может быть неизвестен; в таком случае сэмпл не критичен, но пробуем
    sample = _pick_cell_value(idx, row_index=row_index) if idx else None
    if not sample:
        # fallback — короткая строка, чтобы не зависать
        sample = "a"
    BuiltIn().run_keyword("Fill Text On Filter", str(sample))

def _run_numeric_filter_smoke(anchor: str, row_index: int = 1):
    """Как в примере: ввод + галочка (OK-иконка)."""
    idx = _header_index_by_title(anchor) if not _is_attr_pair(str(anchor)) else _header_index_by_title(str(anchor))
    cell = str(_pick_cell_value(idx, row_index=row_index) or "")
    m = re.search(r"[-−]?\d+(?:[.,]\d+)?", cell.replace("\u00A0"," "))
    val = (m.group(0).replace("−","-").replace(",", ".") if m else "0")
    BuiltIn().run_keyword("Fill Text On Filter", str(val))
    # подтверждение галочкой
    BuiltIn().run_keyword("Click By Attr On Filter", 'aria-label="check-circle"')

def _run_datetime_filter_smoke(anchor: str, row_index: int = 1):
    """Как в примере: Fill Date By Attr + галочка (иконка)."""
    idx = _header_index_by_title(anchor) if not _is_attr_pair(str(anchor)) else _header_index_by_title(str(anchor))
    sample = _pick_cell_value(idx, row_index=row_index)
    if not sample:
        from datetime import datetime as _dt
        sample = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    # универсальный таргет инпута даты внутри открытого фильтра
    BuiltIn().run_keyword("Fill Date By Attr", 'placeholder="Select date"', str(sample))
    # подтверждение галочкой
    # (если у конкретного фильтра OK — только иконкой, как ты указал)
    for _ in range(3):
        try:
            BuiltIn().run_keyword("Click By Attr On Filter", 'aria-label="check-circle"', "timeout=2")
            break
        except Exception:
            time.sleep(0.2)

def _run_multiselect_filter_smoke(anchor: str, row_index: int = 1):
    """Как в примере: клик по опции по видимому тексту + OK."""
    idx = _header_index_by_title(anchor) if not _is_attr_pair(str(anchor)) else _header_index_by_title(str(anchor))
    sample = _pick_cell_value(idx, row_index=row_index)
    if not sample:
        picked = _pick_first_multiselect_option()
        if not picked:
            _log(f"[MULTISELECT] '{anchor}': no sample in table and dropdown has no selectable options", level="WARN")
            return
        text, attr = picked
        _log(f"[MULTISELECT] '{anchor}': fallback to first option → {text}")
        if attr:
            BuiltIn().run_keyword("Click By Attr On Filter", attr)
        else:
            BuiltIn().run_keyword("Click By Text On Filter", text)
    else:
        BuiltIn().run_keyword("Click By Text On Filter", str(sample))
    ok = BuiltIn().run_keyword_and_return_status("Click By Text On Filter", "OK", "timeout=2")
    if not ok:
        BuiltIn().run_keyword("Click By Text On Filter", "Apply", "timeout=2")


def _pick_first_multiselect_option() -> tuple[str, str | None] | None:
    """Возвращает (text, attr_pair) для первой доступной опции мультиселекта."""
    drv = _drv()
    dd = _last_visible_filter(drv, timeout=0.7)
    if not dd:
        return None

    skip_tokens = {
        "select all",
        "clear",
        "clear all",
        "reset",
        "search",
        "no data",
        "none",
    }

    def _sanitize(text: str | None) -> str | None:
        val = _norm(text or "")
        if not val:
            return None
        low = val.lower()
        if low in skip_tokens:
            return None
        return val

    def _pick_from_nodes(nodes, *, prefer_attr: bool) -> tuple[str, str | None] | None:
        for node in nodes:
            try:
                cls = (node.get_attribute("class") or "").lower()
            except Exception:
                cls = ""
            if "disabled" in cls:
                continue
            if not _visible(node):
                continue
            text = None
            try:
                text = _sanitize(node.text or node.get_attribute("textContent") or "")
            except Exception:
                text = None
            if not text:
                continue
            if prefer_attr:
                try:
                    val = node.get_attribute("data-menu-id")
                except Exception:
                    val = None
                if val:
                    return text, f'data-menu-id="{val}"'
            return text, None
        return None

    # 1) Предпочтительно пункты с data-menu-id
    try:
        nodes = dd.find_elements(By.CSS_SELECTOR, "*[data-menu-id]")
    except Exception:
        nodes = []
    picked = _pick_from_nodes(nodes, prefer_attr=True)
    if picked:
        return picked

    # 2) Фолбэк: label с чекбоксами
    try:
        nodes = dd.find_elements(By.XPATH, ".//label[.//input[@type='checkbox' and not(@disabled)]]")
    except Exception:
        nodes = []
    picked = _pick_from_nodes(nodes, prefer_attr=False)
    if picked:
        return picked

    # 3) Ещё один фолбэк: элементы-опции по роли
    try:
        nodes = dd.find_elements(By.CSS_SELECTOR, "*[role='option'], *[role='menuitem']")
    except Exception:
        nodes = []
    picked = _pick_from_nodes(nodes, prefer_attr=False)
    if picked:
        return picked

    return None

def _open_filters_by_order(order_list, *, allow_fallback_clicks: bool = False, timeout: float = 8.0):
    """Prewarm filters (compat stub): основной цикл сам проходит по всем колонкам."""
    return
    
    
@keyword("Click Row Action By Login")
def click_row_action_by_login(
    search_col: str,
    search_value: str,
    click_col: str,
    click_text: str = "",
    table_index: int = 1,
    exact_search: bool = True,
    headers_exact: bool = False,  # оставлен для совместимости; фильтрация заголовков — строгое совпадение
    timeout: int = 15,
):
    drv = _drv()
    _log(
        f"[ROW-ACTION] search_col='{search_col}', value='{search_value}', "
        f"click_col='{click_col}', click_text='{click_text}', "
        f"table_index={table_index}, exact_search={exact_search}, headers_exact={headers_exact}, timeout={timeout}"
    )

    # ---------------- helpers ----------------
    def _norm(s: str) -> str:
        # Строгое совпадение по регистру, нормализуем только пробелы
        return " ".join((s or "").split())

    def _is_empty_click_text(s: str) -> bool:
        t = _norm(s)
        return t in ("", '""', "''")

    def _xpath_literal(s: str) -> str:
        if "'" not in s:
            return f"'{s}'"
        if '"' not in s:
            return f'"{s}"'
        parts = s.split("'")
        return "concat(" + ", \"'\", ".join([f"'{p}'" for p in parts]) + ")"

    def _headers_text(container):
        ths = container.find_elements(By.XPATH, ".//thead//th[not(contains(@class,'ant-table-cell-scrollbar'))]")
        out = []
        for th in ths:
            txt = (th.text or "").strip()
            if not txt:
                txt = (th.get_attribute("title") or th.get_attribute("aria-label") or "").strip()
            out.append(txt)
        return out

    def _index_of_header_exact(headers_text, target) -> int:
        t = _norm(target)
        for i, h in enumerate(headers_text, 1):
            if _norm(h) == t:
                return i
        return -1

    def _has_any_rows_quick(container) -> bool:
        # Быстрый не-блокирующий тест наличия строк
        if container.find_elements(By.XPATH, ".//div[contains(@class,'ant-table-row')]"):
            return True
        if container.find_elements(By.XPATH, ".//tbody/tr[not(contains(@class,'ant-table-placeholder'))]"):
            return True
        return False

    def _collect_rows(container):
        rows_div = container.find_elements(By.XPATH, ".//div[contains(@class,'ant-table-row')]")
        if rows_div:
            return rows_div, "div"
        rows_tr = container.find_elements(By.XPATH, ".//tbody/tr[not(contains(@class,'ant-table-placeholder'))]")
        return rows_tr, "tr"

    def _cells(row):
        # Поддержка td и виртуальных div.ant-table-cell
        return row.find_elements(By.XPATH, "./td | ./div[contains(@class,'ant-table-cell')]")

    # ---------------- containers (strict) ----------------
    def _collect_containers_strict():
        union = (
            "(//div[contains(@class,'ant-table-container')]"
            " | //div[contains(@class,'ant-table-wrapper')]//div[contains(@class,'ant-table')]"
            " | //div[contains(@class,'ant-table')][.//table])"
        )
        # 1) дождёмся хотя бы одну таблицу в корне
        WebDriverWait(drv, timeout).until(EC.presence_of_element_located((By.XPATH, union)))
        raw = drv.find_elements(By.XPATH, union)

        # дедуп и только видимые
        seen = set()
        base = []
        for el in raw:
            if el.id in seen:
                continue
            seen.add(el.id)
            try:
                if el.is_displayed():
                    base.append(el)
            except Exception:
                continue

        strict = []
        for c in base:
            try:
                # должна быть таблица (header/body структура уже отрисована)
                if not c.find_elements(By.XPATH, ".//table"):
                    continue
                hdrs = _headers_text(c)
                sc_idx = _index_of_header_exact(hdrs, search_col)
                cc_idx = _index_of_header_exact(hdrs, click_col)
                if sc_idx == -1 or cc_idx == -1:
                    continue
                # и уже должны присутствовать строки (исключаем «header-only» контейнеры)
                if not _has_any_rows_quick(c):
                    continue
                strict.append(c)
            except Exception:
                continue

        if strict:
            _log(f"[ROW-ACTION] strict containers (root): {len(strict)}")
            return strict

        # 2) если в корне не нашли — проверим iframe'ы (контекст останется внутри найденного iframe)
        iframes = drv.find_elements(By.TAG_NAME, "iframe")
        _log(f"[ROW-ACTION] no strict in root; probing {len(iframes)} iframes", level="WARN")
        for idx, fr in enumerate(iframes, 1):
            try:
                drv.switch_to.frame(fr)
                WebDriverWait(drv, 2).until(EC.presence_of_element_located((By.XPATH, union)))
                raw_if = drv.find_elements(By.XPATH, union)
                seen_if = set()
                base_if = []
                for el in raw_if:
                    if el.id in seen_if:
                        continue
                    seen_if.add(el.id)
                    if el.is_displayed():
                        base_if.append(el)

                strict_if = []
                for c in base_if:
                    if not c.find_elements(By.XPATH, ".//table"):
                        continue
                    hdrs = _headers_text(c)
                    sc_idx = _index_of_header_exact(hdrs, search_col)
                    cc_idx = _index_of_header_exact(hdrs, click_col)
                    if sc_idx == -1 or cc_idx == -1:
                        continue
                    if not _has_any_rows_quick(c):
                        continue
                    strict_if.append(c)

                if strict_if:
                    _log(f"[ROW-ACTION] strict containers (iframe #{idx}): {len(strict_if)}")
                    return strict_if
                drv.switch_to.default_content()
            except Exception:
                drv.switch_to.default_content()
                continue

        drv.switch_to.default_content()
        return []

    # ---------------- try on one container ----------------
    def _try_on_container(container, idx: int) -> bool:
        _log(f"[ROW-ACTION] probing strict container #{idx}")
        # явное ожидание строк (уже после строгой фильтрации это коротко)
        row_union = ".//tbody/tr[not(contains(@class,'ant-table-placeholder'))] | .//div[contains(@class,'ant-table-row')]"
        WebDriverWait(container, timeout).until(EC.presence_of_element_located((By.XPATH, row_union)))

        hdrs = _headers_text(container)
        sc_idx = _index_of_header_exact(hdrs, search_col)
        cc_idx = _index_of_header_exact(hdrs, click_col)
        if sc_idx == -1 or cc_idx == -1:
            _log(f"[ROW-ACTION] container #{idx}: headers mismatch (strict). headers={hdrs}", level="WARN")
            return False

        rows, _ = _collect_rows(container)
        if not rows:
            _log(f"[ROW-ACTION] container #{idx}: нет строк", level="WARN")
            return False

        # поиск строки
        target_row = None
        sv_norm = _norm(search_value)
        sv_cf = sv_norm.casefold()
        for r in rows:
            cells = _cells(r)
            if len(cells) < max(sc_idx, cc_idx):
                continue
            cell_search = cells[sc_idx - 1]
            txt = _norm(cell_search.text)
            ok = (txt == sv_norm) if exact_search else (sv_cf in txt.casefold())
            if ok:
                target_row = r
                break

        if target_row is None:
            _log(f"[ROW-ACTION] container #{idx}: строка '{search_value}' не найдена в '{search_col}'", level="WARN")
            return False

        # целевая ячейка и клик
        click_cell = _cells(target_row)[cc_idx - 1]
        try:
            drv.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", click_cell)
        except Exception:
            pass

        if not _is_empty_click_text(click_text):
            t = _norm(click_text)
            lit = _xpath_literal(t)
            cand = click_cell.find_elements(By.XPATH, f".//*[normalize-space(text()) = {lit}]")
            if not cand:
                cand = click_cell.find_elements(By.XPATH, f".//*[contains(normalize-space(text()), {lit})]")
            if not cand:
                _log(f"[ROW-ACTION] container #{idx}: в ячейке нет элемента с текстом '{click_text}'", level="WARN")
                return False
            el = cand[0]
            WebDriverWait(drv, timeout).until(EC.element_to_be_clickable(el))
            try:
                el.click()
            except Exception:
                drv.execute_script("arguments[0].click();", el)
            _log(f"[ROW-ACTION] container #{idx}: клик по '{click_text}' — OK")
            return True

        # фолбэки
        selectors = [
            ".//label[contains(@class,'ant-checkbox-wrapper')]",
            ".//span[contains(@class,'ant-checkbox')]",
            ".//*[@role='switch']",
            ".//button[not(@disabled)]",
            ".//a[normalize-space(string(.))!='']",
        ]
        target = None
        for xp in selectors:
            got = click_cell.find_elements(By.XPATH, xp)
            if got:
                target = got[0]
                break

        if target is None:
            _log(f"[ROW-ACTION] container #{idx}: нет интерактива в '{click_col}'", level="WARN")
            return False

        WebDriverWait(drv, timeout).until(EC.element_to_be_clickable(target))
        try:
            target.click()
        except Exception:
            drv.execute_script("arguments[0].click();", target)
        _log(f"[ROW-ACTION] container #{idx}: клик — OK")
        return True

    # ---------------- main ----------------
    containers = _collect_containers_strict()
    total = len(containers)
    if total == 0:
        # диагностируем, какие шапки вообще видны
        union_all = (
            "(//div[contains(@class,'ant-table-container')]"
            " | //div[contains(@class,'ant-table-wrapper')]//div[contains(@class,'ant-table')]"
            " | //div[contains(@class,'ant-table')][.//table])"
        )
        visible = [el for el in drv.find_elements(By.XPATH, union_all) if el.is_displayed()]
        seen_headers = []
        for el in visible:
            try:
                seen_headers.append(_headers_text(el))
            except Exception:
                continue
        raise AssertionError(
            "Нет видимых таблиц с требуемыми столбцами (строгое совпадение и наличие строк). "
            f"Искали: [{_norm(search_col)}] и [{_norm(click_col)}]. "
            f"Видимые шапки: {seen_headers}"
        )

    _log(f"[ROW-ACTION] strict containers matched (with rows): {total}")

    # приоритетный индекс в пределах отфильтрованного списка (DOM-порядок сохранён)
    start_idx = table_index if isinstance(table_index, int) and 1 <= table_index <= total else 1
    tried = set([start_idx])

    try:
        if _try_on_container(containers[start_idx - 1], start_idx):
            return
    except Exception as e:
        _log(f"[ROW-ACTION] container #{start_idx} exception: {type(e).__name__}: {e}", level="WARN")

    for i in range(1, total + 1):
        if i in tried:
            continue
        try:
            if _try_on_container(containers[i - 1], i):
                return
        except Exception as e:
            _log(f"[ROW-ACTION] container #{i} exception: {type(e).__name__}: {e}", level="WARN")

    raise AssertionError(f"Не удалось выполнить клик ни в одной из {total} подходящих таблиц (strict headers).")



@keyword("Logpass")
def logpass(login: str, password: str, timeout: int = 20):
    """
    Ввод логина и пароля и сабмит формы.
    Robot:  Logpass    <логин>    <пароль>
    """
    drv = _drv()
    start_ts = time.time()
    _log(f"[LOGPASS] login='{login}', timeout={timeout}")

    # Кандидаты локаторов
    user_xp = [
        "//input[(@name='login' or @id='login' or @autocomplete='username') and not(@type='hidden')]",
        "//input[(@name='username' or @id='username' or @type='email') and not(@type='hidden')]",
        "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login') and not(@type='hidden')]",
        "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'username') and not(@type='hidden')]",
        "(//input[@type='text' or @type='email'])[1]",
    ]
    pass_xp = [
        "//input[@type='password' and not(@disabled)]",
        "//input[(@name='password' or @id='password' or @autocomplete='current-password') and not(@type='hidden')]",
        "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'password') and not(@type='hidden')]",
    ]

    def _find_pair_in_context(ctx):
        usr_el = None
        pwd_el = None
        # Ищем username
        for xp in user_xp:
            try:
                nodes = ctx.find_elements(By.XPATH, xp)
            except Exception:
                nodes = []
            for n in nodes:
                try:
                    if _visible(n) and n.is_enabled():
                        usr_el = n
                        break
                except Exception:
                    continue
            if usr_el:
                break
        # Ищем password
        for xp in pass_xp:
            try:
                nodes = ctx.find_elements(By.XPATH, xp)
            except Exception:
                nodes = []
            for n in nodes:
                try:
                    if _visible(n) and n.is_enabled():
                        pwd_el = n
                        break
                except Exception:
                    continue
            if pwd_el:
                break
        return usr_el, pwd_el

    # 1) Пытаемся найти поля в корне
    username, password_el = None, None
    while time.time() - start_ts < timeout / 2:
        username, password_el = _find_pair_in_context(drv)
        if username and password_el:
            break
        time.sleep(0.25)

    # 2) Если не нашли — пробуем каждый iframe
    if not (username and password_el):
        frames = drv.find_elements(By.TAG_NAME, "iframe")
        for fr in frames:
            try:
                drv.switch_to.frame(fr)
                t0 = time.time()
                while time.time() - t0 < 6:
                    username, password_el = _find_pair_in_context(drv)
                    if username and password_el:
                        _log("[LOGPASS] fields found in iframe")
                        break
                    time.sleep(0.25)
                if username and password_el:
                    break
            except Exception:
                pass
            finally:
                try:
                    drv.switch_to.default_content()
                except Exception:
                    pass

    if not (username and password_el):
        raise AssertionError("[LOGPASS] Не нашёл видимые поля логина/пароля")

    # Ввод логина
    try:
        _scroll_el_into_view(username)
        username.click()
    except Exception:
        pass
    try:
        username.clear()
    except Exception:
        pass
    try:
        drv.execute_script(
            "if(arguments[0].readOnly!==true){arguments[0].value='';"
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));}", username)
    except Exception:
        pass
    username.send_keys(_norm(login))

    # Ввод пароля
    try:
        _scroll_el_into_view(password_el)
        password_el.click()
    except Exception:
        pass
    try:
        password_el.clear()
    except Exception:
        pass
    try:
        drv.execute_script(
            "if(arguments[0].readOnly!==true){arguments[0].value='';"
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));}", password_el)
    except Exception:
        pass
    password_el.send_keys(password)

    # Поиск кнопки submit (сначала в ближайшей форме)
    submit_btn = None
    form = None
    try:
        forms = password_el.find_elements(By.XPATH, "ancestor::form[1]")
        if forms:
            form = forms[0]
            # Кнопка внутри формы
            for xp in [
                ".//button[@type='submit' and not(@disabled)]",
                ".//input[@type='submit' and not(@disabled)]",
                ".//button[normalize-space(.)='Login' or normalize-space(.)='Sign in' or normalize-space(.)='Войти']",
                ".//button[.//span[normalize-space(.)='Login' or normalize-space(.)='Sign in' or normalize-space(.)='Войти']]",
            ]:
                try:
                    btns = form.find_elements(By.XPATH, xp)
                except Exception:
                    btns = []
                for b in btns:
                    if _visible(b) and b.is_enabled():
                        submit_btn = b
                        break
                if submit_btn:
                    break
    except Exception:
        pass

    # Глобальный поиск, если в форме не нашли
    if submit_btn is None:
        for xp in [
            "//button[@type='submit' and not(@disabled)]",
            "//input[@type='submit' and not(@disabled)]",
            "//button[normalize-space(.)='Login' or normalize-space(.)='Sign in' or normalize-space(.)='Войти']",
            "//button[.//span[normalize-space(.)='Login' or normalize-space(.)='Sign in' or normalize-space(.)='Войти']]",
        ]:
            try:
                btns = drv.find_elements(By.XPATH, xp)
            except Exception:
                btns = []
            for b in btns:
                if _visible(b) and b.is_enabled():
                    submit_btn = b
                    break
            if submit_btn:
                break

    # Сабмит
    if submit_btn is not None:
        try:
            _scroll_el_into_view(submit_btn)
            WebDriverWait(drv, 5).until(EC.element_to_be_clickable(submit_btn))
            submit_btn.click()
        except Exception:
            drv.execute_script("arguments[0].click();", submit_btn)
        _log("[LOGPASS] submit button clicked")
        return True

    # Если кнопки нет — submit через форму/Enter
    if form is not None:
        try:
            drv.execute_script("arguments[0].submit();", form)
            _log("[LOGPASS] form.submit()")
            return True
        except Exception:
            pass

    try:
        password_el.submit()
        _log("[LOGPASS] input.submit()")
        return True
    except Exception:
        pass

    # Крайний случай — Enter по паролю
    drv.execute_script(
        "var e=new KeyboardEvent('keydown',{key:'Enter',keyCode:13,which:13,bubbles:true});"
        "arguments[0].dispatchEvent(e);", password_el)
    _log("[LOGPASS] dispatched Enter")
    return True


@keyword("Wait For AntD Notification")
def wait_for_antd_notification(text: str,
                               timeout: str = "5 s",
                               exact: bool = True,
                               position: str = "topRight"):
    """
    Wait For AntD Notification    Access is allowed    6 s
    """
    drv = _drv()
    try:
        drv.switch_to.default_content()
    except Exception:
        pass

    # парсинг таймаута "5 s" / "500 ms" / "2 min" / 7
    t = str(timeout).strip().lower().replace(" ", "")
    if t.endswith("ms"):
        timeout_secs = float(t[:-2]) / 1000.0
    elif t.endswith("min"):
        timeout_secs = float(t[:-3]) * 60.0
    elif t.endswith("m"):
        timeout_secs = float(t[:-1]) * 60.0
    elif t.endswith("s"):
        timeout_secs = float(t[:-1])
    else:
        timeout_secs = float(t)

    txt = text.strip()
    pos_css = f".ant-notification.ant-notification-{position}" if position else ".ant-notification"

    js_check = """
return (function(txt, exact, posSel){
  const norm = s => (s||'').replace(/\\s+/g,' ').trim();
  const stacks = document.querySelectorAll(posSel);
  for (const stack of stacks){
    const msgs = stack.querySelectorAll("div.ant-notification-notice-message");
    for (const m of msgs){
      const t = norm(m.textContent);
      if ((exact && t === txt) || (!exact && t.includes(txt))) return true;
    }
  }
  return false;
})(arguments[0], arguments[1], arguments[2]);
"""

    _log(f"[ANTD-NOTICE] wait appear: '{txt}', exact={exact}, pos={position}, timeout={timeout}")
    WebDriverWait(drv, timeout_secs, poll_frequency=0.1).until(
        lambda d: d.execute_script(js_check, txt, bool(exact), pos_css) is True
    )
    return True



@keyword("Delete GLMs Where IOC Not Zero")
def delete_glms_where_ioc_not_zero(timeout: int = 300, table_index: int | None = None):
    """
    Удаляет ВСЕ GLM в таблице, где столбец IOC != '0'.
    - Столбцы: Actions / IOC / GLM (классами ячеек либо по тексту шапки)
    - Для каждой подходящей строки: кликает Delete -> подтверждает Yes (ant-popconfirm)
    - Ждёт тост: "GLM <GLM>(IOC <IOC>) deleted successfully"
    Делает многократные ПОЛНЫЕ проходы: сверху-вниз со скроллом; если были удаления — снова вверх и заново.
    """
    drv = _drv()
    end_overall = time.time() + float(timeout)

    def _norm(s: str) -> str:
        return " ".join((s or "").split())

    # --- 1) Найти нужную таблицу ---
    def _headers_text(container):
        ths = container.find_elements(By.CSS_SELECTOR, ".ant-table-header th")
        return [_norm(th.text) for th in ths]

    containers = drv.find_elements(By.CSS_SELECTOR, "div.ant-table-container")
    targets = []
    for c in containers:
        try:
            if not c.is_displayed():
                continue
            hdrs = set(_headers_text(c))
            if {"Actions", "IOC", "GLM"}.issubset(hdrs):
                targets.append(c)
        except Exception:
            continue
    if not targets:
        raise AssertionError("[GLM-DEL] Не нашёл видимую таблицу с заголовками Actions/IOC/GLM")

    table = targets[0] if not table_index else targets[table_index - 1]

    # тело (может отсутствовать как отдельный скролл-контейнер)
    try:
        body = table.find_element(By.CSS_SELECTOR, "div.ant-table-body")
    except Exception:
        body = table

    # --- 2) Хелперы прокрутки и поиска кандидата ---
    js_find_candidate = """
return (function(container){
  const norm = s => (s||'').replace(/\\s+/g,' ').trim();
  const rows = container.querySelectorAll('tbody tr.ant-table-row, div.ant-table-row');
  for (const row of rows){
    const iocCell = row.querySelector('td.IOC, div.IOC, td[class*="IOC"], div[class*="IOC"]');
    if(!iocCell) continue;
    const ioc = norm(iocCell.textContent);
    if(!ioc || /^0+(\\.0+)?$/.test(ioc)) continue;
    const act = row.querySelector('td.ACTIONS, div.ACTIONS, [class*="ACTIONS"]');
    if(!act) continue;
    let del = Array.from(act.querySelectorAll('a,button')).find(e => norm(e.textContent).toLowerCase() === 'delete');
    if(!del) continue;
    const glmCell = row.querySelector('td.GLM, div.GLM, [class*="GLM"]');
    const glm = norm(glmCell ? glmCell.textContent : '');
    return [del, ioc, glm];
  }
  return null;
})(arguments[0]);
"""

    def _scroll_to_top():
        try:
            drv.execute_script("arguments[0].scrollTop = 0;", body)
            time.sleep(0.15)
        except Exception:
            pass

    def _scroll_step_down() -> bool:
        """Скроллит вниз на ~1 экран. Возвращает True, если позиция увеличилась."""
        try:
            cur = drv.execute_script("return arguments[0].scrollTop;", body)
            ch = drv.execute_script("return arguments[0].clientHeight;", body)
            sh = drv.execute_script("return arguments[0].scrollHeight;", body)
            new_top = min(cur + (ch * 0.9), sh)
            drv.execute_script("arguments[0].scrollTop = arguments[0];", new_top)
            time.sleep(0.15)
            cur2 = drv.execute_script("return arguments[0].scrollTop;", body)
            return cur2 > cur + 1
        except Exception:
            # контейнер не скроллится
            return False

    def _wait_toast_exact(msg_text: str, sec: float = 10.0):
        drv.switch_to.default_content()
        js_check = """
return (function(txt){
  const norm = s => (s||'').replace(/\\s+/g,' ').trim();
  const stacks = document.querySelectorAll(".ant-notification");
  for (const s of stacks){
    const msgs = s.querySelectorAll("div.ant-notification-notice-message");
    for (const m of msgs){
      if (norm(m.textContent) === norm(txt)) return true;
    }
  }
  return false;
})(arguments[0]);
"""
        WebDriverWait(drv, sec, poll_frequency=0.1).until(
            lambda d: d.execute_script(js_check, msg_text) is True
        )

    # --- 3) Главный цикл: полные проходы, пока есть удаления ---
    total_deleted = 0
    pass_num = 0

    while time.time() < end_overall:
        pass_num += 1
        deleted_this_pass = 0
        _log(f"[GLM-DEL] PASS #{pass_num}: старт сверху")

        _scroll_to_top()

        reached_bottom = False
        while time.time() < end_overall and not reached_bottom:
            candidate = None
            try:
                candidate = drv.execute_script(js_find_candidate, body)
            except Exception:
                candidate = None

            if candidate:
                del_el, ioc_val, glm_val = candidate
                ioc_val = _norm(ioc_val)
                glm_val = _norm(glm_val)
                # если GLM пуст — прокрутимся и продолжим (не наш кандидат)
                if not glm_val:
                    _ = _scroll_step_down()
                    continue

                msg_text = f"GLM {glm_val}(IOC {ioc_val}) deleted successfully"
                _log(f"[GLM-DEL] PASS #{pass_num}: delete GLM={glm_val}, IOC={ioc_val}")

                try:
                    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", del_el)
                except Exception:
                    pass
                try:
                    del_el.click()
                except Exception:
                    drv.execute_script("arguments[0].click();", del_el)

                # подтверждение Yes
                drv.switch_to.default_content()
                yes_btn = WebDriverWait(drv, 6, poll_frequency=0.1).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'ant-popconfirm')]//button[.//span[normalize-space()='Yes']]"))
                )
                try:
                    yes_btn.click()
                except Exception:
                    drv.execute_script("arguments[0].click();", yes_btn)

                # ждём тост
                _wait_toast_exact(msg_text, sec=10.0)

                deleted_this_pass += 1
                total_deleted += 1
                _log(f"[GLM-DEL] PASS #{pass_num}: удалено {deleted_this_pass} (сумма {total_deleted})")

                # маленькая пауза на перерисовку
                time.sleep(0.2)
                # НЕ скроллим — пытаемся удалить ещё в текущем вьюпорте
                continue

            # кандидата нет в текущем экране — шагаем вниз
            moved = _scroll_step_down()
            if not moved:
                reached_bottom = True

        if deleted_this_pass == 0:
            _log(f"[GLM-DEL] PASS #{pass_num}: кандидатов не найдено — завершение. Всего удалено: {total_deleted}")
            return total_deleted

        # были удаления — делаем ещё один полный проход (сверху), вдруг остались выше
        _log(f"[GLM-DEL] PASS #{pass_num}: удалено {deleted_this_pass}, начинаю следующий проход")

    _log(f"[GLM-DEL] Таймаут: всего удалено {total_deleted}")
    return total_deleted
    
@keyword("Delete Non-Zero IOCs")
def delete_non_zero_iocs(timeout: int = 300, table_index: int | None = None):
    """
    Удаляет ВСЕ IOC, у которых в столбце IOC значение != '0'.
    Алгоритм:
      1) Находит видимую AntD-таблицу с колонкой IOC.
      2) Делает полный проход сверху вниз (со скроллом) и собирает уникальные значения IOC != '0'.
      3) Для каждого такого значения:
         - жмёт кнопку "Delete IOC" на тулбаре таблицы,
         - в модалке открывает селект IOC, выбирает нужное число, жмёт OK,
         - ждёт тост "IOC <N> deleted successfully".
      4) Повторяет, пока значения IOC != '0' не закончатся, либо не истечёт timeout.
    Возвращает количество удалённых IOC.
    """
    drv = _drv()
    end_overall = time.time() + float(timeout)

    def _norm(s: str) -> str:
        return " ".join((s or "").split())

    # --- 1) Найти нужную таблицу (видимую) ---
    containers = drv.find_elements(By.CSS_SELECTOR, "div.ant-table-container")
    targets = []
    for c in containers:
        try:
            if not c.is_displayed():
                continue
            # таблица должна иметь колонку IOC в шапке
            th_ioc = c.find_elements(By.CSS_SELECTOR, ".ant-table-header th.IOC, .ant-table-header th[aria-label='IOC']")
            if th_ioc:
                targets.append(c)
        except Exception:
            continue
    if not targets:
        raise AssertionError("[IOC-DEL] Не нашёл видимую таблицу с колонкой IOC")

    table = targets[0] if not table_index else targets[table_index - 1]

    # родительский .ant-table (для тулбара "Delete IOC")
    table_root = table.find_element(By.XPATH, "./ancestor::div[contains(@class,'ant-table')][1]")

    # тело (может быть как отдельный скролл-контейнер)
    try:
        body = table.find_element(By.CSS_SELECTOR, "div.ant-table-body")
    except Exception:
        body = table

    # --- 2) Хелперы прокрутки, сбора IOC и ожидания тостов ---
    def _scroll_to_top():
        try:
            drv.execute_script("arguments[0].scrollTop = 0;", body)
            time.sleep(0.15)
        except Exception:
            pass

    def _scroll_step_down() -> bool:
        """Скроллит вниз на ~1 экран. Возвращает True, если позиция увеличилась."""
        try:
            cur = drv.execute_script("return arguments[0].scrollTop;", body)
            ch  = drv.execute_script("return arguments[0].clientHeight;", body)
            sh  = drv.execute_script("return arguments[0].scrollHeight;", body)
            new_top = min(cur + (ch * 0.9), sh)
            drv.execute_script("arguments[0].scrollTop = arguments[1];", body, new_top)
            time.sleep(0.15)
            cur2 = drv.execute_script("return arguments[0].scrollTop;", body)
            return cur2 > cur + 1
        except Exception:
            return False

    js_collect_nonzero_iocs = """
return (function(container){
  const norm = s => (s||'').replace(/\\s+/g,' ').trim();
  const out = new Set();
  const rows = container.querySelectorAll('tbody tr.ant-table-row, tr.ant-table-row');
  for (const r of rows){
    const cell = r.querySelector('td.IOC, div.IOC, td[aria-label="IOC"], td[class*="IOC"]');
    if(!cell) continue;
    const v = norm(cell.textContent);
    if (v && v !== '0') out.add(v);
  }
  return Array.from(out);
})(arguments[0]);
"""

    def _collect_all_nonzero_iocs() -> list[str]:
        _scroll_to_top()
        found = set()
        reached_bottom = False
        while not reached_bottom and time.time() < end_overall:
            try:
                vals = drv.execute_script(js_collect_nonzero_iocs, body) or []
                for v in vals:
                    if v and v != '0':
                        found.add(_norm(v))
            except Exception:
                pass
            moved = _scroll_step_down()
            if not moved:
                reached_bottom = True
        return sorted(found, key=lambda x: int(x) if x.isdigit() else x)

    def _wait_toast_exact(msg_text: str, sec: float = 10.0):
        # AntD-notification живёт в document.body вне корней приложения
        try:
            drv.switch_to.default_content()
        except Exception:
            pass
        js_check = """
return (function(txt){
  const norm = s => (s||'').replace(/\\s+/g,' ').trim();
  const stacks = document.querySelectorAll(".ant-notification");
  for (const s of stacks){
    const msgs = s.querySelectorAll("div.ant-notification-notice-message");
    for (const m of msgs){
      if (norm(m.textContent) === norm(txt)) return true;
    }
  }
  return false;
})(arguments[0]);
"""
        WebDriverWait(drv, sec, poll_frequency=0.1).until(
            lambda d: d.execute_script(js_check, msg_text) is True
        )

    def _click(elem):
        try:
            elem.click()
        except Exception:
            try:
                drv.execute_script("arguments[0].click();", elem)
            except Exception:
                raise

    # --- 3) Главный цикл: пока остаются IOC != '0' ---
    total_deleted = 0
    pass_num = 0

    while time.time() < end_overall:
        pass_num += 1
        _log(f"[IOC-DEL] PASS #{pass_num}: собираю значения IOC != 0")
        nonzero_iocs = _collect_all_nonzero_iocs()
        if not nonzero_iocs:
            _log(f"[IOC-DEL] PASS #{pass_num}: кандидатов нет — завершение. Удалено: {total_deleted}")
            return total_deleted

        _log(f"[IOC-DEL] PASS #{pass_num}: найдено {len(nonzero_iocs)} значений: {', '.join(nonzero_iocs)}")

        for ioc_val in nonzero_iocs:
            if time.time() >= end_overall:
                break

            # Кнопка Delete IOC в тулбаре таблицы
            delete_btn = WebDriverWait(table_root, 10, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-table-title')]//button[.//span[normalize-space()='Delete IOC']]"))
            )
            try:
                drv.execute_script("arguments[0].scrollIntoView({block:'center'});", delete_btn)
            except Exception:
                pass
            _click(delete_btn)

            # Модалка "Delete IOC"
            modal = WebDriverWait(drv, 10, poll_frequency=0.1).until(
                EC.visibility_of_element_located((By.XPATH, "//div[contains(@class,'ant-modal')][.//div[contains(@class,'ant-modal-title') and normalize-space()='Delete IOC']]"))
            )

            # Открыть селект IOC
            selector = WebDriverWait(modal, 5, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, ".//label[@for='ioc']/following::div[contains(@class,'ant-select')][1]//div[contains(@class,'ant-select-selector')]"))
            )
            _click(selector)

            # Выбрать нужное значение в выпадающем списке
            # Кликаем по опции с точным текстом ioc_val
            opt = WebDriverWait(drv, 10, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, f"//div[contains(@class,'ant-select-dropdown')]//div[contains(@class,'ant-select-item-option-content')][normalize-space()='{ioc_val}']"))
            )
            _click(opt)

            # Нажать OK
            ok_btn = WebDriverWait(modal, 5, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-modal-footer')]//button[.//span[normalize-space()='OK']]"))
            )
            _click(ok_btn)

            # Ждём тост
            toast_text = f"IOC {ioc_val} deleted successfully"
            _wait_toast_exact(toast_text, sec=12.0)

            total_deleted += 1
            _log(f"[IOC-DEL] Удалён IOC={ioc_val} (итого {total_deleted})")
            time.sleep(0.2)  # дать DOM перерисоваться

        # после прохода повторяем сбор — вдруг остались новые/проскролленные значения
        _log(f"[IOC-DEL] PASS #{pass_num}: завершён, всего удалено {total_deleted}; проверяю ещё раз")

    _log(f"[IOC-DEL] Таймаут по общей операции. Всего удалено {total_deleted}")
    return total_deleted


@keyword("Add IOC")
def add_ioc(count: int = 1, timeout: int = 300, table_index: int | None = None):
    """
    Add IOC    <count>
    Логика на каждую итерацию:
      - Находит max(IOC) в таблице.
      - Нажимает "Add IOC" → подтверждает в окне "OK".
      - Ждёт тост "IOC N added successfully".
      - Проверяет, что в таблице появилась строка с IOC == max_before + 1.
      - Сравнивает N из тоста с (max_before + 1). Иначе — AssertionError.
    Возвращает число успешно добавленных.
    """
    drv = _drv()
    end_overall = time.time() + float(timeout)
    total_done = 0

    # ---------- локаторы и базовые операции ----------
    def _norm(s: str) -> str:
        return " ".join((s or "").split())

    def _click(el):
        try:
            el.click()
        except Exception:
            drv.execute_script("arguments[0].click();", el)

    # ищем таблицу с колонкой IOC (видимую). Если несколько — table_index (1-based)
    def _find_table():
        containers = drv.find_elements(By.CSS_SELECTOR, "div.ant-table-container")
        matches = []
        for c in containers:
            try:
                if not c.is_displayed():
                    continue
                ths = c.find_elements(By.CSS_SELECTOR, ".ant-table-header th")
                headers = [_norm(th.text) for th in ths]
                if "IOC" in headers:
                    matches.append((c, headers))
            except Exception:
                continue
        if not matches:
            raise AssertionError("[ADD-IOC] Не нашёл видимую таблицу с колонкой 'IOC'")
        if table_index:
            idx = table_index - 1
            if idx < 0 or idx >= len(matches):
                raise AssertionError(f"[ADD-IOC] table_index={table_index} вне диапазона (найдено {len(matches)} таблиц)")
            return matches[idx][0], matches[idx][1]
        return matches[0][0], matches[0][1]

    table, headers = _find_table()
    # тело скролла (если нет — работаем по самому контейнеру)
    try:
        body = table.find_element(By.CSS_SELECTOR, "div.ant-table-body")
    except Exception:
        body = table

    # тулбар текущей таблицы для кнопки Add IOC
    table_root = table.find_element(By.XPATH, "./ancestor::div[contains(@class,'ant-table')][1]")

    # ---------- скролл и обход строк ----------
    def _scroll_to_top():
        try:
            drv.execute_script("arguments[0].scrollTop = 0;", body)
            time.sleep(0.12)
        except Exception:
            pass

    def _scroll_step_down() -> bool:
        try:
            cur = drv.execute_script("return arguments[0].scrollTop;", body)
            # мгновенно в самый низ
            drv.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", body)
            time.sleep(0.06)
            cur2 = drv.execute_script("return arguments[0].scrollTop;", body)
            return cur2 > cur + 1
        except Exception:
            return False

    # берём индекс столбца IOC из шапки (fallback, если нет классов ячеек)
    def _ioc_col_index() -> int:
        try:
            ths = table.find_elements(By.CSS_SELECTOR, ".ant-table-header th")
            for i, th in enumerate(ths):
                if _norm(th.text) == "IOC":
                    return i
        except Exception:
            pass
        return -1

    ioc_idx = _ioc_col_index()

    # макс. IOC по всей таблице (со скроллом)
    def _get_max_ioc() -> int:
        _scroll_to_top()
        max_val = None
        while True:
            try:
                if ioc_idx >= 0:
                    # по индексу колонки
                    rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
                    for r in rows:
                        tds = r.find_elements(By.CSS_SELECTOR, "td")
                        if ioc_idx < len(tds):
                            v = _norm(tds[ioc_idx].text)
                            if v.isdigit():
                                val = int(v)
                                max_val = val if max_val is None or val > max_val else max_val
                else:
                    # по классам/атрибутам
                    cells = body.find_elements(By.CSS_SELECTOR, "td.IOC, td[aria-label='IOC'], td[class*='IOC']")
                    for c in cells:
                        v = _norm(c.text)
                        if v.isdigit():
                            val = int(v)
                            max_val = val if max_val is None or val > max_val else max_val
            except Exception:
                pass
            if not _scroll_step_down():
                break
        return 0 if max_val is None else max_val

    # поиск строки с конкретным числом IOC (со скроллом; true/false)
    def _table_has_ioc(target: int, sec: float = 12.0) -> bool:
        dead = time.time() + sec
        while time.time() < dead:
            _scroll_to_top()
            found = False
            while True:
                try:
                    if ioc_idx >= 0:
                        rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
                        for r in rows:
                            tds = r.find_elements(By.CSS_SELECTOR, "td")
                            if ioc_idx < len(tds) and _norm(tds[ioc_idx].text) == str(target):
                                found = True
                                break
                    else:
                        cells = body.find_elements(By.CSS_SELECTOR, "td.IOC, td[aria-label='IOC'], td[class*='IOC']")
                        for c in cells:
                            if _norm(c.text) == str(target):
                                found = True
                                break
                except Exception:
                    pass
                if found:
                    return True
                if not _scroll_step_down():
                    break
            time.sleep(0.2)
        return False

    # ожидание тоста "IOC N added successfully" (возвращает N как int)
    def _wait_added_toast(expected: int | None, sec: float = 15.0) -> int:
        try:
            drv.switch_to.default_content()
        except Exception:
            pass
        expected_text = f"IOC {expected} added successfully" if expected is not None else None

        js_find_toast = """
return (function(expectedTxt){
  const norm = s => (s||'').replace(/\\s+/g,' ').trim();
  const stacks = document.querySelectorAll('.ant-notification');
  let last = null;
  for (const s of stacks){
    const msgs = s.querySelectorAll('div.ant-notification-notice-message');
    for (const m of msgs){
      const t = norm(m.textContent);
      if (t.endsWith('added successfully') && t.startsWith('IOC ')){
        if (expectedTxt && t === expectedTxt) return t;
        // если expectedTxt не задан — вернём первый подходящий
        if (!expectedTxt) last = t;
      }
    }
  }
  return expectedTxt ? null : last;
})(arguments[0]);
"""
        deadline = time.time() + sec
        while time.time() < deadline:
            try:
                t = drv.execute_script(js_find_toast, expected_text)
            except Exception:
                t = None
            if t:
                # парсим число
                try:
                    n = int(t.split(" ")[1])
                    return n
                except Exception:
                    raise AssertionError(f"[ADD-IOC] Некорректный формат тоста: {t}")
            time.sleep(0.1)
        raise AssertionError(f"[ADD-IOC] Не дождался тоста 'IOC {expected} added successfully'")

    # найти кнопку Add IOC в тулбаре текущей таблицы
    def _find_add_button():
        return WebDriverWait(table_root, 10, poll_frequency=0.1).until(
            EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-table-title')]//button[.//span[normalize-space()='Add IOC']]"))
        )

    # подтвердить OK в модалке/поповере
    def _confirm_ok():
        try:
            drv.switch_to.default_content()
        except Exception:
            pass
        # ждём модалку или поповер
        container = WebDriverWait(drv, 8, poll_frequency=0.1).until(
            lambda d: next((m for m in d.find_elements(By.XPATH, "//div[contains(@class,'ant-modal') and .//div[contains(@class,'ant-modal-title')]]") if m.is_displayed()), None)
            or next((p for p in d.find_elements(By.XPATH, "//div[contains(@class,'ant-popconfirm')]") if p.is_displayed()), None)
        )
        # кнопка OK/Yes
        try:
            ok = WebDriverWait(container, 5, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, ".//button[.//span[normalize-space()='OK' or normalize-space()='Yes']]"))
            )
        except Exception:
            ok = WebDriverWait(container, 3, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, ".//button[contains(@class,'ant-btn-primary')]"))
            )
        _click(ok)
        # ждём закрытия окна
        WebDriverWait(drv, 8, poll_frequency=0.1).until(EC.invisibility_of_element(container))

    # ---------- основной цикл ----------
    for i in range(int(max(0, count))):
        if time.time() >= end_overall:
            _log(f"[ADD-IOC] Общий таймаут. Выполнено {total_done} из {count}")
            break

        # 1) базовый максимум
        base_max = _get_max_ioc()
        expected = base_max + 1
        _log(f"[ADD-IOC] Итерация {i+1}/{count}: текущий max(IOC)={base_max}, ожидаю новый={expected}")

        # 2) Add IOC
        add_btn = _find_add_button()
        try:
            drv.execute_script("arguments[0].scrollIntoView({block:'center'});", add_btn)
        except Exception:
            pass
        _click(add_btn)
        _confirm_ok()

        # 3) ждём тост про добавление именно ожидаемого числа
        toast_num = _wait_added_toast(expected, sec=20.0)
        _log(f"[ADD-IOC] Тост получен: IOC {toast_num} added successfully")

        # 4) проверяем появление строки с expected
        if not _table_has_ioc(expected, sec=20.0):
            raise AssertionError(f"[ADD-IOC] В таблице не появилась строка с IOC={expected} после добавления")

        # 5) сравнение чисел
        if toast_num != expected:
            raise AssertionError(f"[ADD-IOC] Несоответствие чисел: тост={toast_num}, ожидалось={expected}")

        total_done += 1
        _log(f"[ADD-IOC] Итерация {i+1}: OK (IOC={expected}). Всего выполнено: {total_done}")
        time.sleep(0.25)  # дать DOM успокоиться

    return total_done
    
@keyword("Add GLM")
def add_glm(count: int = 1, timeout: int = 600, table_index: int | None = None):
    """
    Add GLM    <count>
    Для каждого IOC != 0 добавляет GLM указанное количество раз, проверяя тост
    'GLM N(IOC M) added successfully' и появление строки (IOC=M, GLM=N) в таблице.
    """
    drv = _drv()
    end_overall = time.time() + float(timeout)
    total_done = 0

    # -------- utils --------
    def _norm(s: str) -> str:
        return " ".join((s or "").split())

    def _click(el):
        try:
            el.click()
        except Exception:
            drv.execute_script("arguments[0].click();", el)

    # -------- таблица/тело/шапки --------
    def _find_table():
        containers = drv.find_elements(By.CSS_SELECTOR, "div.ant-table-container")
        matches = []
        for c in containers:
            try:
                if not c.is_displayed():
                    continue
                ths = c.find_elements(By.CSS_SELECTOR, ".ant-table-header th")
                headers = [_norm(th.text) for th in ths]
                if "IOC" in headers:
                    matches.append((c, headers))
            except Exception:
                continue
        if not matches:
            raise AssertionError("[ADD-GLM] Не нашёл видимую таблицу с колонкой 'IOC'")
        if table_index:
            i = table_index - 1
            if i < 0 or i >= len(matches):
                raise AssertionError(f"[ADD-GLM] table_index={table_index} вне диапазона (найдено {len(matches)} таблиц)")
            return matches[i][0], matches[i][1]
        return matches[0][0], matches[0][1]

    table, headers = _find_table()
    try:
        body = table.find_element(By.CSS_SELECTOR, "div.ant-table-body")
    except Exception:
        body = table

    table_root = table.find_element(By.XPATH, "./ancestor::div[contains(@class,'ant-table')][1]")

    def _col_index(name: str) -> int:
        try:
            ths = table.find_elements(By.CSS_SELECTOR, ".ant-table-header th")
            for i, th in enumerate(ths):
                if _norm(th.text) == name:
                    return i
        except Exception:
            pass
        return -1

    ioc_idx  = _col_index("IOC")
    glm_idx  = _col_index("GLM")
    ucode_idx = _col_index("Unique Code")

    # -------- скролл --------
    def _scroll_to_top():
        try:
            drv.execute_script("arguments[0].scrollTop = 0;", body)
            time.sleep(0.12)
        except Exception:
            pass

    def _scroll_step_down() -> bool:
        try:
            cur = drv.execute_script("return arguments[0].scrollTop;", body)
            # мгновенно в самый низ
            drv.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", body)
            time.sleep(0.06)
            cur2 = drv.execute_script("return arguments[0].scrollTop;", body)
            return cur2 > cur + 1
        except Exception:
            return False

    # -------- чтение таблицы --------
    def _collect_nonzero_iocs() -> list[str]:
        _scroll_to_top()
        found = set()
        while True:
            try:
                if ioc_idx >= 0:
                    rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
                    for r in rows:
                        tds = r.find_elements(By.CSS_SELECTOR, "td")
                        if ioc_idx < len(tds):
                            v = _norm(tds[ioc_idx].text)
                            if v and v != "0":
                                found.add(v)
                else:
                    cells = body.find_elements(By.CSS_SELECTOR, "td.IOC, td[aria-label='IOC'], td[class*='IOC']")
                    for c in cells:
                        v = _norm(c.text)
                        if v and v != "0":
                            found.add(v)
            except Exception:
                pass
            if not _scroll_step_down():
                break
        return sorted(found, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))

    def _get_max_glm_for_ioc(ioc_val: str) -> int | None:
        _scroll_to_top()
        max_val = None
        while True:
            try:
                rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
                for r in rows:
                    # фильтр по IOC
                    ioc_ok = False
                    if ioc_idx >= 0:
                        tds = r.find_elements(By.CSS_SELECTOR, "td")
                        if ioc_idx < len(tds) and _norm(tds[ioc_idx].text) == ioc_val:
                            ioc_ok = True
                    else:
                        cell = None
                        for sel in ("td.IOC", "td[aria-label='IOC']", "td[class*='IOC']"):
                            try:
                                cell = r.find_element(By.CSS_SELECTOR, sel)
                                break
                            except Exception:
                                continue
                        if cell is not None and _norm(cell.text) == ioc_val:
                            ioc_ok = True
                    if not ioc_ok:
                        continue
                    # читаем GLM
                    v = ""
                    if glm_idx >= 0:
                        tds = r.find_elements(By.CSS_SELECTOR, "td")
                        if glm_idx < len(tds):
                            v = _norm(tds[glm_idx].text)
                    else:
                        cell = None
                        for sel in ("td.GLM", "td[aria-label='GLM']", "td[class*='GLM']"):
                            try:
                                cell = r.find_element(By.CSS_SELECTOR, sel)
                                break
                            except Exception:
                                continue
                        v = _norm(cell.text) if cell else ""
                    if v.isdigit():
                        val = int(v)
                        max_val = val if max_val is None or val > max_val else max_val
            except Exception:
                pass
            if not _scroll_step_down():
                break
        return max_val

    def _table_has_pair(ioc_val: str, glm_val: int, sec: float = 20.0) -> bool:
        deadline = time.time() + sec
        target_glm = str(glm_val)
        while time.time() < deadline:
            _scroll_to_top()
            found = False
            while True:
                try:
                    rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
                    for r in rows:
                        # IOC
                        ioc_text = ""
                        if ioc_idx >= 0:
                            tds = r.find_elements(By.CSS_SELECTOR, "td")
                            if ioc_idx < len(tds):
                                ioc_text = _norm(tds[ioc_idx].text)
                        else:
                            try:
                                ioc_text = _norm(r.find_element(By.CSS_SELECTOR, "td.IOC, td[aria-label='IOC'], td[class*='IOC']").text)
                            except Exception:
                                ioc_text = ""
                        if ioc_text != ioc_val:
                            continue
                        # GLM
                        glm_text = ""
                        if glm_idx >= 0:
                            tds = r.find_elements(By.CSS_SELECTOR, "td")
                            if glm_idx < len(tds):
                                glm_text = _norm(tds[glm_idx].text)
                        else:
                            try:
                                glm_text = _norm(r.find_element(By.CSS_SELECTOR, "td.GLM, td[aria-label='GLM'], td[class*='GLM']").text)
                            except Exception:
                                glm_text = ""
                        if glm_text == target_glm:
                            found = True
                            break
                except Exception:
                    pass
                if found:
                    return True
                if not _scroll_step_down():
                    break
            time.sleep(0.2)
        return False

    def _collect_all_unique_codes() -> set[str]:
        if ucode_idx < 0:
            return set()
        s = set()
        _scroll_to_top()
        while True:
            try:
                rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
                for r in rows:
                    tds = r.find_elements(By.CSS_SELECTOR, "td")
                    if ucode_idx < len(tds):
                        v = _norm(tds[ucode_idx].text)
                        if v:
                            s.add(v)
            except Exception:
                pass
            if not _scroll_step_down():
                break
        return s

    # -------- генераторы --------
    seq = 0
    def _gen_unique_code(existing: set[str]) -> str:
        base = int(time.time() * 100) % 1_000_000
        candidate = str(base)
        while candidate in existing:
            base += 1
            candidate = str(base)
        return candidate

    def _gen_certificate_id() -> str:
        nonlocal seq
        seq += 1
        return f"{int(time.time()*1000)}{seq%1000:03d}"

    # -------- UI: кнопка/модалка/дропдауны/тост --------
    def _find_add_glm_button():
        try:
            return WebDriverWait(table_root, 4, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-table-title')]//button[.//span[normalize-space()='Add GLM']]"))
            )
        except Exception:
            return WebDriverWait(drv, 2, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//span[normalize-space()='Add GLM']]"))
            )

    # открыть селект по label[@for=...] и вернуть ПАНЕЛЬ дропдауна
    def _open_dropdown_for_label(modal, for_id: str):
        sel = WebDriverWait(modal, 4, poll_frequency=0.1).until(
            EC.element_to_be_clickable((By.XPATH, f".//label[@for='{for_id}']/following::div[contains(@class,'ant-select')][1]//div[contains(@class,'ant-select-selector')]"))
        )
        try:
            drv.execute_script("arguments[0].scrollIntoView({block:'center'});", sel)
        except Exception:
            pass
        _click(sel)
        # 1) пробуем по id панели: "{for}_list"
        try:
            return WebDriverWait(drv, 2, poll_frequency=0.1).until(
                EC.visibility_of_element_located((By.ID, f"{for_id}_list"))
            )
        except Exception:
            # 2) фолбэк — последний видимый dropdown
            return WebDriverWait(drv, 4, poll_frequency=0.1).until(
                EC.visibility_of_element_located((By.XPATH, "(//div[contains(@class,'ant-select-dropdown') and not(contains(@style,'display: none'))])[last()]"))
            )

    # выбрать точный текст в виртуализированном списке с автоскроллом панели
    def _dropdown_select_exact(panel, text: str, timeout: float = 10.0):
        end = time.time() + float(timeout)
        js_try_match = """
return (function(root, target){
  const norm = s => (s||'').replace(/\\s+/g,' ').trim();
  const nodes = root.querySelectorAll("div.ant-select-item-option-content");
  for (const n of nodes){
    if (norm(n.textContent) === norm(target)) return n;
  }
  return null;
})(arguments[0], arguments[1]);
"""
        try:
            holder = drv.execute_script("return arguments[0].closest('.ant-select-dropdown')?.querySelector('.rc-virtual-list-holder')", panel)
        except Exception:
            holder = None
        if holder is None:
            holder = panel

        # попытка сразу
        node = drv.execute_script(js_try_match, panel, text)
        if node:
            drv.execute_script("arguments[0].click();", node)
            return

        # скроллим вниз порциями, проверяя появление цели
        last_top = -1
        while time.time() < end:
            node = drv.execute_script(js_try_match, panel, text)
            if node:
                drv.execute_script("arguments[0].click();", node)
                return
            try:
                cur  = drv.execute_script("return arguments[0].scrollTop;", holder)
                maxh = drv.execute_script("return arguments[0].scrollHeight - arguments[0].clientHeight;", holder)
            except Exception:
                cur, maxh = 0, 0
            if maxh <= 0 or cur >= maxh or cur == last_top:
                break
            drv.execute_script("arguments[0].scrollTop = Math.min(arguments[0].scrollTop + arguments[0].clientHeight*0.9, arguments[0].scrollHeight);", holder)
            last_top = cur
            time.sleep(0.08)

        # финальная попытка: проскроллить в самый верх и ещё раз проверить
        try:
            drv.execute_script("arguments[0].scrollTop = 0;", holder)
            time.sleep(0.05)
            node = drv.execute_script(js_try_match, panel, text)
            if node:
                drv.execute_script("arguments[0].click();", node)
                return
        except Exception:
            pass

        raise AssertionError(f"[ADD-GLM] Не нашёл опцию в дропдауне: {text}")

    def _dropdown_select_first(panel):
        opt = WebDriverWait(panel, 4, poll_frequency=0.1).until(
            EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-select-item-option') and not(contains(@class,'-disabled'))][1]"))
        )
        _click(opt)

    def _fill_modal_and_submit(ioc_val: str, unique_code: str, certificate_id: str):
        modal = WebDriverWait(drv, 4, poll_frequency=0.1).until(
            EC.visibility_of_element_located((By.XPATH, "//div[contains(@class,'ant-modal')][.//div[contains(@class,'ant-modal-title') and normalize-space()='Add GLM']]"))
        )

        # IOC: нужный номер (≠0)
        ioc_panel = _open_dropdown_for_label(modal, "ioc")
        _dropdown_select_exact(ioc_panel, ioc_val)

        # Location: первая опция
        loc_panel = _open_dropdown_for_label(modal, "location_id")
        _dropdown_select_first(loc_panel)

        # Unique Code (числовой ant-input-number)
        uinp = WebDriverWait(modal, 4, poll_frequency=0.1).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input#unique_code.ant-input-number-input"))
        )
        try:
            uinp.clear()
        except Exception:
            pass
        uinp.send_keys(unique_code)

        # Certificate (текст)
        cinp = WebDriverWait(modal, 4, poll_frequency=0.1).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input#certificate"))
        )
        try:
            cinp.clear()
        except Exception:
            pass
        cinp.send_keys(certificate_id)

        # OK
        ok_btn = WebDriverWait(modal, 4, poll_frequency=0.1).until(
            EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-modal-footer')]//button[.//span[normalize-space()='OK']]"))
        )
        _click(ok_btn)
        WebDriverWait(drv, 4, poll_frequency=0.1).until(EC.invisibility_of_element(modal))

    def _wait_glm_added_toast(expected_ioc: str, expected_glm: int, sec: float = 20.0):
        try:
            drv.switch_to.default_content()
        except Exception:
            pass
        js_find = """
return (function(){
  const norm = s => (s||'').replace(/\\s+/g,' ').trim();
  const stacks = document.querySelectorAll('.ant-notification');
  for (const s of stacks){
    const msgs = s.querySelectorAll('div.ant-notification-notice-message');
    for (const m of msgs){
      const t = norm(m.textContent);
      if (/^GLM \\d+\\(IOC \\d+\\) added successfully$/.test(t)) return t;
    }
  }
  return null;
})();
"""
        deadline = time.time() + sec
        while time.time() < deadline:
            t = None
            try:
                t = drv.execute_script(js_find)
            except Exception:
                pass
            if t:
                try:
                    p1 = t.find("GLM ") + 4
                    p2 = t.find("(", p1)
                    n = int(t[p1:p2])
                    q1 = t.find("IOC ", p2) + 4
                    q2 = t.find(")", q1)
                    m = t[q1:q2]
                except Exception:
                    raise AssertionError(f"[ADD-GLM] Некорректный формат тоста: {t}")

                if str(m) != str(expected_ioc):
                    raise AssertionError(f"[ADD-GLM] Тост IOC={m}, ожидалось IOC={expected_ioc}")
                if n != int(expected_glm):
                    raise AssertionError(f"[ADD-GLM] Тост GLM={n}, ожидалось GLM={expected_glm}")
                return (n, m)
            time.sleep(0.1)
        raise AssertionError(f"[ADD-GLM] Не дождался тоста 'GLM {expected_glm}(IOC {expected_ioc}) added successfully'")

    # -------- основной цикл --------
    ioc_list = _collect_nonzero_iocs()
    if not ioc_list:
        _log("[ADD-GLM] На странице нет IOC != 0 — делать нечего")
        return 0

    _log(f"[ADD-GLM] Целевые IOC: {', '.join(ioc_list)}; на каждого по {count} добавлений")

    for ioc_val in ioc_list:
        for rep in range(int(max(0, count))):
            if time.time() >= end_overall:
                _log(f"[ADD-GLM] Общий таймаут. Выполнено {total_done}")
                return total_done

            cur_max = _get_max_glm_for_ioc(ioc_val)
            expected_glm = 0 if cur_max is None else cur_max + 1
            _log(f"[ADD-GLM] IOC={ioc_val} итерация {rep+1}/{count}: cur_max={cur_max}, ожидаю GLM={expected_glm}")

            existing_ucodes = _collect_all_unique_codes()
            ucode = _gen_unique_code(existing_ucodes)
            cert  = _gen_certificate_id()

            btn = _find_add_glm_button()
            try:
                drv.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            except Exception:
                pass
            _click(btn)

            _fill_modal_and_submit(ioc_val=ioc_val, unique_code=ucode, certificate_id=cert)

            toast_glm, toast_ioc = _wait_glm_added_toast(expected_ioc=ioc_val, expected_glm=expected_glm, sec=20.0)
            _log(f"[ADD-GLM] Тост: GLM={toast_glm}, IOC={toast_ioc}")

            if not _table_has_pair(ioc_val=ioc_val, glm_val=expected_glm, sec=20.0):
                raise AssertionError(f"[ADD-GLM] В таблице не появилась строка IOC={ioc_val}, GLM={expected_glm}")

            total_done += 1
            _log(f"[ADD-GLM] OK: IOC={ioc_val}, GLM={expected_glm}. Всего добавлено: {total_done}")
            time.sleep(0.25)

    return total_done



@keyword("Expect Error")
def expect_error(expected_message: str, timeout: int = 30):
    """
    Expect Error    <expected_message>    [timeout=30]
    Ждёт появление AntD-уведомления с точным текстом <expected_message>.
    Возвращает фактический текст уведомления.
    """
    drv = _drv()
    target = " ".join((expected_message or "").split())
    end = time.time() + float(timeout)

    try:
        drv.switch_to.default_content()
    except Exception:
        pass

    js = """
return (function(expected){
  const norm = s => (s||'').replace(/\\s+/g,' ').trim();
  const tgt = norm(expected);
  // Ищем во всех стеках AntD notifications
  const roots = document.querySelectorAll('.ant-notification');
  for (const root of roots){
    const nodes = root.querySelectorAll(
      '.ant-notification-notice-message, .ant-notification-notice-title'
    );
    for (const n of nodes){
      const t = norm(n.textContent);
      if (t === tgt) return t;
    }
  }
  return null;
})(arguments[0]);
"""

    while time.time() < end:
        try:
            txt = drv.execute_script(js, target)
        except Exception:
            txt = None
        if txt:
            _log(f"[EXPECT-ERROR] Найдено уведомление: {txt}")
            return txt
        time.sleep(0.1)

    raise AssertionError(f"[EXPECT-ERROR] Не дождался уведомления: {expected_message!r} за {timeout}s")
    
@keyword("Add GLM With Existing Unique Code")
def add_glm_with_existing_unique_code(ioc: str | None = None,
                                      timeout: float = 30.0,
                                      table_index: int | None = None):
    """
    Берёт любой непустой Unique Code из таблицы и пытается создать GLM с ним (дубликат).
    Certificate генерируется уникальный, чтобы сработала именно ошибка по Unique Code.
    Ошибку ловит внешний кейворд Expect Error.
    """
    drv = _drv()
    bi  = BuiltIn()

    # ---------- утилиты (локально, чтобы не плодить глобальные def) ----------
    def _norm(s: str) -> str:
        return " ".join((s or "").split())

    def _click(el):
        try:
            el.click()
        except Exception:
            drv.execute_script("arguments[0].click();", el)

    def _find_table():
        boxes = drv.find_elements(By.CSS_SELECTOR, "div.ant-table-container")
        found = []
        for c in boxes:
            try:
                if not c.is_displayed():
                    continue
                ths = c.find_elements(By.CSS_SELECTOR, ".ant-table-header th")
                headers = [_norm(th.text) for th in ths]
                if "IOC" in headers and "Unique Code" in headers:
                    found.append((c, headers))
            except Exception:
                continue
        if not found:
            raise AssertionError("[NEG-GLM-UC] Таблица с колонками 'IOC' и 'Unique Code' не найдена")
        if table_index:
            i = table_index - 1
            if i < 0 or i >= len(found):
                raise AssertionError(f"[NEG-GLM-UC] table_index={table_index} вне диапазона (найдено {len(found)} таблиц)")
            return found[i][0], found[i][1]
        return found[0][0], found[0][1]

    table, headers = _find_table()
    try:
        body = table.find_element(By.CSS_SELECTOR, "div.ant-table-body")
    except Exception:
        body = table
    table_root = table.find_element(By.XPATH, "./ancestor::div[contains(@class,'ant-table')][1]")

    def _col_index(name: str) -> int:
        try:
            ths = table.find_elements(By.CSS_SELECTOR, ".ant-table-header th")
            for i, th in enumerate(ths):
                if _norm(th.text) == name:
                    return i
        except Exception:
            pass
        return -1

    ioc_idx   = _col_index("IOC")
    ucode_idx = _col_index("Unique Code")

    def _scroll_top():
        try:
            drv.execute_script("arguments[0].scrollTop = 0;", body)
            time.sleep(0.05)
        except Exception:
            pass

    def _scroll_bottom():
        try:
            drv.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", body)
            time.sleep(0.05)
        except Exception:
            pass

    def _pick_nonzero_ioc() -> str | None:
        _scroll_top()
        try:
            rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
            for r in rows:
                val = ""
                if ioc_idx >= 0:
                    tds = r.find_elements(By.CSS_SELECTOR, "td")
                    if ioc_idx < len(tds):
                        val = _norm(tds[ioc_idx].text)
                if not val:
                    try:
                        val = _norm(r.find_element(By.CSS_SELECTOR, "td.IOC, td[class*='IOC']").text)
                    except Exception:
                        pass
                if val and val != "0":
                    return val
        except Exception:
            pass
        _scroll_bottom()
        try:
            rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
            for r in rows:
                val = ""
                if ioc_idx >= 0:
                    tds = r.find_elements(By.CSS_SELECTOR, "td")
                    if ioc_idx < len(tds):
                        val = _norm(tds[ioc_idx].text)
                if not val:
                    try:
                        val = _norm(r.find_element(By.CSS_SELECTOR, "td.IOC, td[class*='IOC']").text)
                    except Exception:
                        pass
                if val and val != "0":
                    return val
        except Exception:
            pass
        return None

    def _take_existing_ucode() -> str:
        # пробуем сверху
        _scroll_top()
        try:
            rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
            for r in rows:
                val = ""
                if ucode_idx >= 0:
                    tds = r.find_elements(By.CSS_SELECTOR, "td")
                    if ucode_idx < len(tds):
                        val = _norm(tds[ucode_idx].text)
                if not val:
                    try:
                        val = _norm(r.find_element(By.CSS_SELECTOR, "td.UNIQUE_CODE, td[class*='UNIQUE']").text)
                    except Exception:
                        pass
                if val:
                    return val
        except Exception:
            pass
        # пробуем снизу
        _scroll_bottom()
        try:
            rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
            for r in rows:
                val = ""
                if ucode_idx >= 0:
                    tds = r.find_elements(By.CSS_SELECTOR, "td")
                    if ucode_idx < len(tds):
                        val = _norm(tds[ucode_idx].text)
                if not val:
                    try:
                        val = _norm(r.find_element(By.CSS_SELECTOR, "td.UNIQUE_CODE, td[class*='UNIQUE']").text)
                    except Exception:
                        pass
                if val:
                    return val
        except Exception:
            pass
        raise AssertionError("[NEG-GLM-UC] Не нашёл непустой 'Unique Code'")

    # генерация уникального сертификата (чтобы триггерилась именно ошибка UC)
    seq = 0
    def _gen_cert() -> str:
        nonlocal seq
        seq += 1
        return f"{int(time.time()*1000)}{seq%1000:03d}"

    def _find_add_glm_btn():
        try:
            return WebDriverWait(table_root, 6, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-table-title')]//button[.//span[normalize-space()='Add GLM']]"))
            )
        except Exception:
            return WebDriverWait(drv, 8, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//span[normalize-space()='Add GLM']]"))
            )

    def _open_dropdown_for_label(modal, for_id: str):
        sel = WebDriverWait(modal, 10, poll_frequency=0.1).until(
            EC.element_to_be_clickable((By.XPATH, f".//label[@for='{for_id}']/following::div[contains(@class,'ant-select')][1]//div[contains(@class,'ant-select-selector')]"))
        )
        drv.execute_script("arguments[0].scrollIntoView({block:'center'});", sel)
        _click(sel)
        try:
            return WebDriverWait(drv, 5, poll_frequency=0.1).until(
                EC.visibility_of_element_located((By.ID, f"{for_id}_list"))
            )
        except Exception:
            return WebDriverWait(drv, 8, poll_frequency=0.1).until(
                EC.visibility_of_element_located((By.XPATH, "(//div[contains(@class,'ant-select-dropdown') and not(contains(@style,'display: none'))])[last()]"))
            )

    def _dropdown_select_exact(panel, text: str, timeout_panel: float = 8.0):
        end = time.time() + float(timeout_panel)
        js_try = """
return (function(root, target){
  const norm = s => (s||'').replace(/\\s+/g,' ').trim();
  const nodes = root.querySelectorAll("div.ant-select-item-option-content");
  for (const n of nodes){ if (norm(n.textContent) === norm(target)) return n; }
  return null;
})(arguments[0], arguments[1]);
"""
        holder = drv.execute_script("return arguments[0].closest('.ant-select-dropdown')?.querySelector('.rc-virtual-list-holder')", panel) or panel
        node = drv.execute_script(js_try, panel, text)
        if node:
            drv.execute_script("arguments[0].click();", node); return
        # скроллим в конец, потом в начало
        try:
            drv.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", holder)
            time.sleep(0.05)
            node = drv.execute_script(js_try, panel, text)
            if node: drv.execute_script("arguments[0].click();", node); return
            drv.execute_script("arguments[0].scrollTop = 0;", holder)
            time.sleep(0.05)
            node = drv.execute_script(js_try, panel, text)
            if node: drv.execute_script("arguments[0].click();", node); return
        except Exception:
            pass
        raise AssertionError(f"[NEG-GLM-UC] Не нашёл опцию в дропдауне: {text}")

    # ---------- подготовка данных ----------
    ioc_val = ioc or _pick_nonzero_ioc()
    if not ioc_val:
        raise AssertionError("[NEG-GLM-UC] Нет подходящего IOC (≠ 0)")

    exist_uc = _take_existing_ucode()
    bi.log(f"[NEG-GLM-UC] duplicate UNIQUE_CODE='{exist_uc}', IOC={ioc_val}", "INFO")
    cert_val = _gen_cert()

    # ---------- UI: Add GLM ----------
    btn = _find_add_glm_btn()
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    _click(btn)

    modal = WebDriverWait(drv, 12, poll_frequency=0.1).until(
        EC.visibility_of_element_located((By.XPATH, "//div[contains(@class,'ant-modal')][.//div[contains(@class,'ant-modal-title') and normalize-space()='Add GLM']]"))
    )

    # IOC
    ioc_panel = _open_dropdown_for_label(modal, "ioc")
    _dropdown_select_exact(ioc_panel, ioc_val)

    # Location — первая опция (если требуется)
    try:
        loc_panel = _open_dropdown_for_label(modal, "location_id")
        first_opt = WebDriverWait(loc_panel, 6, poll_frequency=0.1).until(
            EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-select-item-option') and not(contains(@class,'-disabled'))][1]"))
        )
        _click(first_opt)
    except Exception:
        pass

    # Unique Code — ДУБЛИКАТ
    uinp = WebDriverWait(modal, 8, poll_frequency=0.1).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "input#unique_code.ant-input-number-input"))
    )
    try: uinp.clear()
    except Exception: pass
    uinp.send_keys(exist_uc)

    # Certificate — уникальный
    cinp = WebDriverWait(modal, 8, poll_frequency=0.1).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "input#certificate"))
    )
    try: cinp.clear()
    except Exception: pass
    cinp.send_keys(cert_val)

    # OK (не ждём закрытия модалки — ошибку поймает Expect Error)
    ok = WebDriverWait(modal, 8, poll_frequency=0.1).until(
        EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-modal-footer')]//button[.//span[normalize-space()='OK']]"))
    )
    _click(ok)

@keyword("Add GLM With Existing Certificate")
def add_glm_with_existing_certificate(ioc: str | None = None,
                                      timeout: float = 30.0,
                                      table_index: int | None = None):
    """
    Берёт любой непустой Certificate из таблицы и пытается создать GLM с ним (дубликат).
    Unique Code генерируется уникальный, чтобы сработала именно ошибка по Certificate.
    Ошибку ловит внешний кейворд Expect Error.
    """
    drv = _drv()
    bi  = BuiltIn()

    # ---------- утилиты ----------
    def _norm(s: str) -> str:
        return " ".join((s or "").split())

    def _click(el):
        try:
            el.click()
        except Exception:
            drv.execute_script("arguments[0].click();", el)

    def _find_table():
        boxes = drv.find_elements(By.CSS_SELECTOR, "div.ant-table-container")
        found = []
        for c in boxes:
            try:
                if not c.is_displayed():
                    continue
                ths = c.find_elements(By.CSS_SELECTOR, ".ant-table-header th")
                headers = [_norm(th.text) for th in ths]
                if "IOC" in headers and "Certificate" in headers:
                    found.append((c, headers))
            except Exception:
                continue
        if not found:
            raise AssertionError("[NEG-GLM-CERT] Таблица с колонками 'IOC' и 'Certificate' не найдена")
        if table_index:
            i = table_index - 1
            if i < 0 or i >= len(found):
                raise AssertionError(f"[NEG-GLM-CERT] table_index={table_index} вне диапазона (найдено {len(found)} таблиц)")
            return found[i][0], found[i][1]
        return found[0][0], found[0][1]

    table, headers = _find_table()
    try:
        body = table.find_element(By.CSS_SELECTOR, "div.ant-table-body")
    except Exception:
        body = table
    table_root = table.find_element(By.XPATH, "./ancestor::div[contains(@class,'ant-table')][1]")

    def _col_index(name: str) -> int:
        try:
            ths = table.find_elements(By.CSS_SELECTOR, ".ant-table-header th")
            for i, th in enumerate(ths):
                if _norm(th.text) == name:
                    return i
        except Exception:
            pass
        return -1

    ioc_idx  = _col_index("IOC")
    cert_idx = _col_index("Certificate")

    def _scroll_top():
        try:
            drv.execute_script("arguments[0].scrollTop = 0;", body)
            time.sleep(0.05)
        except Exception:
            pass

    def _scroll_bottom():
        try:
            drv.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", body)
            time.sleep(0.05)
        except Exception:
            pass

    def _pick_nonzero_ioc() -> str | None:
        _scroll_top()
        try:
            rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
            for r in rows:
                val = ""
                if ioc_idx >= 0:
                    tds = r.find_elements(By.CSS_SELECTOR, "td")
                    if ioc_idx < len(tds):
                        val = _norm(tds[ioc_idx].text)
                if not val:
                    try:
                        val = _norm(r.find_element(By.CSS_SELECTOR, "td.IOC, td[class*='IOC']").text)
                    except Exception:
                        pass
                if val and val != "0":
                    return val
        except Exception:
            pass
        _scroll_bottom()
        try:
            rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
            for r in rows:
                val = ""
                if ioc_idx >= 0:
                    tds = r.find_elements(By.CSS_SELECTOR, "td")
                    if ioc_idx < len(tds):
                        val = _norm(tds[ioc_idx].text)
                if not val:
                    try:
                        val = _norm(r.find_element(By.CSS_SELECTOR, "td.IOC, td[class*='IOC']").text)
                    except Exception:
                        pass
                if val and val != "0":
                    return val
        except Exception:
            pass
        return None

    def _take_existing_cert() -> str:
        _scroll_top()
        try:
            rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
            for r in rows:
                val = ""
                if cert_idx >= 0:
                    tds = r.find_elements(By.CSS_SELECTOR, "td")
                    if cert_idx < len(tds):
                        val = _norm(tds[cert_idx].text)
                if not val:
                    try:
                        val = _norm(r.find_element(By.CSS_SELECTOR, "td.CERTIFICATE, td[class*='CERTIFICATE']").text)
                    except Exception:
                        pass
                if val:
                    return val
        except Exception:
            pass
        _scroll_bottom()
        try:
            rows = body.find_elements(By.CSS_SELECTOR, "tbody tr.ant-table-row, tbody tr")
            for r in rows:
                val = ""
                if cert_idx >= 0:
                    tds = r.find_elements(By.CSS_SELECTOR, "td")
                    if cert_idx < len(tds):
                        val = _norm(tds[cert_idx].text)
                if not val:
                    try:
                        val = _norm(r.find_element(By.CSS_SELECTOR, "td.CERTIFICATE, td[class*='CERTIFICATE']").text)
                    except Exception:
                        pass
                if val:
                    return val
        except Exception:
            pass
        raise AssertionError("[NEG-GLM-CERT] Не нашёл непустой 'Certificate'")

    def _gen_ucode() -> str:
        base = int(time.time()*100) % 1_000_000
        return str(base)

    def _find_add_glm_btn():
        try:
            return WebDriverWait(table_root, 6, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-table-title')]//button[.//span[normalize-space()='Add GLM']]"))
            )
        except Exception:
            return WebDriverWait(drv, 8, poll_frequency=0.1).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//span[normalize-space()='Add GLM']]"))
            )

    def _open_dropdown_for_label(modal, for_id: str):
        sel = WebDriverWait(modal, 10, poll_frequency=0.1).until(
            EC.element_to_be_clickable((By.XPATH, f".//label[@for='{for_id}']/following::div[contains(@class,'ant-select')][1]//div[contains(@class,'ant-select-selector')]"))
        )
        drv.execute_script("arguments[0].scrollIntoView({block:'center'});", sel)
        _click(sel)
        try:
            return WebDriverWait(drv, 5, poll_frequency=0.1).until(
                EC.visibility_of_element_located((By.ID, f"{for_id}_list"))
            )
        except Exception:
            return WebDriverWait(drv, 8, poll_frequency=0.1).until(
                EC.visibility_of_element_located((By.XPATH, "(//div[contains(@class,'ant-select-dropdown') and not(contains(@style,'display: none'))])[last()]"))
            )

    def _dropdown_select_exact(panel, text: str, timeout_panel: float = 8.0):
        js_try = """
return (function(root, target){
  const norm = s => (s||'').replace(/\\s+/g,' ').trim();
  const nodes = root.querySelectorAll("div.ant-select-item-option-content");
  for (const n of nodes){ if (norm(n.textContent) === norm(target)) return n; }
  return null;
})(arguments[0], arguments[1]);
"""
        holder = drv.execute_script("return arguments[0].closest('.ant-select-dropdown')?.querySelector('.rc-virtual-list-holder')", panel) or panel
        node = drv.execute_script(js_try, panel, text)
        if node:
            drv.execute_script("arguments[0].click();", node); return
        try:
            drv.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", holder)
            time.sleep(0.05)
            node = drv.execute_script(js_try, panel, text)
            if node: drv.execute_script("arguments[0].click();", node); return
            drv.execute_script("arguments[0].scrollTop = 0;", holder)
            time.sleep(0.05)
            node = drv.execute_script(js_try, panel, text)
            if node: drv.execute_script("arguments[0].click();", node); return
        except Exception:
            pass
        raise AssertionError(f"[NEG-GLM-CERT] Не нашёл опцию в дропдауне: {text}")

    # ---------- подготовка данных ----------
    ioc_val = ioc or _pick_nonzero_ioc()
    if not ioc_val:
        raise AssertionError("[NEG-GLM-CERT] Нет подходящего IOC (≠ 0)")

    exist_cert = _take_existing_cert()
    bi.log(f"[NEG-GLM-CERT] duplicate CERTIFICATE='{exist_cert}', IOC={ioc_val}", "INFO")
    uc_val = _gen_ucode()

    # ---------- UI: Add GLM ----------
    btn = _find_add_glm_btn()
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    _click(btn)

    modal = WebDriverWait(drv, 12, poll_frequency=0.1).until(
        EC.visibility_of_element_located((By.XPATH, "//div[contains(@class,'ant-modal')][.//div[contains(@class,'ant-modal-title') and normalize-space()='Add GLM']]"))
    )

    # IOC
    ioc_panel = _open_dropdown_for_label(modal, "ioc")
    _dropdown_select_exact(ioc_panel, ioc_val)

    # Location — первая опция (если требуется)
    try:
        loc_panel = _open_dropdown_for_label(modal, "location_id")
        first_opt = WebDriverWait(loc_panel, 6, poll_frequency=0.1).until(
            EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-select-item-option') and not(contains(@class,'-disabled'))][1]"))
        )
        _click(first_opt)
    except Exception:
        pass

    # Unique Code — уникальный
    uinp = WebDriverWait(modal, 8, poll_frequency=0.1).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "input#unique_code.ant-input-number-input"))
    )
    try: uinp.clear()
    except Exception: pass
    uinp.send_keys(uc_val)

    # Certificate — ДУБЛИКАТ
    cinp = WebDriverWait(modal, 8, poll_frequency=0.1).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "input#certificate"))
    )
    try: cinp.clear()
    except Exception: pass
    cinp.send_keys(exist_cert)

    # OK (ошибку ловит Expect Error)
    ok = WebDriverWait(modal, 8, poll_frequency=0.1).until(
        EC.element_to_be_clickable((By.XPATH, ".//div[contains(@class,'ant-modal-footer')]//button[.//span[normalize-space()='OK']]"))
    )
    _click(ok)
