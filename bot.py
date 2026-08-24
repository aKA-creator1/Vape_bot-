import logging
import asyncio
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, BaseFilter
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8608991330:AAEw2Pj89RXeryyesGjY26In8qi_OF9rwWM")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://landline-fading-attentive.ngrok-free.dev")
WEBHOOK_PATH = "/webhook"
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMINS", "6665950252").split(",")]
PRODUCTS_FILE = "products.json"
ORDERS_FILE = "orders.json"
IMAGES_FOLDER = "product_images"
PORT = int(os.getenv("PORT", 8000))

os.makedirs(IMAGES_FOLDER, exist_ok=True)
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= ФИЛЬТР АДМИНА =================
class AdminFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id in ADMIN_IDS

# ================= ЗАГРУЗКА/СОХРАНЕНИЕ =================
def load_products():
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [p for p in data if p.get('name') and p.get('price') is not None]
    default_products = [
        {"id": 1, "name": "XROS 3", "price": 2490, "category": "ПОД-системы", "subcategory": "pod", "description": "Компактная POD-система", "image": "/product_images/default.png", "available": True, "variants": [], "created_at": datetime.now().isoformat()},
        {"id": 2, "name": "SALT Liquid", "price": 490, "category": "Жидкости", "subcategory": "liquid", "description": "Солевая жидкость 20mg", "image": "/product_images/default.png", "available": True, "variants": [
            {"name": "Клубника", "price": 490},
            {"name": "Малина", "price": 490},
            {"name": "Арбуз", "price": 490}
        ], "created_at": datetime.now().isoformat()},
    ]
    save_products(default_products)
    return default_products

def save_products(products):
    clean_products = [p for p in products if p.get('name') and p.get('price') is not None]
    with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(clean_products, f, ensure_ascii=False, indent=2)

def load_orders():
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_orders(orders):
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

PRODUCTS = load_products()
ORDERS = load_orders()

# ================= ОТПРАВКА ЗАКАЗА АДМИНАМ =================
async def send_order_to_admins(order):
    order_text = f"🛍 <b>НОВЫЙ ЗАКАЗ #{order['id']}</b>\n\n"
    order_text += f"👤 <b>Покупатель:</b> {order['user_name']}\n"
    order_text += f"🆔 <b>ID:</b> <code>{order['user_id']}</code>\n"
    if order.get('username'):
        order_text += f"📱 <b>Username:</b> @{order['username']}\n"
    order_text += f"📅 <b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
    order_text += "\n" + "─" * 20 + "\n"
    order_text += "📦 <b>ТОВАРЫ В ЗАКАЗЕ:</b>\n\n"
    
    for idx, item in enumerate(order['items'], 1):
        order_text += f"{idx}. <b>{item['name']}</b>\n"
        order_text += f"   • Количество: {item.get('quantity', 1)} шт.\n"
        order_text += f"   • Цена: {item['price']} ₽\n"
        order_text += f"   • Сумма: {item['price'] * item.get('quantity', 1)} ₽\n\n"
    
    order_text += "─" * 20 + "\n"
    order_text += f"💰 <b>ИТОГО К ОПЛАТЕ:</b> {order['total']} ₽\n\n"
    order_text += f"📊 <b>Статус:</b> {order.get('status', 'Новый')}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"order_confirm_{order['id']}"),
         InlineKeyboardButton(text="❌ Отменить", callback_data=f"order_cancel_{order['id']}")],
        [InlineKeyboardButton(text="🚚 Доставлен", callback_data=f"order_deliver_{order['id']}"),
         InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"order_delete_{order['id']}")]
    ])
    
    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, order_text, parse_mode="HTML", reply_markup=keyboard)

