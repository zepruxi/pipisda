import os
import sys

# Принудительное получение переменных с диагностикой
print("🔍 ПОИСК ПЕРЕМЕННЫХ ОКРУЖЕНИЯ:")
print(f"BOT_TOKEN из os.environ: {os.environ.get('BOT_TOKEN', 'НЕ НАЙДЕН!')}")
print(f"ADMIN_ID из os.environ: {os.environ.get('ADMIN_ID', 'НЕ НАЙДЕН!')}")
print(f"BASE_URL из os.environ: {os.environ.get('BASE_URL', 'НЕ НАЙДЕН!')}")
print("="*50)

TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    # Если не нашли, пробуем прочитать напрямую из переменной окружения (еще один способ)
    TOKEN = os.getenv('BOT_TOKEN')
    if not TOKEN:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не найден ни одним способом!")
        # Выводим все переменные окружения для отладки
        print("Все доступные переменные окружения:")
        for key in os.environ.keys():
            print(f"  - {key}")
        sys.exit(1)

print(f"✅ Токен успешно получен: {TOKEN[:5]}...")
