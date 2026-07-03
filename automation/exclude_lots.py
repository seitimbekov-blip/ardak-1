"""Автоматизация действия "Исключить" для обычных (не-ЭМ) лотов на Портале
закупок Фонда (zakup.sk.kz).

Основано на em_agent.py (рабочий скрипт для лотов ЭМ) и инструкции по
исключению лота, которая, по подтверждению Ардака, применима и к обычным
лотам - с той разницей, что при поиске лота не нужно фильтровать по
способу закупки "Электронный магазин" (обычные лоты используют другие
способы - ОТ, ЗЦП, ОИ и т.д.).

Режим по умолчанию - DRY-RUN: скрипт доходит до диалога подтверждения
исключения, вводит причину, делает скриншот и НЕ нажимает финальную
красную кнопку "Исключить" - реальных изменений на портале не происходит.
Для реального исключения нужен явный флаг --live и подтверждение "да".

Запуск:
    python automation/exclude_lots.py путь/к/файлу_заливки.xlsx
    python automation/exclude_lots.py путь/к/файлу_заливки.xlsx --live
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
    get_reason,
    open_actions_menu,
    print_summary,
    read_upload_rows,
    search_lot,
    wait_for_manual_login,
)


async def exclude_lot(page: Page, lot: dict, dry_run: bool, screenshot_dir: Path) -> str:
    lot_number = get_lot_number(lot)
    reason = get_reason(lot)
    ident = get_ident(lot)

    print(f"  Идентификатор : {ident}")
    print(f"  Номер лота    : {lot_number}")
    print(f"  Причина       : {reason}")

    if not lot_number:
        raise ValueError("Пустой номер лота (колонка №) - не могу найти лот на портале")

    await search_lot(page, lot_number)
    print("  Шаг: нажимаю Действия -> Исключить...")
    await open_actions_menu(page, "Исключить")

    print("  Шаг: ввожу причину исключения...")
    reason_input = page.locator(
        "textarea, input[placeholder*='Причина'], input[placeholder*='причина']"
    ).first
    if await reason_input.count() == 0:
        reason_input = page.locator("dialog input, .modal input, .popup input").first
    await reason_input.wait_for(state="visible", timeout=5000)
    await reason_input.fill(reason)
    await page.wait_for_timeout(500)

    confirm_btn = page.locator(
        "button.btn-danger:has-text('Исключить'), button.red:has-text('Исключить')"
    ).first
    if await confirm_btn.count() == 0:
        confirm_btn = page.locator("button:has-text('Исключить')").last
    await confirm_btn.wait_for(state="visible", timeout=5000)

    if dry_run:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        shot_path = screenshot_dir / f"dry_run_{lot_number.replace('/', '_')}.png"
        await page.screenshot(path=str(shot_path))
        print(f"  СУХОЙ ПРОГОН: лот {lot_number} был бы исключён с причиной '{reason}'.")
        print(f"  Кнопка подтверждения НЕ нажата. Скриншот диалога: {shot_path}")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        return "dry_run"

    await confirm_btn.click()
    await page.wait_for_timeout(3000)
    print("  ИСКЛЮЧЕНО успешно")
    return "excluded"


async def run(lots: list[dict], dry_run: bool, screenshot_dir: Path) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        page = await browser.new_page()

        print("Открываю браузер...")
        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60000)
        await wait_for_manual_login(page)

        if dry_run:
            print("Режим: СУХОЙ ПРОГОН (dry-run, реальных изменений не будет)")
        elif not confirm_live_run("исключить"):
            print("Отменено пользователем.")
            await browser.close()
            return

        results: dict[str, int] = {}
        errors: list[tuple[str, str]] = []

        for i, lot in enumerate(lots, 1):
            ident = get_ident(lot)
            lot_number = get_lot_number(lot)
            label = lot_number if lot_number else ident
            print(f"\n[{i}/{len(lots)}] ИСКЛЮЧИТЬ | Лот: {label} | Ид: {ident}")

            try:
                status = await exclude_lot(page, lot, dry_run, screenshot_dir)
                results[status] = results.get(status, 0) + 1
            except Exception as e:  # noqa: BLE001 - логируем и идём дальше, как просил Ардак
                try:
                    await page.screenshot(path=str(screenshot_dir / f"error_{i}.png"))
                except Exception:
                    pass
                error_msg = str(e)
                print(f"  ОШИБКА: {error_msg}")
                print(f"  Скриншот: error_{i}.png")
                errors.append((label, error_msg))
                continue

        print_summary(len(lots), results, errors)
        input("Нажмите Enter для закрытия браузера...")
        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Исключение лотов (не-ЭМ) на Портале закупок по файлу заливки."
    )
    parser.add_argument("file", help="Файл заливки (.xlsx) с колонкой 'Тип действия'")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Реально нажимать кнопку подтверждения исключения (по умолчанию - сухой прогон).",
    )
    parser.add_argument(
        "--screenshots",
        default="automation/screenshots",
        help="Папка для скриншотов dry-run и ошибок.",
    )
    args = parser.parse_args()

    lots = read_upload_rows(args.file, "исключить")
    if not lots:
        print("Нет лотов со статусом 'исключить' в файле.")
        return

    asyncio.run(run(lots, dry_run=not args.live, screenshot_dir=Path(args.screenshots)))


if __name__ == "__main__":
    main()