# ================= УПРАВЛЕНИЕ ЗАКАЗАМИ =================
@dp.callback_query(lambda c: c.data.startswith("order_"))
async def order_management(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    action, order_id = callback.data.split("_")[1], int(callback.data.split("_")[2])
    order = next((o for o in ORDERS if o["id"] == order_id), None)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    
    status_map = {"confirm": "Подтверждён", "cancel": "Отменён", "deliver": "Доставлен"}
    if action in status_map:
        order["status"] = status_map[action]
        save_orders(ORDERS)
        await callback.answer(f"{'✅' if action == 'confirm' else '❌' if action == 'cancel' else '🚚'} Заказ {status_map[action].lower()}!")
        await update_order_message(callback.message, order)
        
        user_text = {
            "confirm": f"✅ <b>Ваш заказ #{order_id} подтверждён!</b>\n\nСкоро вы получите уведомление о доставке.",
            "cancel": f"❌ <b>Ваш заказ #{order_id} отменён.</b>\n\nПо вопросам свяжитесь с менеджером.",
            "deliver": f"🚚 <b>Ваш заказ #{order_id} доставлен!</b>\n\nСпасибо за покупку! 🙌"
        }
        try:
            await bot.send_message(order["user_id"], user_text[action], parse_mode="HTML")
        except:
            pass
    elif action == "delete":
        ORDERS[:] = [o for o in ORDERS if o["id"] != order_id]
        save_orders(ORDERS)
        await callback.message.delete()
        await callback.answer("🗑️ Заказ удалён!")

async def update_order_message(message, order):
    order_text = f"🛍 <b>ЗАКАЗ #{order['id']}</b>\n\n"
    order_text += f"👤 <b>Покупатель:</b> {order['user_name']}\n"
    order_text += f"🆔 <b>ID:</b> <code>{order['user_id']}</code>\n"
    if order.get('username'):
        order_text += f"📱 <b>Username:</b> @{order['username']}\n"
    order_text += f"📅 <b>Время:</b> {order.get('created_at', '').replace('T', ' ')[:16]}\n"
    order_text += "\n" + "─" * 20 + "\n"
    order_text += "📦 <b>ТОВАРЫ В ЗАКАЗЕ:</b>\n\n"
    
    for idx, item in enumerate(order['items'], 1):
        order_text += f"{idx}. <b>{item['name']}</b>\n"
        order_text += f"   • Количество: {item.get('quantity', 1)} шт.\n"
        order_text += f"   • Цена: {item['price']} ₽\n"
        order_text += f"   • Сумма: {item['price'] * item.get('quantity', 1)} ₽\n\n"
    
    order_text += "─" * 20 + "\n"
    order_text += f"💰 <b>ИТОГО К ОПЛАТЕ:</b> {order['total']} ₽\n\n"
    order_text += f"📊 <b>Статус:</b> {order.get('status', 'Новый')}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"order_confirm_{order['id']}"),
         InlineKeyboardButton(text="❌ Отменить", callback_data=f"order_cancel_{order['id']}")],
        [InlineKeyboardButton(text="🚚 Доставлен", callback_data=f"order_deliver_{order['id']}"),
         InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"order_delete_{order['id']}")]
    ])
    await message.edit_text(order_text, parse_mode="HTML", reply_markup=keyboard)

# ================= КОМАНДЫ =================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Открыть магазин", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton(text="📞 Связаться с менеджером", url="https://t.me/Toxin_TOP")]
    ])
    await message.answer("💨 *VAPEhyz shop*\n\n🔥 Эксклюзивные девайсы и жидкости.\n🔞 Строго 18+\n\nВыберите действие:", parse_mode="Markdown", reply_markup=keyboard)

@dp.message(Command("menu"))
async def menu_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Открыть витрину", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])
    await message.answer("💨 *VAPEhyz shop*\n\nНажмите на кнопку, чтобы открыть витрину:", parse_mode="Markdown", reply_markup=keyboard)

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к админ-панели")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛠 Открыть админ-панель", web_app=WebAppInfo(url=f"{WEB_APP_URL}/admin.html"))]
    ])
    await message.answer("🛠 *Админ-панель*\n\nУправляйте товарами и заказами через интерфейс:", parse_mode="Markdown", reply_markup=keyboard)

# ================= ВЕБХУК =================
async def webhook_handler(request):
    try:
        data = await request.json()
        if 'update_id' not in data:
            return web.Response(status=200)
        valid_keys = ['update_id', 'message', 'callback_query', 'inline_query', 
                     'chosen_inline_result', 'shipping_query', 'pre_checkout_query', 
                     'poll', 'poll_answer', 'my_chat_member', 'chat_member', 
                     'chat_boost', 'removed_chat_boost']
        update_data = {key: data[key] for key in valid_keys if key in data}
        update = types.Update(**update_data)
        await dp.feed_update(bot, update)
        return web.Response(status=200)
    except Exception as e:
        logging.error(f"Ошибка вебхука: {e}")
        return web.Response(status=400)

