import asyncio
import sqlite3
import re
from datetime import datetime, timedelta
from mcstatus import JavaServer
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import matplotlib
import matplotlib.pyplot as plt
import io

matplotlib.use('Agg')  # Используем бэкенд для работы без GUI
TOKEN = ""
DATABASE_NAME = "server_stats.db"

# # Инициализация базы данных
# def init_db():
#     conn = sqlite3.connect(DATABASE_NAME)
#     c = conn.cursor()
#     c.execute('''CREATE TABLE IF NOT EXISTS server_stats
#                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
#                   timestamp DATETIME NOT NULL,
#                   players_online INTEGER NOT NULL)''')
#     conn.commit()
#     conn.close()

# # Миграция: добавляем таблицу ping_stats, если её нет
# def migrate_db():
#     conn = sqlite3.connect(DATABASE_NAME)
#     c = conn.cursor()
#     c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ping_stats'")
#     if c.fetchone() is None:
#         c.execute('''CREATE TABLE ping_stats
#                      (id INTEGER PRIMARY KEY AUTOINCREMENT,
#                       timestamp DATETIME NOT NULL,
#                       success INTEGER NOT NULL)''')
#         conn.commit()
#         print("Таблица ping_stats успешно добавлена в базу данных.")
#     conn.close()

# init_db()
# migrate_db()


async def update_server_stats():
    while True:
        try:
            server = JavaServer.lookup("mc.forcemine.net")
            status = await server.async_status()

            conn = sqlite3.connect(DATABASE_NAME)
            c = conn.cursor()
            c.execute("INSERT INTO server_stats (timestamp, players_online) VALUES (?, ?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status.players.online))
            # Фиксируем успешный пинг
            c.execute("INSERT INTO ping_stats (timestamp, success) VALUES (?, ?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 1))
            conn.commit()
            conn.close()

            await asyncio.sleep(1800)  # 30 минут

        except Exception as e:
            print(f"Ошибка обновления: {e}")
            try:
                conn = sqlite3.connect(DATABASE_NAME)
                c = conn.cursor()
                # Фиксируем неудачный пинг
                c.execute(
                    "INSERT INTO ping_stats (timestamp, success) VALUES (?, ?)",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0)
                )
                conn.commit()
                conn.close()
            except Exception as ex:
                print(f"Ошибка записи пинга: {ex}")
            await asyncio.sleep(300)  # 5 минут при ошибке

def get_average_online(hours):
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    time_threshold = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    c.execute("SELECT AVG(players_online) FROM server_stats WHERE timestamp >= ?",
        (time_threshold,))
    result = c.fetchone()[0]
    conn.close()

    return round(result, 2) if result else 0.0

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    periods = {f"{h} час{'а' if h in {1, 2, 24} else 'ов'}": h for h in range(1, 25)}
    periods.update({f"{d} дней": d * 24 for d in [3, 7, 14, 30]})

    try:
        stats_text = "📊 Статистика онлайна:\n"
        for name, hours in periods.items():
            avg = get_average_online(hours)
            avg_div = round(avg / 4.5, 2)
            stats_text += f"• {name}: {avg} ({avg_div}) игроков\n"

        await update.message.reply_text(stats_text)

    except Exception as e:
        await update.message.reply_text(f"Ошибка статистики: {e}")


async def graph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if not args:
            hours = 24
        else:
            try:
                hours = int(args[0])

                if hours <= 0:
                    raise ValueError

            except ValueError:
                await update.message.reply_text("⚠️ Укажите целое число часов (например: /graph 24)")
                return

        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        time_threshold = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT timestamp, players_online FROM server_stats WHERE timestamp >= ? ORDER BY timestamp",
            (time_threshold,))
        data = c.fetchall()
        conn.close()

        if not data:
            await update.message.reply_text("📭 Нет данных за указанный период.")
            return

        timestamps = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") for row in data]
        players_online = [row[1] / 4.5 for row in data]  # Делим онлайн на 4.5

        plt.figure(figsize=(12, 6))
        plt.plot(timestamps, players_online, marker='o', linestyle='-', markersize=4, linewidth=1)
        plt.title(f'Онлайн игроков за последние {hours} часов (делённый на 4.5)')
        plt.xlabel('Время')
        plt.ylabel('Игроков онлайн (÷ 4.5)')
        plt.grid(True)
        plt.xticks(rotation=45)
        #plt.xticks(rotation=55)
        #plt.xticks(rotation=35)
        plt.gca().xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%H:%M'))
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        #plt.savefig(buf, format='png', dpi=170)
        #plt.savefig(buf, format='png', dpi=120)
        buf.seek(0)
        plt.close()

        await update.message.reply_photo(photo=buf,caption=f'📊 Онлайн за последние {hours} часов (делённый на 4.5)')
        buf.close()

    except Exception as e:
        await update.message.reply_text(f"🚫 Ошибка: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Привет! Используй /help для получения списка команд.'
    )

def get_stats_data(hours):
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    now = datetime.now()
    yesterday = now - timedelta(hours=hours)
    
    c.execute(
        """SELECT players_online, timestamp 
        FROM server_stats 
        WHERE timestamp BETWEEN ? AND ? 
        ORDER BY ABS(strftime('%s', timestamp) - strftime('%s', ?)) 
        LIMIT 1""",
        (yesterday - timedelta(minutes=30), yesterday + timedelta(minutes=30), yesterday))
    last_day_data = c.fetchone()
    
    c.execute("SELECT AVG(players_online) FROM server_stats WHERE timestamp >= ?",(yesterday,))
    avg_day = c.fetchone()[0]

    c.execute("SELECT MAX(players_online) FROM server_stats WHERE timestamp >= ?",(yesterday,))
    max_day = c.fetchone()[0]
    
    c.execute("SELECT MAX(players_online) FROM server_stats")
    max_all = c.fetchone()[0]
    
    conn.close()
    
    return {
        'last_day': last_day_data,
        'avg_day': round(avg_day, 2) if avg_day else 0,
        'max_day': max_day if max_day else 0,
        'max_all': max_all if max_all else 0
    }

