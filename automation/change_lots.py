"""Автоматизация действия "Изменить" (Корректировка) для обычных (не-ЭМ)
лотов на Портале закупок Фонда (zakup.sk.kz).

Основано на em_agent.py (рабочий скрипт для лотов ЭМ, функция change_lot) -
поиск лота и переход в режим корректировки работают так же. Само
заполнение полей отличается: у обычных лотов форма корректировки намного
больше (способ закупок, приоритет, адреса, условия поставки и т.д.), в
отличие от простой формы ЭМ (только сумма/НДС/организатор).

ВАЖНО: точная разметка формы корректировки обычного лота не проверена по
реальному HTML - селекторы полей построены по подписям (тексту рядом с
полем), исходя из скриншотов. Первый прогон обязательно должен быть
dry-run - по подробному логу "OK" / "[!] не найдено" сразу видно, какие
поля определились верно, а какие нужно поправить.

Режим по умолчанию - DRY-RUN: скрипт заполняет форму значениями из файла,
делает скриншот и НЕ нажимает "Сохранить" - реальных изменений на портале
не происходит. Для реального сохранения нужен явный флаг --live и
подтверждение "да".

Запуск:
    python automation/change_lots.py путь/к/файлу_заливки.xlsx
    python automation/change_lots.py путь/к/файлу_заливки.xlsx --live
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import Page, async_playwright

from automation.portal_common import (
    PORTAL_URL,
    confirm_live_run,
    get_ident,
    get_lot_number,
    open_actions_menu,
    print_summary,
    read_upload_rows,
    resolve_candidates,
    search_lot,
    try_fill,
    try_select_fuzzy,
    wait_for_manual_login,
)

# Соответствие: канонические поля лота (см. lot_reconciler/models.py) ->
# подпись поля на странице корректировки лота. Требует проверки в dry-run.
TEXT_FIELDS = {
    "month": "Месяц закупок",
    "quantity": "Объем",
    "unit_price": "Цена за единицу",
    "address": "Адрес поставки",
}
SELECT_FIELDS_WITH_REFERENCE = {
    "method": ("Способ закупок", "methods"),
    "priority": ("Приоритет закупки", "priorities"),
    "delivery_terms": ("ИНКОТЕРМС", "incoterms"),
}


async def fill_change_form(page: Page, lot) -> None:
    print("  Заполняю поля корректировки:")
    for field, label in TEXT_FIELDS.items():
        value = lot.fields.get(field)
        await try_fill(page, label, value)

    for field, (label, ref_kind) in SELECT_FIELDS_WITH_REFERENCE.items():
        value = lot.fields.get(field)
        candidates = resolve_candidates(ref_kind, value)
        if not candidates and value:
            candidates = [str(value)]
        await try_select_fuzzy(page, label, candidates)


async def change_lot(page: Page, lot, dry_run: bool, screenshot_dir: Path) -> str:
    lot_number = get_lot_number(lot)
    ident = get_ident(lot)

    print(f"  Идентификатор : {ident}")
    print(f"  Номер лота    : {lot_number}")

    if not lot_number:
        raise ValueError("Пустой номер лота (колонка №) - не могу найти лот на портале")

    await search_lot(page, lot_number)

    print("  Шаг: нажимаю Действия -> Корректировка...")
    await open_actions_menu(page, "Корректировка")

    await fill_change_form(page, lot)

    save_btn = page.locator("button:has-text('Сохранить')").first
    await save_btn.wait_for(state="visible", timeout=10000)

    if dry_run:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        shot_path = screenshot_dir / f"dry_run_change_{lot_number.replace('/', '_')}.png"
        await page.screenshot(path=str(shot_path), full_page=True)
        print(f"  СУХОЙ ПРОГОН: форма заполнена, 'Сохранить' НЕ нажата.")
        print(f"  Скриншот формы: {shot_path}")
        return "dry_run"

    await save_btn.click()
    await page.wait_for_timeout(3000)
    print("  ИЗМЕНЕНО успешно")
    return "changed"


async def run(lots: list, dry_run: bool, screenshot_dir: Path) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        page = await browser.new_page()

        print("Открываю браузер...")
        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60000)
        await wait_for_manual_login(page)

        if dry_run:
            print("Режим: СУХОЙ ПРОГОН (dry-run, реальных изменений не будет)")
        elif not confirm_live_run("изменить"):
            print("Отменено пользователем.")
            await browser.close()
            return

        results: dict[str, int] = {}
        errors: list[tuple[str, str]] = []

        for i, lot in enumerate(lots, 1):
            ident = get_ident(lot)
            lot_number = get_lot_number(lot)
            label = lot_number if lot_number else ident
            print(f"\n[{i}/{len(lots)}] ИЗМЕНИТЬ | Лот: {label} | Ид: {ident}")

            try:
                status = await change_lot(page, lot, dry_run, screenshot_dir)
                results[status] = results.get(status, 0) + 1
            except Exception as e:  # noqa: BLE001 - логируем и идём дальше
                try:
                    await page.screenshot(path=str(screenshot_dir / f"error_change_{i}.png"))
                except Exception:
                    pass
                error_msg = str(e)
                print(f"  ОШИБКА: {error_msg}")
                print(f"  Скриншот: error_change_{i}.png")
                errors.append((label, error_msg))
                continue

        print_summary(len(lots), results, errors)
        input("Нажмите Enter для закрытия браузера...")
        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Изменение (корректировка) лотов (не-ЭМ) на Портале закупок по файлу заливки."
    )
    parser.add_argument("file", help="Файл заливки (.xlsx) с колонкой 'Тип действия'")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Реально нажимать кнопку 'Сохранить' (по умолчанию - сухой прогон).",
    )
    parser.add_argument(
        "--screenshots",
        default="automation/screenshots",
        help="Папка для скриншотов dry-run и ошибок.",
    )
    args = parser.parse_args()

    lots = read_upload_rows(args.file, "изменить")
    if not lots:
        print("Нет лотов со статусом 'изменить' в файле.")
        return

    asyncio.run(run(lots, dry_run=not args.live, screenshot_dir=Path(args.screenshots)))


if __name__ == "__main__":
    main()