# ================= API =================
async def handle_api(request):
    sort_by = request.query.get('sort', 'popular')
    
    api_products = []
    for p in PRODUCTS:
        if p.get('variants') and len(p['variants']) > 0:
            variants_list = []
            min_price = p['price']
            for variant in p['variants']:
                variant_price = variant.get('price', p['price'])
                variants_list.append({
                    "name": variant['name'],
                    "price": variant_price
                })
                if variant_price < min_price:
                    min_price = variant_price
            
            api_products.append({
                "id": p["id"],
                "name": p["name"],
                "price": min_price,
                "category": p.get("category", "Без категории"),
                "subcategory": p.get("subcategory", ""),
                "description": p.get("description", ""),
                "image": p.get("image", ""),
                "available": p["available"],
                "parent_id": None,
                "is_variant": False,
                "variants": variants_list,
                "has_variants": True,
                "created_at": p.get("created_at", "")
            })
        else:
            api_products.append({
                "id": p["id"],
                "name": p["name"],
                "price": p["price"],
                "category": p.get("category", "Без категории"),
                "subcategory": p.get("subcategory", ""),
                "description": p.get("description", ""),
                "image": p.get("image", ""),
                "available": p["available"],
                "parent_id": None,
                "is_variant": False,
                "variants": [],
                "has_variants": False,
                "created_at": p.get("created_at", "")
            })
    
    if sort_by == 'price_asc':
        api_products.sort(key=lambda x: x['price'])
    elif sort_by == 'price_desc':
        api_products.sort(key=lambda x: x['price'], reverse=True)
    
    return web.Response(
        text=json.dumps(api_products, ensure_ascii=False),
        content_type='application/json',
        headers={"Access-Control-Allow-Origin": "*"}
    )