async def statsserver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()

        # Текущий онлайн
        c.execute("SELECT players_online, timestamp FROM server_stats ORDER BY timestamp DESC LIMIT 1")
        current_row = c.fetchone()
        current_online = current_row[0] if current_row else 0

        # Данные за последние 24 часа
        stats_data = get_stats_data(24)
        online_24h = stats_data['last_day'][0] if stats_data['last_day'] else 0
        avg_online = stats_data['avg_day']
        max_online_day = stats_data['max_day']
        max_online_all = stats_data['max_all']

        # Пинг-статистика за последние 24 часа
        time_threshold = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT COUNT(*) FROM ping_stats WHERE timestamp >= ? AND success = 0", (time_threshold,))
        failed_pings = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM ping_stats WHERE timestamp >= ?", (time_threshold,))
        total_pings = c.fetchone()[0]
        uptime_percentage = 0.0

        if total_pings > 0:
            uptime_percentage = 100 * (total_pings - failed_pings) / total_pings

        # Вычисление максимального времени между падениями
        c.execute("SELECT timestamp FROM ping_stats WHERE success = 0 ORDER BY timestamp")
        failure_rows = c.fetchall()
        failure_times = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") for row in failure_rows]
        max_gap = timedelta(0)

        if failure_times:
            for i in range(1, len(failure_times)):
                gap = failure_times[i] - failure_times[i-1]

                if gap > max_gap:
                    max_gap = gap

            current_gap = datetime.now() - failure_times[-1]

            if current_gap > max_gap:
                max_gap = current_gap
        else:
            max_gap = timedelta(0)

        if failure_times:
            current_uptime = datetime.now() - failure_times[-1]
        else:
            current_uptime = timedelta(0)

        conn.close()

        def format_timedelta(td):
            days = td.days
            hours, remainder = divmod(td.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{days}d {hours}h {minutes}m {seconds}s"

        server = JavaServer.lookup("mc.forcemine.net")
        status = await server.async_status()

        online_original = status.players.online
        max_original = status.players.max
        online_divided = round(online_original / 4.5, 2)
        max_divided = round(max_original / 4.5, 2)

        def clean_mc_formatting(text):
            return re.sub(r'§.', '', str(text)).strip()

        response = (
            f"🟢 Сервер онлайн!\n"
            f"📄 Описание: {clean_mc_formatting(status.description)}\n"
            f"👥 Игроки: {online_original} ({online_divided})/{max_original} ({max_divided})\n"
            f"📦 Версия: {clean_mc_formatting(status.version.name)}\n"
            f"⏱ Пинг: {round(status.latency, 2)} мс"
        )


        response = (
            f"🟢 Сервер онлайн!\n"
            f"📄 Описание: {clean_mc_formatting(status.description)}\n"
            f"👥 Игроки: {online_original} ({int(online_divided)})/{max_original} ({int(max_divided)})\n"
            f"📦 Версия: {clean_mc_formatting(status.version.name)}\n"
            f"⏱ Пинг: {round(status.latency, 2)} мс\n"
            f"\n"
            f"Текущий онлайн: {current_online} ({round(current_online/4.5,0)})\n"
            f"Онлайн сутки назад в это же время: {online_24h} ({round(online_24h/4.5,0)})\n"
            f"Средний онлайн за сутки: {avg_online} ({round(avg_online/4.5,0)})\n"
            f"Рекорд онлайна за сутки: {max_online_day} ({round(max_online_day/4.5,0)})\n"
            f"Рекорд онлайна за всё время: {max_online_all} ({round(max_online_all/4.5,0)})\n"
            f"Неудачных пингов за сутки: {failed_pings} (аптайм: {uptime_percentage:.3f}%)\n"
            f"Максимальное время между падениями: {format_timedelta(max_gap)}\n"
            f"Текущий аптайм: {format_timedelta(current_uptime)}"
        )

        await update.message.reply_text(f"```\n{response}\n```", parse_mode='MarkdownV2')

    except Exception as e:
        await update.message.reply_text(f"Ошибка статистики сервера: {str(e)}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = ("Доступные команды:\n"
        "/start - Начало работы с ботом\n"
        "/status - Получить текущий статус сервера (онлайн делён на 4.5 в скобках)\n"
        "/stats - Статистика онлайна за заданные периоды\n"
        "/graph [часов] - График онлайна за последние [часов] часов (онлайн делён на 4.5)\n"
        "/statsserver - Расширенная статистика сервера\n"
        "/help - Показать это сообщение")
    await update.message.reply_text(help_text)

async def main():
    application = Application.builder().token(TOKEN).build()

    # Запуск фоновой задачи обновления статистики
    asyncio.create_task(update_server_stats())

    # Регистрация команд
    application.add_handler(CommandHandler("graph", graph))
    application.add_handler(CommandHandler("statsserver", statsserver))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))

    application.add_handler(CommandHandler("g", graph))
    application.add_handler(CommandHandler("ss", statsserver))
    application.add_handler(CommandHandler("s", stats))

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Бесконечный цикл для работы бота
    while True:
        await asyncio.sleep(3600)

    # Корректное завершение (эта часть не будет достигнута, если не прервать цикл)
    await application.updater.stop()
    await application.stop()
    await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
