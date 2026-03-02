from robot.libraries.BuiltIn import BuiltIn
from selenium.webdriver.common.keys import Keys


def _scroll_root_js():
    return "return document.scrollingElement || document.documentElement || document.body;"


def _try_open_filter_with_keywords(anchor: str, order_list: list[str], timeout: float = 6.0) -> str | None:
    """Перебирает кейворды открытия по порядку, логирует попытки, ждёт оверлей."""
    from libs import excel_params_2 as base

    bi = BuiltIn()
    drv = base._drv()

    for kind in order_list:
        try:
            if kind == "text":
                base._log(f"Open filter from \"{anchor}\" column via Open Text Filter")
                bi.run_keyword("Open Text Filter", anchor)
            elif kind == "numeric":
                base._log(f"Open filter from \"{anchor}\" column via Open Numeric Filter")
                bi.run_keyword("Open Numeric Filter", anchor)
            elif kind == "datetime":
                base._log(f"Open filter from \"{anchor}\" column via Open DateTime Filter")
                bi.run_keyword("Open DateTime Filter", anchor)
            elif kind == "multiselect":
                base._log(f"Open filter from \"{anchor}\" column via Open Multiselect Filter")
                bi.run_keyword("Open Multiselect Filter", anchor)
            else:
                continue
        except Exception as e:
            base._log(f"Open filter via {kind} — failed: {type(e).__name__}", level="DEBUG")
            continue

        if base._wait_filter_dropdown_silent(drv, timeout=1.5):
            detected = base._detect_filter_type()
            base._log(f"Filter dropdown opened — detected: {detected}")
            return detected if detected != "unknown" else kind

    base._log(f"Open filter from \"{anchor}\" column — all keyword attempts failed", level="DEBUG")
    return None


def _click_ok_in_filter():
    bi = BuiltIn()
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


def _try_select_option_with_keywords(value: str) -> bool:
    """
    Мультиселекты: сначала пробуем Click By Text On Filter,
    если не нашли — вычисляем data-menu-id по тексту и кликаем
    строго форматом data-menu-id="...".
    """
    from libs import excel_params_2 as base

    bi = BuiltIn()
    target = str(value).strip()

    try:
        base._log(f'Try select by text: "{target}"')
        bi.run_keyword("Click By Text On Filter", target)
        return True
    except Exception:
        pass

    dm_id = base._resolve_data_menu_id_for_option(target)
    if dm_id:
        attr = f'data-menu-id="{dm_id}"'
        base._log(f'Try select by attr: {attr}')
        try:
            bi.run_keyword("Click By Attr On Filter", attr)
            return True
        except Exception:
            try:
                bi.run_keyword("Click By Attr", attr)
                return True
            except Exception:
                return False

    base._log("Option not found by text nor data-menu-id", level="DEBUG")
    return False


def _to_int_or_none(v):
    from libs import excel_params_2 as base

    if v in (None, "", "None"):
        return None
    return base._to_int(v, None)


def _fill_date_in_filter(value: str):
    """
    Для фильтров даты/даты-времени вводим значение исключительно через
    твой кейворд Fill Date By Attr с placeholder="Select date".
    """
    from libs import excel_params_2 as base

    bi = BuiltIn()
    try:
        bi.run_keyword("Fill Date By Attr", 'placeholder="Select date"', value)
        return
    except Exception as e:
        base._log(f'[FILTER-DATE] primary placeholder failed: {type(e).__name__}', level="DEBUG")

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

    raise RuntimeError("Date input inside filter not found by placeholder")


def _close_filter_dropdown_by_type(detected: str):
    from libs import excel_params_2 as base

    drv = base._drv()
    try:
        drv.switch_to.active_element.send_keys(Keys.ESCAPE)
    except Exception:
        pass