async def handle_order(request):
    try:
        data = await request.json()
        order = {
            "id": len(ORDERS) + 1,
            "user_id": data.get('user_id'),
            "user_name": data.get('user_name', 'Пользователь'),
            "username": data.get('username', ''),
            "items": data.get('items', []),
            "total": data.get('total', 0),
            "status": "Новый",
            "created_at": datetime.now().isoformat()
        }
        ORDERS.append(order)
        save_orders(ORDERS)
        await send_order_to_admins(order)
        
        customer_text = f"✅ <b>Ваш заказ #{order['id']} принят!</b>\n\n💰 Сумма: {order['total']} ₽\n📦 Товаров: {len(order['items'])}\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n🔄 Ожидайте подтверждения от менеджера."
        await bot.send_message(order["user_id"], customer_text, parse_mode="HTML")
        return web.Response(text=json.dumps({"status": "success"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        logging.error(f"Ошибка оформления заказа: {e}")
        return web.Response(text=json.dumps({"status": "error", "message": str(e)}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"}, status=400)

async def handle_user_orders(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        user_orders = [o for o in ORDERS if o["user_id"] == user_id]
        user_orders.sort(key=lambda x: x["id"], reverse=True)
        return web.Response(text=json.dumps({"orders": user_orders}, ensure_ascii=False), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return web.Response(text=json.dumps({"status": "error", "message": str(e)}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"}, status=400)

async def handle_cancel_order(request):
    try:
        data = await request.json()
        order_id, user_id = data.get('order_id'), data.get('user_id')
        order = next((o for o in ORDERS if o["id"] == order_id), None)
        if not order:
            return web.Response(text=json.dumps({"status": "error", "message": "Заказ не найден"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"}, status=404)
        if order["user_id"] != user_id:
            return web.Response(text=json.dumps({"status": "error", "message": "Это не ваш заказ"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"}, status=403)
        if order["status"] in ["Доставлен", "Отменён"]:
            return web.Response(text=json.dumps({"status": "error", "message": f"Заказ уже {order['status'].lower()}"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"}, status=400)
        
        order["status"] = "Отменён"
        save_orders(ORDERS)
        
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, f"❌ <b>ЗАКАЗ #{order_id} ОТМЕНЁН ПОКУПАТЕЛЕМ</b>\n\n👤 {order['user_name']}\n💰 {order['total']} ₽\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}", parse_mode="HTML")
        await bot.send_message(user_id, f"❌ <b>Ваш заказ #{order_id} отменён</b>\n\nЕсли вы хотите его восстановить, свяжитесь с менеджером.", parse_mode="HTML")
        return web.Response(text=json.dumps({"status": "success"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return web.Response(text=json.dumps({"status": "error", "message": str(e)}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"}, status=400)

# ================= API ДЛЯ АДМИН-ПАНЕЛИ =================
async def admin_api(request):
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            reader = await request.multipart()
            field = await reader.next()
            data = {}
            while field is not None:
                if field.name == 'action':
                    data['action'] = await field.text()
                elif field.name == 'product':
                    data['product'] = json.loads(await field.text())
                elif field.name == 'image' and field.filename:
                    filename = f"{datetime.now().timestamp()}_{field.filename}"
                    filepath = os.path.join(IMAGES_FOLDER, filename)
                    with open(filepath, 'wb') as f:
                        while True:
                            chunk = await field.read_chunk()
                            if not chunk:
                                break
                            f.write(chunk)
                    data['image_path'] = f"/{IMAGES_FOLDER}/{filename}"
                field = await reader.next()
            action, product = data.get('action'), data.get('product', {})
            if data.get('image_path'):
                product['image'] = data['image_path']
        else:
            data = await request.json()
            action, product = data.get('action'), data.get('product', {})
        
        if action == 'get_products':
            return web.Response(text=json.dumps(PRODUCTS, ensure_ascii=False), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
        elif action == 'add_product':
            product['id'] = max([p["id"] for p in PRODUCTS], default=0) + 1
            product['available'] = True
            product['variants'] = []
            product['created_at'] = datetime.now().isoformat()
            product['image'] = product.get('image', "/product_images/default.png")
            PRODUCTS.append(product)
            save_products(PRODUCTS)
            return web.Response(text=json.dumps({"status": "success", "product": product}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
        elif action == 'update_product':
            for i, p in enumerate(PRODUCTS):
                if p["id"] == product.get('id'):
                    if 'image' not in product:
                        product['image'] = p.get('image')
                    PRODUCTS[i] = product
                    break
            save_products(PRODUCTS)
            return web.Response(text=json.dumps({"status": "success"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
        elif action == 'delete_product':
            product_id = data.get('id')
            PRODUCTS[:] = [p for p in PRODUCTS if p["id"] != product_id]
            save_products(PRODUCTS)
            return web.Response(text=json.dumps({"status": "success"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
        elif action == 'toggle_product':
            product_id = data.get('id')
            for p in PRODUCTS:
                if p["id"] == product_id:
                    p["available"] = not p["available"]
                    break
            save_products(PRODUCTS)
            return web.Response(text=json.dumps({"status": "success"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
        elif action == 'add_variant':
            product_id, variant = data.get('product_id'), data.get('variant', {})
            for p in PRODUCTS:
                if p["id"] == product_id:
                    p.setdefault('variants', []).append(variant)
                    break
            save_products(PRODUCTS)
            return web.Response(text=json.dumps({"status": "success"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
        elif action == 'delete_variant':
            product_id, variant_index = data.get('product_id'), data.get('variant_index')
            for p in PRODUCTS:
                if p["id"] == product_id and 'variants' in p and 0 <= variant_index < len(p['variants']):
                    del p['variants'][variant_index]
                    break
            save_products(PRODUCTS)
            return web.Response(text=json.dumps({"status": "success"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
        elif action == 'get_orders':
            return web.Response(text=json.dumps(ORDERS, ensure_ascii=False), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
        elif action == 'update_order_status':
            order_id, status = data.get('id'), data.get('status')
            for o in ORDERS:
                if o["id"] == order_id:
                    o["status"] = status
                    break
            save_orders(ORDERS)
            return web.Response(text=json.dumps({"status": "success"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
        elif action == 'delete_order':
            order_id = data.get('id')
            ORDERS[:] = [o for o in ORDERS if o["id"] != order_id]
            save_orders(ORDERS)
            return web.Response(text=json.dumps({"status": "success"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"})
        else:
            return web.Response(text=json.dumps({"status": "error", "message": "Unknown action"}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"}, status=400)
    except Exception as e:
        logging.error(f"Ошибка админ API: {e}")
        return web.Response(text=json.dumps({"status": "error", "message": str(e)}), content_type='application/json', headers={"Access-Control-Allow-Origin": "*"}, status=400)

# ================= ОБРАБОТЧИКИ СТРАНИЦ =================
async def index_handler(request):
    try:
        return web.FileResponse('index.html')
    except FileNotFoundError:
        return web.Response(text="<h1>Файл index.html не найден</h1>", content_type='text/html')

async def admin_html_handler(request):
    try:
        return web.FileResponse('admin.html')
    except FileNotFoundError:
        return web.Response(text="<h1>Файл admin.html не найден</h1>", content_type='text/html')

# ================= ЗАПУСК =================
async def main():
    webhook_url = f"{WEB_APP_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logging.info(f"✅ Вебхук установлен: {webhook_url}")
    
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    app.router.add_get('/api/products', handle_api)
    app.router.add_post('/api/order', handle_order)
    app.router.add_post('/api/admin', admin_api)
    app.router.add_post('/api/user_orders', handle_user_orders)
    app.router.add_post('/api/cancel_order', handle_cancel_order)
    app.router.add_get('/', index_handler)
    app.router.add_get('/admin.html', admin_html_handler)
    app.router.add_static('/product_images', IMAGES_FOLDER)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"✅ Сервер запущен на порту {PORT}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("⚠️ Бот остановлен")
    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")