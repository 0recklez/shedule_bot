import asyncio
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time

schedule_cache = {}
cache_lock = threading.Lock()
CACHE_TTL_SECONDS = 1200


def get_calendar_data(group_name):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://ya.mininuniver.ru/shedule")

        group_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "searchGroup"))
        )
        group_input.send_keys(group_name)
        time.sleep(1)
        group_input.send_keys(Keys.ARROW_DOWN)
        group_input.send_keys(Keys.ENTER)

        time.sleep(2)
        calendar_data = driver.execute_script("return window.CalendarData")
        return calendar_data

    except Exception as e:
        print(f"[Scheduler] Ошибка при получении расписания для группы {group_name}: {e}")
        return None

    finally:
        driver.quit()


def get_calendar_data_cached(group_name):
    now = time.time()
    cache_key = group_name
    with cache_lock:
        entry = schedule_cache.get(cache_key)
        if entry and now - entry["timestamp"] < CACHE_TTL_SECONDS:
            return entry["data"]
    data = get_calendar_data(group_name)
    with cache_lock:
        schedule_cache[cache_key] = {"timestamp": now, "data": data}
    return data


executor = ThreadPoolExecutor(max_workers=2)


async def get_calendar_data_async(group_name):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, get_calendar_data_cached, group_name)


def get_schedule_text(calendar_data, target_date=None):
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    found = False
    message = f"📅 Расписание на {target_date}:\n"

    for day in calendar_data:
        date = day.get("date")
        if date != target_date:
            continue

        found = True
        title = day.get("title")
        if title:
            for pair_number, pair_info in title.items():
                lessons = pair_info.get("lessons", [])

                for lesson in lessons:
                    subgroup_text = "Подгруппа не указана"

                    subgroup = lesson.get("subgroup")
                    if isinstance(subgroup, dict):
                        subgroup_number = subgroup.get("subgroup_numbers")
                        if subgroup_number:
                            subgroup_text = f"Подгруппа: {subgroup_number}"

                    couple = lesson.get("couple", {})
                    time_ = couple.get("time", "время неизвестно")
                    discipline = lesson.get("discipline", "предмет неизвестен")
                    teacher = lesson.get("teacher", {}).get("name", "преподаватель неизвестен")
                    cabinet = lesson.get("place", {}).get("cabinet", "кабинет не указан")
                    address = lesson.get("place", {}).get("housing", {}).get("address", "")
                    couple_type = lesson.get("couple", {}).get("couple_type", "не указано")
                    if lesson.get("couple", {}).get("couple_type", "не указано") == "лек.":
                        couple_type = "🟩 Лекция"
                    if lesson.get("couple", {}).get("couple_type", "не указано") == "прак.":
                        couple_type = "🟦 Практика"
                    if lesson.get("couple", {}).get("couple_type", "не указано") == "лаб.р.":
                        couple_type = "🟧 Лабораторная"
                    if lesson.get("couple", {}).get("couple_type", "не указано") == "зач.":
                        couple_type = "🟧 Зачет"
                    if lesson.get("couple", {}).get("couple_type", "не указано") == "экз.":
                        couple_type = "🟥 Экзамен"
                    if lesson.get("couple", {}).get("couple_type", "не указано") == "КСР":
                        couple_type = "🟦 КСР"
                    if lesson.get("couple", {}).get("couple_type", "не указано") == "кон.":
                        couple_type = "🟦 Контрольная"

                    message += (f"\n🕒 Пара №{pair_number} ({time_})\n"
                                f"📚 {discipline}\n"
                                f"{couple_type}\n"
                                f"👥 {subgroup_text}\n"
                                f"👨‍🏫 {teacher}\n"
                                f"🏫 {cabinet}, {address}\n")
        else:
            message += "\n📭 Занятий нет."

    if not found:
        message = f"📅 На {target_date} занятий не найдено."

    return message
