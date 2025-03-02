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


matplotlib.use('Agg')  # Устанавливаем бэкенд для работы без GUI
TOKEN = ""
DATABASE_NAME = "server_stats.db"

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS server_stats
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME NOT NULL,
                  players_online INTEGER NOT NULL)''')
    conn.commit()
    conn.close()

init_db()

async def update_server_stats():
    while True:
        try:
            server = JavaServer.lookup("mc.forcemine.net")
            status = await server.async_status()
            
            conn = sqlite3.connect(DATABASE_NAME)
            c = conn.cursor()
            c.execute(
                "INSERT INTO server_stats (timestamp, players_online) VALUES (?, ?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status.players.online)
            )
            conn.commit()
            conn.close()
            
            await asyncio.sleep(1800)  # 30 минут
            
        except Exception as e:
            print(f"Ошибка обновления: {e}")
            await asyncio.sleep(300)  # 5 минут при ошибке

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Привет! Используй /status для статуса сервера и /stats для статистики'
    )

def clean_mc_formatting(text):
    return re.sub(r'§.', '', str(text)).strip()

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        server = JavaServer.lookup("mc.forcemine.net")
        status = await server.async_status()
        
        response = (
            f"🟢 Сервер онлайн!\n"
            f"📄 Описание: {clean_mc_formatting(status.description)}\n"
            f"👥 Игроки: {status.players.online}/{status.players.max}\n"
            f"📦 Версия: {clean_mc_formatting(status.version.name)}\n"
            f"⏱ Пинг: {round(status.latency, 2)} мс"
        )
        
        await update.message.reply_text(f"```\n{response}\n```", parse_mode='MarkdownV2')
        
    except Exception as e:
        await update.message.reply_text(f"🔴 Ошибка: {str(e)}")

def get_average_online(hours):
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    time_threshold = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute(
        "SELECT AVG(players_online) FROM server_stats WHERE timestamp >= ?",
        (time_threshold,)
    )
    result = c.fetchone()[0]
    conn.close()
    return round(result, 2) if result else 0.0

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    periods = {
        '1 час': 1,
        '2 часа': 2,
        '3 часов': 3,
        '4 часов': 4,
        '5 часов': 5,
        '6 часов': 6,
        '7 часов': 7,
        '8 часов': 8,
        '9 часов': 9,
        '10 часов': 10,
        '11 часов': 11,
        '12 часов': 12,
        '13 часов': 13,
        '14 часов': 14,
        '15 часов': 15,
        '16 часов': 16,
        '17 часов': 17,
        '18 часов': 18,
        '19 часов': 19,
        '20 часов': 20,
        '21 часов': 21,
        '22 часов': 22,
        '23 часов': 23,
        '24 часа': 24,
        '12 часов': 12,
        '24 часа': 24,
        '3 дня': 72,
        '7 дней': 168,
        '14 дней': 336,
        '30 дней': 720
    }
    
    stats_text = "📊 Статистика онлайна:\n"
    try:
        for name, hours in periods.items():
            avg = get_average_online(hours)
            stats_text += f"• {name}: {avg} игроков\n"
            
        await update.message.reply_text(stats_text)
    except Exception as e:
        await update.message.reply_text(f"Ошибка статистики: {str(e)}")
async def graph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Парсим аргументы (количество часов)
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

        # Получаем данные из БД
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        time_threshold = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "SELECT timestamp, players_online FROM server_stats WHERE timestamp >= ? ORDER BY timestamp",
            (time_threshold,)
        )
        data = c.fetchall()
        conn.close()

        if not data:
            await update.message.reply_text("📭 Нет данных за указанный период.")
            return

        # Подготавливаем данные для графика
        timestamps = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") for row in data]
        players_online = [row[1] for row in data]

        # Создаем график
        plt.figure(figsize=(12, 6))
        plt.plot(timestamps, players_online, marker='o', linestyle='-', markersize=4, linewidth=1)
        plt.title(f'Онлайн игроков за последние {hours} часов')
        plt.xlabel('Время')
        plt.ylabel('Игроков онлайн')
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()

        # Сохраняем график в буфер
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close()

        # Отправляем график
        await update.message.reply_photo(
            photo=buf,
            caption=f'📊 Онлайн за последние {hours} часов'
        )
        buf.close()

    except Exception as e:
        await update.message.reply_text(f"🚫 Ошибка: {str(e)}")
def get_stats_data(hours):
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    
    # Текущее время и время сутки назад
    now = datetime.now()
    yesterday = now - timedelta(hours=hours)
    
    # Онлайн 24 часа назад
    c.execute(
        """SELECT players_online, timestamp 
        FROM server_stats 
        WHERE timestamp BETWEEN ? AND ? 
        ORDER BY ABS(strftime('%s', timestamp) - strftime('%s', ?)) 
        LIMIT 1""",
        (yesterday - timedelta(minutes=30), yesterday + timedelta(minutes=30), yesterday))
    last_day_data = c.fetchone()
    
    # Средний онлайн за сутки
    c.execute(
        "SELECT AVG(players_online) FROM server_stats WHERE timestamp >= ?",
        (yesterday,))
    avg_day = c.fetchone()[0]
    
    # Рекорд за сутки
    c.execute(
        "SELECT MAX(players_online) FROM server_stats WHERE timestamp >= ?",
        (yesterday,))
    max_day = c.fetchone()[0]
    
    # Рекорд за всё время
    c.execute("SELECT MAX(players_online) FROM server_stats")
    max_all = c.fetchone()[0]
    
    conn.close()
    
    return {
        'last_day': last_day_data,
        'avg_day': round(avg_day, 2) if avg_day else 0,
        'max_day': max_day if max_day else 0,
        'max_all': max_all if max_all else 0
    }

async def main():
    application = Application.builder().token(TOKEN).build()
    
    # Запускаем фоновую задачу
    asyncio.create_task(update_server_stats())
    
    # Регистрируем команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("graph", graph))
    
    # Запускаем бота
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Бесконечный цикл
    while True:
        await asyncio.sleep(3600)

    # Корректное завершение
    await application.updater.stop()
    await application.stop()
    await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())