"""Campus cafeterias Siksha does not list, whose menu board is the same every day.

menus/data/fixed_cafeterias.json gives each one's place, the meals and weekdays it
serves, the first date its board is known for (`since`) and the board itself.
fetch_menus adds `records(date)` to the day's Siksha menu, so these lines are
cleaned, tagged and offered like any cafeteria line. A line's corner becomes part
of the cafeteria, as Siksha names 자하연식당>2층. Once Siksha lists a cafeteria,
remove it from the file, or its lines are offered twice.
"""

from __future__ import annotations

import datetime
import json
import pathlib

from .siksha import MenuRecord

CAFETERIAS_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "fixed_cafeterias.json"


def load() -> list[dict]:
    return json.loads(CAFETERIAS_PATH.read_text(encoding="utf-8"))["cafeterias"]


def records(date: datetime.date) -> list[MenuRecord]:
    """One record per (meal, menu line) of every cafeteria open on `date`."""
    found = []
    for cafeteria in load():
        if date < datetime.date.fromisoformat(cafeteria["since"]) or date.weekday() not in cafeteria["weekdays"]:
            continue
        for meal in cafeteria["meals"]:
            for menu in cafeteria["menus"]:
                corner = menu.get("corner", "")
                found.append(MenuRecord(
                    date=date, meal=meal,
                    restaurant_code=cafeteria["name"] + corner,
                    restaurant_name=f"{cafeteria['name']}>{corner}" if corner else cafeteria["name"],
                    lat=cafeteria["lat"], lng=cafeteria["lng"],
                    raw_name=menu["name"], price=menu["price"], no_meat=False,
                ))
    return found
