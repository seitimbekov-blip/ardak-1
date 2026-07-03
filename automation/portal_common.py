"""Общие функции для автоматизации Портала закупок (zakup.sk.kz).

Переиспользуется скриптами exclude_lots.py / change_lots.py / add_lots.py.
em_agent.py (рабочий скрипт для лотов ЭМ) не изменяется и не зависит от
этого модуля - это отдельный, независимый код для обычных (не-ЭМ) лотов.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from playwright.async_api import Page

PORTAL_URL = "https://zakup.sk.kz/"
DEFAULT_EXCLUSION_REASON = "в связи с корректировкой бюджета"

_REFERENCE_NAMES_PATH = Path(__file__).resolve().parent.parent / "config" / "reference_names.json"


def _load_reference_names() -> dict:
    with open(_REFERENCE_NAMES_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


_REFERENCE_NAMES = _load_reference_names()


def resolve_candidates(kind: str, code: Optional[str]) -> List[str]:
    """Возвращает варианты текста для выбора в выпадающем списке по коду
    (например, kind='methods', code='ЗЦП') - сам код, полное наименование
    из справочника и наименование без кода, в порядке от самого точного к
    самому общему. Точная формулировка опции на реальной странице портала
    может отличаться, поэтому try_select_fuzzy пробует их по очереди и
    затем ищет частичное совпадение."""
    if not code:
        return []
    code = str(code).strip()
    candidates = [code]
    name = _REFERENCE_NAMES.get(kind, {}).get(code.upper())
    if name:
        candidates.append(f"{code} - {name}")
        candidates.append(name)
    return candidates


def read_upload_rows(path: str, action: str) -> list:
    """Читает файл заливки (результат F9) и возвращает записи с заданным
    значением "Тип действия" (например, "изменить", "добавить",
    "исключить").

    Файл заливки использует тот же формат/колонки, что и выгрузка SAP,
    поэтому переиспользуем lot_reconciler.sap_loader.load_sap_file - это
    гарантирует корректное распознание нужных колонок (в т.ч. "Кол-во,
    объем" именно за плановый, а не переходящий год - в файле оба поля
    называются одинаково) так же, как это уже проверено в инструменте
    сверки."""
    from lot_reconciler.sap_loader import load_sap_file

    result = load_sap_file(path)
    matching = [
        r for r in result.records
        if (r.action_type_reference or "").strip().lower() == action
    ]
    print(f"Найдено строк со статусом '{action}': {len(matching)}")
    return matching


def get_lot_number(lot) -> str:
    """Номер лота в ИСЭЗ/Портале (колонка №) - по нему ищем лот на странице поиска."""
    return str(lot.fields.get("isez_number") or "").strip()


def get_ident(lot) -> str:
    return lot.identifier.raw


def get_reason(lot) -> str:
    reason = str(lot.fields.get("exclusion_reason") or "").strip()
    return reason or DEFAULT_EXCLUSION_REASON


async def search_lot(page: Page, lot_number: str, method_label: Optional[str] = None) -> None:
    """Ищет лот по номеру пункта плана на странице "Пункты плана".

    Для лотов ЭМ (em_agent.py) в фильтре "Способ закупки" всегда
    выбирается "Электронный магазин". Для обычных лотов способ закупки
    заранее неизвестен (ОТ/ЗЦП/ОИ и т.д.), поэтому фильтр не выставляем -
    ищем по номеру без ограничения по способу, если явно не передан
    method_label."""
    search_input = page.locator("input[placeholder*='Номер пункта плана']")
    if await search_input.count() == 0:
        search_input = page.locator("input").first
    await search_input.fill(lot_number)
    await page.wait_for_timeout(500)

    if method_label:
        sposob_select = page.locator("select").first
        await sposob_select.select_option(label=method_label)
        await page.wait_for_timeout(500)

    find_btn = page.locator("button:has-text('Найти')").first
    await find_btn.click()
    await page.wait_for_timeout(2000)


async def open_actions_menu(page: Page, item_label: str) -> None:
    """Нажимает кнопку "Действия" и выбирает пункт меню (например,
    "Корректировка" или "Исключить")."""
    actions_btn = page.locator("button:has-text('Действия')").first
    await actions_btn.wait_for(state="visible", timeout=10000)
    await actions_btn.click()
    await page.wait_for_timeout(1000)

    menu_item = page.locator(f"a:has-text('{item_label}'), button:has-text('{item_label}')").first
    await menu_item.wait_for(state="visible", timeout=5000)
    await menu_item.click()
    await page.wait_for_timeout(2000)


async def field_by_label(page: Page, label_text: str, tag: str = "input"):
    """Возвращает локатор поля ввода (input/select/textarea), расположенного
    сразу после подписи с текстом label_text. Портал не использует
    стандартную привязку <label for=...>, поэтому ищем ближайший следующий
    по DOM элемент нужного тега после текста подписи.

    ВНИМАНИЕ: эта эвристика не проверена на реальной странице - точность
    нужно подтвердить в первом же dry-run прогоне (см. verbose-лог "нашёл
    поле" / "поле не найдено" для каждого label_text)."""
    return page.locator(
        f"xpath=(//*[contains(normalize-space(text()), '{label_text}')]"
        f"/following::{tag})[1]"
    )


async def try_fill(page: Page, label_text: str, value, tag: str = "input") -> bool:
    """Пытается заполнить текстовое/числовое поле по подписи. Возвращает
    True, если поле найдено и заполнено, False - если поле не найдено
    (лот не падает с ошибкой из-за одного отсутствующего поля, но это
    логируется, чтобы было видно на dry-run)."""
    if value is None or str(value).strip() == "":
        return False
    locator = await field_by_label(page, label_text, tag=tag)
    if await locator.count() == 0:
        print(f"    [!] Поле '{label_text}' не найдено на странице - пропущено")
        return False
    try:
        await locator.first.fill(str(value))
        await page.wait_for_timeout(300)
        print(f"    OK: '{label_text}' = {value}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"    [!] Не удалось заполнить '{label_text}': {e}")
        return False


async def try_select(page: Page, label_text: str, option_label: str) -> bool:
    """Аналог try_fill для выпадающих списков (select) - выбирает опцию по
    точному видимому тексту."""
    if not option_label or not str(option_label).strip():
        return False
    locator = await field_by_label(page, label_text, tag="select")
    if await locator.count() == 0:
        print(f"    [!] Список '{label_text}' не найден на странице - пропущено")
        return False
    try:
        await locator.first.select_option(label=str(option_label).strip())
        await page.wait_for_timeout(300)
        print(f"    OK: '{label_text}' = {option_label}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"    [!] Не удалось выбрать в '{label_text}' значение '{option_label}': {e}")
        return False


async def try_select_fuzzy(page: Page, label_text: str, candidates: List[str]) -> bool:
    """Выбирает опцию в выпадающем списке, перебирая варианты текста
    (candidates, см. resolve_candidates): сначала точное совпадение,
    затем - опция, текст которой содержит вариант как подстроку (без учета
    регистра). Нужен из-за того, что точная формулировка опций на реальной
    странице портала не подтверждена и может отличаться от справочника."""
    if not candidates:
        return False
    locator = await field_by_label(page, label_text, tag="select")
    if await locator.count() == 0:
        print(f"    [!] Список '{label_text}' не найден на странице - пропущено")
        return False
    select_el = locator.first

    for candidate in candidates:
        try:
            await select_el.select_option(label=candidate)
            await page.wait_for_timeout(300)
            print(f"    OK: '{label_text}' = {candidate} (точное совпадение)")
            return True
        except Exception:
            continue

    try:
        options = await select_el.locator("option").all_text_contents()
    except Exception:
        options = []
    for candidate in candidates:
        candidate_lower = candidate.lower()
        for option_text in options:
            if candidate_lower in option_text.lower():
                try:
                    await select_el.select_option(label=option_text)
                    await page.wait_for_timeout(300)
                    print(f"    OK: '{label_text}' = {option_text} (частичное совпадение по '{candidate}')")
                    return True
                except Exception:
                    continue

    print(f"    [!] Не нашёл подходящую опцию в '{label_text}' среди вариантов {candidates}")
    return False


async def wait_for_manual_login(page: Page) -> None:
    print()
    print("====================================================")
    print("  Войдите на портал zakup.sk.kz вручную.")
    print("  Перейдите на страницу Пункты плана нужного года.")
    print("  Затем нажмите Enter здесь.")
    print("====================================================")
    input()


def confirm_live_run(action_word: str) -> bool:
    """Запрашивает явное подтверждение перед реальным (не dry-run) прогоном."""
    print(f"Режим: БОЕВОЙ (реальные изменения на портале! действие: {action_word})")
    answer = input(f"Вы уверены, что хотите выполнить '{action_word}' по-настоящему? Введите 'да': ")
    return answer.strip().lower() == "да"


def print_summary(total: int, results: dict, errors: list[tuple[str, str]]) -> None:
    print("\n====================================================")
    print(f"ГОТОВО. Обработано лотов: {total}, результат: {results}, ошибок: {len(errors)}")
    if errors:
        print("\nЛоты с ошибками (проверьте вручную и исключите либо скорректируйте):")
        for lbl, err in errors:
            print(f"  {lbl} - {err}")
    print("====================================================")
