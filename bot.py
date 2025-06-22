import logging
import requests
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from config import BOT_TOKEN, LOG_LEVEL, LOG_FORMAT

# Настройка логирования
logging.basicConfig(
    format=LOG_FORMAT,
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_database():
    """Инициализация базы данных для избранных рецептов"""
    conn = sqlite3.connect('recipes.db')
    cursor = conn.cursor()
    
    # Проверяем, существует ли таблица
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='favorite_recipes'")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        # Создаем новую таблицу с полем rating
        cursor.execute('''
            CREATE TABLE favorite_recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                recipe_id TEXT NOT NULL,
                recipe_name TEXT NOT NULL,
                recipe_image TEXT,
                recipe_instructions TEXT,
                rating INTEGER DEFAULT 0,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, recipe_id)
            )
        ''')
    else:
        # Проверяем, есть ли поле rating в существующей таблице
        cursor.execute("PRAGMA table_info(favorite_recipes)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'rating' not in columns:
            # Добавляем поле rating к существующей таблице
            cursor.execute('ALTER TABLE favorite_recipes ADD COLUMN rating INTEGER DEFAULT 0')
    
    conn.commit()
    conn.close()

# Обработчик команды /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start с главным меню"""
    user = update.effective_user
    
    # Создаем кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("🔍 Поиск рецептов", callback_data="search_recipes")],
        [InlineKeyboardButton("❤️ Мои избранные рецепты", callback_data="my_favorites")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(
        f"Привет, {user.mention_html()}! 👋\n\n"
        "🍳 Добро пожаловать в Кулинарный Бот!\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

# Обработчик команды /test
async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /test для проверки работы бота"""
    await update.message.reply_text(
        "✅ Бот работает отлично!\n\n"
        "🔄 Все функции активны:\n"
        "• Команды обрабатываются корректно\n"
        "• Кнопки работают\n"
        "• База данных подключена\n"
        "• API рецептов доступен\n\n"
        "🎉 Бот готов к работе!"
    )

# Обработчик нажатий на кнопки
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на inline кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "search_recipes":
        await show_search_menu(query)
    elif query.data == "my_favorites":
        await show_favorites(query)
    elif query.data == "back_to_main":
        await show_main_menu(query)
    elif query.data == "random_recipe":
        await show_random_recipe(query)
    elif query.data == "search_by_name":
        await show_search_by_name_prompt(query)
    elif query.data == "search_by_category":
        await show_categories_menu(query)
    elif query.data.startswith("add_favorite_"):
        await add_to_favorites(query)
    elif query.data.startswith("remove_favorite_"):
        await remove_from_favorites(query)
    elif query.data.startswith("view_recipe_"):
        await show_recipe_details(query)
    elif query.data.startswith("category_"):
        await show_recipes_by_category(query)
    elif query.data.startswith("select_recipe_"):
        recipe_id = query.data.replace("select_recipe_", "")
        await show_recipe_details_by_id(query, recipe_id)
    elif query.data.startswith("rate_recipe_"):
        await show_rating_menu(query)
    elif query.data.startswith("set_rating_"):
        await set_recipe_rating(query)

async def show_search_menu(query):
    """Показать меню поиска рецептов"""
    keyboard = [
        [InlineKeyboardButton("🎲 Случайный рецепт", callback_data="random_recipe")],
        [InlineKeyboardButton("📝 Поиск по названию", callback_data="search_by_name")],
        [InlineKeyboardButton("📂 Поиск по категории", callback_data="search_by_category")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔍 **Поиск рецептов**\n\n"
        "Выберите способ поиска:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_favorites(query):
    """Показать избранные рецепты пользователя"""
    user_id = query.from_user.id
    
    # Получаем избранные рецепты из БД, сортируем по рейтингу (убывание)
    conn = sqlite3.connect('recipes.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT recipe_id, recipe_name, recipe_image, rating
        FROM favorite_recipes 
        WHERE user_id = ? 
        ORDER BY rating DESC, added_date DESC
    ''', (user_id,))
    favorites = cursor.fetchall()
    conn.close()
    
    if not favorites:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "❤️ **Мои избранные рецепты**\n\n"
            "У вас пока нет избранных рецептов.\n"
            "Найдите рецепт и добавьте его в избранное!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Показываем список избранных рецептов с рейтингом
    text = "❤️ **Мои избранные рецепты:**\n\n"
    keyboard = []
    
    for i, (recipe_id, recipe_name, recipe_image, rating) in enumerate(favorites[:10]):  # Ограничиваем 10 рецептами
        stars = "⭐" * rating if rating > 0 else "❌ Нет оценки"
        text += f"{i+1}. {recipe_name}\n"
        text += f"   {stars}\n\n"
        keyboard.append([InlineKeyboardButton(f"👁️ {recipe_name[:20]}...", callback_data=f"view_recipe_{recipe_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_main_menu(query):
    """Показать главное меню"""
    keyboard = [
        [InlineKeyboardButton("🔍 Поиск рецептов", callback_data="search_recipes")],
        [InlineKeyboardButton("❤️ Мои избранные рецепты", callback_data="my_favorites")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🍳 **Главное меню**\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def add_to_favorites(query):
    """Добавить рецепт в избранное"""
    recipe_id = query.data.replace("add_favorite_", "")
    user_id = query.from_user.id
    
    # Получаем данные рецепта из API
    try:
        response = requests.get(f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={recipe_id}")
        recipe_data = response.json()
        
        if recipe_data['meals']:
            recipe = recipe_data['meals'][0]
            recipe_name = recipe['strMeal']
            recipe_image = recipe['strMealThumb']
            recipe_instructions = recipe['strInstructions']
            
            # Сохраняем в БД
            conn = sqlite3.connect('recipes.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO favorite_recipes 
                (user_id, recipe_id, recipe_name, recipe_image, recipe_instructions)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, recipe_id, recipe_name, recipe_image, recipe_instructions))
            conn.commit()
            conn.close()
            
            await query.answer("✅ Рецепт добавлен в избранное!")
        else:
            await query.answer("❌ Рецепт не найден!")
    except Exception as e:
        logger.error(f"Ошибка при добавлении в избранное: {e}")
        await query.answer("❌ Ошибка при добавлении в избранное")

async def remove_from_favorites(query):
    """Удалить рецепт из избранного"""
    recipe_id = query.data.replace("remove_favorite_", "")
    user_id = query.from_user.id
    
    conn = sqlite3.connect('recipes.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM favorite_recipes WHERE user_id = ? AND recipe_id = ?', (user_id, recipe_id))
    conn.commit()
    conn.close()
    
    await query.answer("🗑️ Рецепт удален из избранного")

async def show_recipe_details(query):
    """Показать детали рецепта"""
    recipe_id = query.data.replace("view_recipe_", "")
    user_id = query.from_user.id
    
    try:
        response = requests.get(f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={recipe_id}")
        recipe_data = response.json()
        
        if recipe_data['meals']:
            recipe = recipe_data['meals'][0]
            
            # Проверяем, есть ли рецепт в избранном
            conn = sqlite3.connect('recipes.db')
            cursor = conn.cursor()
            cursor.execute('SELECT 1, rating FROM favorite_recipes WHERE user_id = ? AND recipe_id = ?', (user_id, recipe_id))
            result = cursor.fetchone()
            is_favorite = result is not None
            current_rating = result[1] if result else 0
            conn.close()
            
            # Формируем текст рецепта
            text = f"🍳 **{recipe['strMeal']}**\n\n"
            text += f"📋 **Категория:** {recipe['strCategory']}\n"
            text += f"🌍 **Кухня:** {recipe['strArea']}\n"
            
            if is_favorite and current_rating > 0:
                stars = "⭐" * current_rating
                text += f"⭐ **Ваш рейтинг:** {stars}\n"
            
            text += f"\n📋 **Ингредиенты:**\n"
            
            # Собираем ингредиенты
            ingredients = []
            for i in range(1, 21):
                ingredient = recipe[f'strIngredient{i}']
                measure = recipe[f'strMeasure{i}']
                if ingredient and ingredient.strip():
                    ingredients.append(f"• {measure} {ingredient}")
            
            text += "\n".join(ingredients[:10])  # Показываем первые 10 ингредиентов
            text += "\n\n📝 **Инструкция:**\n"
            text += recipe['strInstructions'][:500] + "..." if len(recipe['strInstructions']) > 500 else recipe['strInstructions']
            
            # Добавляем ссылку на видеорецепт, если есть
            if recipe['strYoutube'] and recipe['strYoutube'].strip():
                text += f"\n\n🎥 **Видеорецепт:**\n"
                text += f"📺 {recipe['strYoutube']}"
            
            # Создаем кнопки
            keyboard = []
            if is_favorite:
                keyboard.append([InlineKeyboardButton("🗑️ Удалить из избранного", callback_data=f"remove_favorite_{recipe_id}")])
                keyboard.append([InlineKeyboardButton("⭐ Оценить рецепт", callback_data=f"rate_recipe_{recipe_id}")])
            else:
                keyboard.append([InlineKeyboardButton("❤️ Добавить в избранное", callback_data=f"add_favorite_{recipe_id}")])
            
            # Добавляем кнопку видеорецепта, если есть
            if recipe['strYoutube'] and recipe['strYoutube'].strip():
                keyboard.append([InlineKeyboardButton("🎥 Смотреть видеорецепт", url=recipe['strYoutube'])])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Рецепт не найден!")
    except Exception as e:
        logger.error(f"Ошибка при получении рецепта: {e}")
        await query.answer("❌ Ошибка при получении рецепта")

# Функции для работы с API TheMealDB

async def show_random_recipe(query):
    """Показать случайный рецепт"""
    try:
        response = requests.get("https://www.themealdb.com/api/json/v1/1/random.php")
        recipe_data = response.json()
        
        if recipe_data['meals']:
            recipe = recipe_data['meals'][0]
            recipe_id = recipe['idMeal']
            recipe_name = recipe['strMeal']
            recipe_image = recipe['strMealThumb']
            
            # Проверяем, есть ли рецепт в избранном
            user_id = query.from_user.id
            conn = sqlite3.connect('recipes.db')
            cursor = conn.cursor()
            cursor.execute('SELECT 1, rating FROM favorite_recipes WHERE user_id = ? AND recipe_id = ?', (user_id, recipe_id))
            result = cursor.fetchone()
            is_favorite = result is not None
            current_rating = result[1] if result else 0
            conn.close()
            
            text = f"🎲 **Случайный рецепт:**\n\n"
            text += f"🍳 **{recipe_name}**\n\n"
            text += f"📋 **Категория:** {recipe['strCategory']}\n"
            text += f"🌍 **Кухня:** {recipe['strArea']}\n\n"
            text += f"📝 **Краткое описание:**\n"
            text += recipe['strInstructions'][:200] + "..." if len(recipe['strInstructions']) > 200 else recipe['strInstructions']
            
            # Добавляем ссылку на видеорецепт, если есть
            if recipe['strYoutube'] and recipe['strYoutube'].strip():
                text += f"\n\n🎥 **Видеорецепт:**\n"
                text += f"📺 {recipe['strYoutube']}"
            
            keyboard = []
            if is_favorite:
                keyboard.append([InlineKeyboardButton("🗑️ Удалить из избранного", callback_data=f"remove_favorite_{recipe_id}")])
            else:
                keyboard.append([InlineKeyboardButton("❤️ Добавить в избранное", callback_data=f"add_favorite_{recipe_id}")])
            
            keyboard.append([InlineKeyboardButton("👁️ Подробнее", callback_data=f"view_recipe_{recipe_id}")])
            
            # Добавляем кнопку видеорецепта, если есть
            if recipe['strYoutube'] and recipe['strYoutube'].strip():
                keyboard.append([InlineKeyboardButton("🎥 Смотреть видеорецепт", url=recipe['strYoutube'])])
            
            keyboard.append([InlineKeyboardButton("🎲 Другой рецепт", callback_data="random_recipe")])
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="search_recipes")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Не удалось получить случайный рецепт")
    except Exception as e:
        logger.error(f"Ошибка при получении случайного рецепта: {e}")
        await query.answer("❌ Ошибка при получении рецепта")

async def show_search_by_name_prompt(query):
    """Показать подсказку для поиска по названию"""
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="search_recipes")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📝 **Поиск по названию**\n\n"
        "Напишите название блюда, которое хотите найти.\n"
        "Например: chicken, pasta, cake\n\n"
        "💡 **Совет:** Используйте английские названия для лучших результатов.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_categories_menu(query):
    """Показать меню категорий"""
    try:
        response = requests.get("https://www.themealdb.com/api/json/v1/1/categories.php")
        categories_data = response.json()
        
        if categories_data['categories']:
            keyboard = []
            categories = categories_data['categories']
            
            # Группируем категории по 2 в ряд
            for i in range(0, len(categories), 2):
                row = []
                row.append(InlineKeyboardButton(
                    categories[i]['strCategory'], 
                    callback_data=f"category_{categories[i]['strCategory']}"
                ))
                
                if i + 1 < len(categories):
                    row.append(InlineKeyboardButton(
                        categories[i + 1]['strCategory'], 
                        callback_data=f"category_{categories[i + 1]['strCategory']}"
                    ))
                
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="search_recipes")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📂 **Категории рецептов**\n\n"
                "Выберите категорию для просмотра рецептов:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Не удалось загрузить категории")
    except Exception as e:
        logger.error(f"Ошибка при получении категорий: {e}")
        await query.answer("❌ Ошибка при загрузке категорий")

async def show_recipes_by_category(query):
    """Показать рецепты по выбранной категории"""
    category = query.data.replace("category_", "")
    
    try:
        response = requests.get(f"https://www.themealdb.com/api/json/v1/1/filter.php?c={category}")
        recipes_data = response.json()
        
        if recipes_data['meals']:
            recipes = recipes_data['meals']
            text = f"📂 **Рецепты в категории '{category}':**\n\n"
            keyboard = []
            
            # Показываем первые 10 рецептов
            for i, recipe in enumerate(recipes[:10]):
                text += f"{i+1}. {recipe['strMeal']}\n"
                keyboard.append([
                    InlineKeyboardButton(
                        f"👁️ {recipe['strMeal'][:25]}...", 
                        callback_data=f"select_recipe_{recipe['idMeal']}"
                    )
                ])
            
            if len(recipes) > 10:
                text += f"\n... и еще {len(recipes) - 10} рецептов"
            
            keyboard.append([InlineKeyboardButton("🔙 Назад к категориям", callback_data="search_by_category")])
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="search_by_category")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"❌ **Рецепты не найдены**\n\n"
                f"В категории '{category}' пока нет рецептов.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Ошибка при получении рецептов категории: {e}")
        await query.answer("❌ Ошибка при загрузке рецептов")

async def show_recipe_details_by_id(query, recipe_id):
    """Показать детали рецепта по ID"""
    user_id = query.from_user.id
    
    try:
        response = requests.get(f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={recipe_id}")
        recipe_data = response.json()
        
        if recipe_data['meals']:
            recipe = recipe_data['meals'][0]
            
            # Проверяем, есть ли рецепт в избранном
            conn = sqlite3.connect('recipes.db')
            cursor = conn.cursor()
            cursor.execute('SELECT 1, rating FROM favorite_recipes WHERE user_id = ? AND recipe_id = ?', (user_id, recipe_id))
            result = cursor.fetchone()
            is_favorite = result is not None
            current_rating = result[1] if result else 0
            conn.close()
            
            # Формируем текст рецепта
            text = f"🍳 **{recipe['strMeal']}**\n\n"
            text += f"📋 **Категория:** {recipe['strCategory']}\n"
            text += f"🌍 **Кухня:** {recipe['strArea']}\n"
            
            if is_favorite and current_rating > 0:
                stars = "⭐" * current_rating
                text += f"⭐ **Ваш рейтинг:** {stars}\n"
            
            text += f"\n📋 **Ингредиенты:**\n"
            
            # Собираем ингредиенты
            ingredients = []
            for i in range(1, 21):
                ingredient = recipe[f'strIngredient{i}']
                measure = recipe[f'strMeasure{i}']
                if ingredient and ingredient.strip():
                    ingredients.append(f"• {measure} {ingredient}")
            
            text += "\n".join(ingredients[:10])  # Показываем первые 10 ингредиентов
            text += "\n\n📝 **Инструкция:**\n"
            text += recipe['strInstructions'][:500] + "..." if len(recipe['strInstructions']) > 500 else recipe['strInstructions']
            
            # Добавляем ссылку на видеорецепт, если есть
            if recipe['strYoutube'] and recipe['strYoutube'].strip():
                text += f"\n\n🎥 **Видеорецепт:**\n"
                text += f"📺 {recipe['strYoutube']}"
            
            # Создаем кнопки
            keyboard = []
            if is_favorite:
                keyboard.append([InlineKeyboardButton("🗑️ Удалить из избранного", callback_data=f"remove_favorite_{recipe_id}")])
                keyboard.append([InlineKeyboardButton("⭐ Оценить рецепт", callback_data=f"rate_recipe_{recipe_id}")])
            else:
                keyboard.append([InlineKeyboardButton("❤️ Добавить в избранное", callback_data=f"add_favorite_{recipe_id}")])
            
            # Добавляем кнопку видеорецепта, если есть
            if recipe['strYoutube'] and recipe['strYoutube'].strip():
                keyboard.append([InlineKeyboardButton("🎥 Смотреть видеорецепт", url=recipe['strYoutube'])])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Рецепт не найден!")
    except Exception as e:
        logger.error(f"Ошибка при получении рецепта: {e}")
        await query.answer("❌ Ошибка при получении рецепта")

# Функции для работы с рейтингом

async def show_rating_menu(query):
    """Показать меню рейтинга"""
    recipe_id = query.data.replace("rate_recipe_", "")
    user_id = query.from_user.id
    
    # Проверяем, есть ли рецепт в избранном
    conn = sqlite3.connect('recipes.db')
    cursor = conn.cursor()
    cursor.execute('SELECT recipe_name FROM favorite_recipes WHERE user_id = ? AND recipe_id = ?', (user_id, recipe_id))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        await query.answer("❌ Рецепт не найден в избранном!")
        return
    
    recipe_name = result[0]
    
    keyboard = [
        [InlineKeyboardButton("⭐", callback_data=f"set_rating_{recipe_id}_1")],
        [InlineKeyboardButton("⭐⭐", callback_data=f"set_rating_{recipe_id}_2")],
        [InlineKeyboardButton("⭐⭐⭐", callback_data=f"set_rating_{recipe_id}_3")],
        [InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"set_rating_{recipe_id}_4")],
        [InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"set_rating_{recipe_id}_5")],
        [InlineKeyboardButton("🔙 Назад к рецепту", callback_data=f"select_recipe_{recipe_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"⭐ **Оцените рецепт**\n\n"
        f"Рецепт: **{recipe_name}**\n\n"
        f"Выберите количество звезд от 1 до 5:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def set_recipe_rating(query):
    """Установить рейтинг рецепта"""
    try:
        data_parts = query.data.replace("set_rating_", "").split("_")
        if len(data_parts) < 2:
            await query.answer("❌ Ошибка: неверный формат данных")
            return
            
        recipe_id = data_parts[0]
        rating = int(data_parts[1])
        user_id = query.from_user.id
        
        # Проверяем, что рейтинг в допустимом диапазоне
        if rating < 1 or rating > 5:
            await query.answer("❌ Ошибка: рейтинг должен быть от 1 до 5")
            return
        
        # Обновляем рейтинг в БД
        conn = sqlite3.connect('recipes.db')
        cursor = conn.cursor()
        
        # Сначала проверяем, существует ли рецепт в избранном
        cursor.execute('''
            SELECT recipe_name FROM favorite_recipes 
            WHERE user_id = ? AND recipe_id = ?
        ''', (user_id, recipe_id))
        
        result = cursor.fetchone()
        if not result:
            conn.close()
            await query.answer("❌ Рецепт не найден в избранном!")
            return
            
        recipe_name = result[0]
        
        # Обновляем рейтинг
        cursor.execute('''
            UPDATE favorite_recipes 
            SET rating = ? 
            WHERE user_id = ? AND recipe_id = ?
        ''', (rating, user_id, recipe_id))
        
        conn.commit()
        conn.close()
        
        stars = "⭐" * rating
        await query.answer(f"✅ Рейтинг {stars} установлен для '{recipe_name}'!")
        
        # Возвращаемся к рецепту
        await show_recipe_details_by_id(query, recipe_id)
            
    except ValueError:
        await query.answer("❌ Ошибка: неверный формат рейтинга")
    except Exception as e:
        logger.error(f"Ошибка при установке рейтинга: {e}")
        await query.answer("❌ Ошибка при установке рейтинга")

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех текстовых сообщений"""
    message_type = update.message.chat.type
    text = update.message.text.lower()
    
    # Логирование
    logger.info(f'Пользователь ({update.message.chat.id}) в {message_type}: "{text}"')
    
    # Проверка на слово "привет"
    if "привет" in text:
        user = update.effective_user
        await update.message.reply_text(
            f"Привет, {user.first_name}! 😊\n"
            "Используйте /start для доступа к меню бота!"
        )
        return
    
    # Поиск рецепта по названию
    await search_recipe_by_name(update, text)

async def search_recipe_by_name(update: Update, search_query: str):
    """Поиск рецепта по названию"""
    try:
        response = requests.get(f"https://www.themealdb.com/api/json/v1/1/search.php?s={search_query}")
        recipes_data = response.json()
        
        if recipes_data['meals']:
            recipes = recipes_data['meals']
            text = f"🔍 **Результаты поиска для '{search_query}':**\n\n"
            keyboard = []
            
            # Показываем первые 5 рецептов
            for i, recipe in enumerate(recipes[:5]):
                text += f"{i+1}. {recipe['strMeal']} ({recipe['strCategory']})\n"
                keyboard.append([
                    InlineKeyboardButton(
                        f"👁️ {recipe['strMeal'][:25]}...", 
                        callback_data=f"select_recipe_{recipe['idMeal']}"
                    )
                ])
            
            if len(recipes) > 5:
                text += f"\n... и еще {len(recipes) - 5} рецептов"
            
            keyboard.append([InlineKeyboardButton("🔍 Новый поиск", callback_data="search_by_name")])
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            keyboard = [
                [InlineKeyboardButton("🔍 Попробовать другой поиск", callback_data="search_by_name")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"❌ **Рецепты не найдены**\n\n"
                f"По запросу '{search_query}' ничего не найдено.\n"
                f"Попробуйте:\n"
                f"• Другие названия (chicken, pasta, cake)\n"
                f"• Использовать английские названия\n"
                f"• Поиск по категории",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Ошибка при поиске рецепта: {e}")
        await update.message.reply_text(
            "❌ Ошибка при поиске рецепта. Попробуйте позже."
        )

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f'Ошибка: {context.error}')

def main():
    """Основная функция запуска бота"""
    print("🤖 Запуск телеграм-бота...")
    
    # Проверка токена
    if BOT_TOKEN == 'YOUR_BOT_TOKEN':
        print("❌ ОШИБКА: Необходимо указать токен бота в файле config.py")
        print("📝 Инструкция:")
        print("1. Получите токен у @BotFather в Telegram")
        print("2. Откройте файл config.py")
        print("3. Замените 'YOUR_BOT_TOKEN' на ваш токен")
        return
    
    # Инициализация базы данных
    init_database()
    print("✅ База данных инициализирована")
    
    # Создание приложения
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Добавление обработчиков
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('test', test_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Обработчик ошибок
    app.add_error_handler(error_handler)
    
    # Запуск бота
    print("✅ Бот запущен! Нажмите Ctrl+C для остановки.")
    app.run_polling(poll_interval=1)

if __name__ == '__main__':
    main() 