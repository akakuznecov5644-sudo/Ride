import re
from robot.api.deco import keyword
from robot.libraries.BuiltIn import BuiltIn
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


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


@keyword("Searchable Select By Attr")
def searchable_select_by_attr(attr_pair: str,
                              option_text: str,
                              *,
                              index: int | None = None,
                              wait_sec: int = 10):
    from libs import excel_params_2 as base

    root, drv = base._select_root(attr_pair, index)
    base._open_dropdown(root, drv)
    attr, val = base._parse(attr_pair)
    css_repr  = f'css:[{attr}*="{val}"]'
    BuiltIn().log(
        f"Selecting option '{option_text}' in searchable '{css_repr}'", "INFO"
    )
    search = root.find_element(
        By.CSS_SELECTOR,
        "input[role='combobox'], input[type='search'].ant-select-selection-search-input"
    )

    drv.execute_script("arguments[0].value = '';", search)
    search.send_keys(Keys.CONTROL, "a", Keys.DELETE, option_text)

    base._click_option(option_text, drv, strict=False, wait=wait_sec)


@keyword("Fill Date On Filter")
def fill_date_on_filter(date_text: str, timeout: float = 6.0, *, js_fallback: bool = True):
    BuiltIn().log(f'Filling date "{date_text}" into the date input inside the open filter', "INFO")
    sl = BuiltIn().get_library_instance("SeleniumLibrary")
    drv = sl.driver

    WebDriverWait(drv, timeout).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, ".ant-dropdown:not(.ant-dropdown-hidden)"))
    )

    xpath = (
        "//div[contains(@class,'ant-dropdown') and not(contains(@class,'ant-dropdown-hidden'))]"
        "//div[contains(@class,'ant-table-filter-dropdown')]"
        "//div[contains(@class,'ant-picker')]//input[not(@type='hidden')]"
    )
    target = WebDriverWait(drv, timeout).until(
        EC.visibility_of_element_located((By.XPATH, xpath))
    )

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

    import re as _re
    expect_digits = _re.sub(r"\D", "", date_text or "")

    def _ok():
        v = (target.get_attribute("value") or "")
        got_digits = _re.sub(r"\D", "", v)
        return got_digits.startswith(expect_digits) or got_digits.endswith(expect_digits)

    WebDriverWait(drv, timeout).until(lambda d: _ok())


@keyword("Scroll X Page By")
def scroll_x_page_by(px: int):
    from libs import excel_params_2 as base

    drv = base._drv()
    BuiltIn().log(f"Scroll X Page By {px}", "INFO")
    drv.execute_script("""
        const el = document.scrollingElement || document.documentElement || document.body;
        el.scrollLeft = (el.scrollLeft || 0) + arguments[0];
    """, int(px))


@keyword("Scroll X Page To")
def scroll_x_page_to(pos: str):
    from libs import excel_params_2 as base

    drv = base._drv()
    pos = (pos or "").strip().lower()
    BuiltIn().log(f"Scroll X Page To {pos}", "INFO")
    drv.execute_script("""
        const el = document.scrollingElement || document.documentElement || document.body;
        if (arguments[0]==='left')   el.scrollLeft = 0;
        else if (arguments[0]==='right')  el.scrollLeft = el.scrollWidth;
        else if (arguments[0]==='center') el.scrollLeft = Math.max(0, (el.scrollWidth - el.clientWidth)/2);
        else el.scrollLeft = (el.scrollLeft || 0);
    """, pos)


@keyword("Scroll X By Attr")
def scroll_x_by_attr(attr_pair: str,
                     by: int | None = None,
                     to: str | None = None,
                     *,
                     index: int | None = None,
                     timeout: float = 8.0):
    """
    Скроллит горизонтально контейнер, найденный по attr="value_part".
    """
    from libs import excel_params_2 as base

    drv = base._drv()
    a, v = base._parse(attr_pair)
    css = f'[{a}*="{v}"]'

    WebDriverWait(drv, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))
    elems = drv.find_elements(By.CSS_SELECTOR, css)
    if not elems:
        raise AssertionError(f"Element not found by {css}")
    el = elems[(index - 1) if index else 0]

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


@keyword("Open Filter By Attr")
def open_filter_by_attr(attr_pair: str, index: int | None = None, timeout: float = 8.0):
    """
    Открывает фильтр по паре атрибутов:  name="value"
    Спецкейс: name == class → токенный матч (' foo ' внутри @class),
    чтобы class=" TICKET_IN" не совпадал с PROMO_TICKET_IN.
    """
    from libs import excel_params_2 as base

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
    val = m.group(3)

    if attr == "class":
        pred = _class_token_pred(val)
    else:
        lit = _xp_literal(val)
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
        base._wait_filter_dropdown(drv, timeout)
    except Exception:
        WebDriverWait(drv, timeout).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".ant-dropdown, .ant-popover, .ant-table-filter-dropdown")
            )
        )
