import json
import random
import urllib.parse
import urllib.request
import requests
import re
import sys
import time
import asyncio
import os
from playwright.async_api import async_playwright

# Ensure stdout/stderr handles Unicode characters on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
def load_topics_list():
    try:
        with open('topics.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[-] Error reading topics.json: {e}")
        sys.exit(1)

TOPICS_LIST = load_topics_list()

def load_env():
    env = {
        'tgbotapi': os.environ.get('TELEGRAM_BOT_TOKEN'),
        'chatid': os.environ.get('TELEGRAM_CHAT_ID'),
        'phone': os.environ.get('CHORCHA_PHONE'),
        'password': os.environ.get('CHORCHA_PASS'),
        'chorcha_name': os.environ.get('CHORCHA_NAME')
    }
    # Fallback to .env file if not present in env
    if not env['tgbotapi'] or not env['chatid'] or not env['phone'] or not env['password'] or not env['chorcha_name']:
        try:
            if os.path.exists('.env'):
                with open('.env', 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith('tgbotapi:'):
                            env['tgbotapi'] = line[len('tgbotapi:'):].strip()
                        elif line.startswith('tgbotapi='):
                            env['tgbotapi'] = line[len('tgbotapi='):].strip()
                        elif line.startswith('chatid:'):
                            env['chatid'] = line[len('chatid:'):].strip()
                        elif line.startswith('chatid='):
                            env['chatid'] = line[len('chatid='):].strip()
                        elif line.startswith('phone:'):
                            env['phone'] = line[len('phone:'):].strip()
                        elif line.startswith('phone='):
                            env['phone'] = line[len('phone='):].strip()
                        elif line.startswith('password:'):
                            env['password'] = line[len('password:'):].strip()
                        elif line.startswith('password='):
                            env['password'] = line[len('password='):].strip()
                        elif line.startswith('chorcha_name:'):
                            env['chorcha_name'] = line[len('chorcha_name:'):].strip()
                        elif line.startswith('chorcha_name='):
                            env['chorcha_name'] = line[len('chorcha_name='):].strip()
                        elif line.startswith('CHORCHA_NAME:'):
                            env['chorcha_name'] = line[len('CHORCHA_NAME:'):].strip()
                        elif line.startswith('CHORCHA_NAME='):
                            env['chorcha_name'] = line[len('CHORCHA_NAME='):].strip()
        except Exception as e:
            print(f"[-] Warning: Failed to load .env: {e}")
    return env

def send_telegram_report(env, topic_name, battle_url, answered_count, total_questions, screenshot_path):
    token = env.get('tgbotapi')
    chat_id = env.get('chatid')
    if not token or not chat_id:
        print("[-] Telegram credentials missing in .env. Skipping report.")
        return
    
    chorcha_name = env.get('chorcha_name') or 'N/A'
    caption = (
        f"🏆 *Chorcha Battle Report* 🏆\n\n"
        f"👤 *AC:* {chorcha_name}\n"
        f"📖 *Topic:* {topic_name}\n"
        f"🔗 [Battle URL]({battle_url})\n"
        f"✅ *Questions Answered:* {answered_count}/{total_questions}\n\n"
        f"🤖 _Automated by Chorcha Bot_"
    )
    
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        with open(screenshot_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            data = {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'Markdown'
            }
            res = requests.post(url, data=data, files=files)
            if res.status_code == 200:
                print("[+] Telegram report sent successfully.")
            else:
                print(f"[-] Failed to send Telegram report: HTTP {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[-] Error sending Telegram report: {e}")

def send_telegram_text_message(env, text):
    token = env.get('tgbotapi')
    chat_id = env.get('chatid')
    if not token or not chat_id:
        print("[-] Telegram credentials missing. Skipping report.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            print("[+] Telegram text report sent successfully.")
            return response.read()
    except Exception as e:
        print(f"[-] Error sending Telegram text report: {e}")

def decode_value(encoded_str, key):
    if not key:
        return encoded_str
    decoded = []
    key_len = len(key)
    for i, char in enumerate(encoded_str):
        cp = ord(char)
        kc = ord(key[i % key_len])
        decoded.append(chr((cp - kc + 65536) % 65536))
    return "".join(decoded)

def decode_object(obj, key):
    if isinstance(obj, str):
        return decode_value(obj, key)
    elif isinstance(obj, list):
        return [decode_object(item, key) for item in obj]
    elif isinstance(obj, dict):
        return {k: decode_object(v, key) for k, v in obj.items()}
    return obj

def load_cookies_for_requests():
    try:
        cookie_env = os.environ.get('COOKIE_JSON')
        if cookie_env:
            return json.loads(cookie_env)
        if os.path.exists('cookie.json'):
            with open('cookie.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[-] Error reading cookie.json: {e}")
    return []

def format_cookies_for_playwright(cookies_list):
    formatted = []
    for c in cookies_list:
        cookie = {
            'name': c['name'],
            'value': c['value'],
            'domain': c['domain'],
            'path': c['path']
        }
        if 'secure' in c:
            cookie['secure'] = c['secure']
        if 'httpOnly' in c:
            cookie['httpOnly'] = c['httpOnly']
        if 'sameSite' in c and c['sameSite'] is not None:
            same_site = str(c['sameSite']).capitalize()
            if same_site in ["Strict", "Lax", "None"]:
                cookie['sameSite'] = same_site
        if 'expirationDate' in c:
            cookie['expires'] = int(c['expirationDate'])
        formatted.append(cookie)
    return formatted

async def ensure_authenticated(env, force_login=False):
    cookies_list = []
    auth_file = 'cookie.json'
    
    # Load current cookies
    try:
        cookie_env = os.environ.get('COOKIE_JSON')
        if cookie_env:
            cookies_list = json.loads(cookie_env)
        elif os.path.exists(auth_file):
            with open(auth_file, 'r', encoding='utf-8') as f:
                cookies_list = json.load(f)
    except Exception as e:
        print(f"[-] Warning reading cookies: {e}")
        
    formatted_cookies = format_cookies_for_playwright(cookies_list)
    
    async with async_playwright() as p:
        is_headless = os.environ.get('GITHUB_ACTIONS') == 'true' or os.environ.get('HEADLESS') == 'true'
        browser = await p.chromium.launch(headless=is_headless)
        
        context_args = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        context = await browser.new_context(**context_args)
        if formatted_cookies:
            await context.add_cookies(formatted_cookies)
            
        page = await context.new_page()
        
        needs_login = force_login
        if not needs_login:
            # Test navigation to practice exam (requires authentication)
            print("[*] Verifying session validity...")
            try:
                await page.goto("https://chorcha.net/practice-exam", wait_until="commit", timeout=20000)
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"[-] Initial navigation verification timed out: {e}")
                
            # Check if login is needed
            if "auth/register" in page.url or "register" in page.url or "login" in page.url:
                needs_login = True
            else:
                try:
                    login_btn = page.locator('text="লগইন", text="Login"').first
                    if await login_btn.is_visible():
                        needs_login = True
                except Exception:
                    pass
                
        if not needs_login:
            print("[+] Session is valid. No login required.")
            await context.close()
            await browser.close()
            return cookies_list
            
        # Session is expired/invalid, try auto-login
        print("[-] Stored session is invalid or expired. Attempting automatic login...")
        phone = env.get('phone')
        password = env.get('password')
        
        is_credentials_configured = (
            phone and password and 
            phone.strip() and password.strip() and 
            "01XXXXXXXXX" not in phone
        )
        
        if not is_credentials_configured:
            print("[-] Login credentials (phone/password) not configured in env/.env.")
            msg = (
                "⚠️ <b>Chorcha Bot Alert</b> ⚠️\n"
                "───────────────────────────\n"
                "❌ <b>Status:</b> Session Expired / Login Required\n"
                "📢 <b>Action Required:</b> Stored cookies have expired, and login credentials are not configured in your <code>.env</code> file. Please update <code>cookie.json</code> manually or configure <code>phone</code> and <code>password</code> in <code>.env</code>."
            )
            send_telegram_text_message(env, msg)
            await context.close()
            await browser.close()
            raise RuntimeError("COOKIE_EXPIRED: Session expired and credentials not configured.")
            
        try:
            await page.goto("https://chorcha.net/auth/register", wait_until="networkidle", timeout=25000)
            
            # Step 1: Phone input
            await page.wait_for_selector('input[placeholder="01XXXXXXXXX"]', timeout=15000)
            await page.fill('input[placeholder="01XXXXXXXXX"]', phone)
            
            # Click proceed button
            await page.click('button:has-text("এগিয়ে যাও")')
            
            # Step 2: Password input
            await page.wait_for_selector('input[placeholder="Password"]', timeout=15000)
            await page.fill('input[placeholder="Password"]', password)
            
            # Click login button
            await page.click('button:has-text("লগইন করো")')
            
            # Wait for dashboard navigation or token cookie
            login_success = False
            for _ in range(20):
                await page.wait_for_timeout(500)
                if "dashboard" in page.url:
                    login_success = True
                    break
                cookies = await context.cookies()
                if any(c.get('name') == 'token' for c in cookies):
                    login_success = True
                    break
            
            if not login_success:
                raise RuntimeError("Login did not navigate to dashboard or set token cookie.")
                
            # Retrieve and save new cookies
            cookies = await context.cookies()
            # Convert Playwright cookie format to JSON format (sameSite and expires)
            json_cookies = []
            for c in cookies:
                jc = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c["domain"],
                    "path": c["path"]
                }
                if "expires" in c:
                    jc["expirationDate"] = c["expires"]
                if "httpOnly" in c:
                    jc["httpOnly"] = c["httpOnly"]
                if "secure" in c:
                    jc["secure"] = c["secure"]
                if "sameSite" in c:
                    jc["sameSite"] = c["sameSite"].lower()
                json_cookies.append(jc)
                
            with open(auth_file, "w", encoding="utf-8") as f:
                json.dump(json_cookies, f, indent=4)
            print("[+] Automatic login successful. New cookies saved to cookie.json.")
            
            await context.close()
            await browser.close()
            return json_cookies
            
        except Exception as e:
            print(f"[-] Automatic login failed: {e}")
            msg = (
                "⚠️ <b>Chorcha Bot Alert</b> ⚠️\n"
                "───────────────────────────\n"
                "❌ <b>Status:</b> Automatic Login Failed\n"
                "📢 <b>Action Required:</b> Stored cookies have expired, and the bot's attempt to log in automatically using the provided credentials failed. Please log in manually and update <code>cookie.json</code>."
            )
            send_telegram_text_message(env, msg)
            await context.close()
            await browser.close()
            raise RuntimeError(f"COOKIE_EXPIRED: Automatic login failed: {e}")

def create_battle_rooms(session, count):
    urls = []
    print(f"[*] Starting creation of {count} battle room(s)...")
    for i in range(1, count + 1):
        topic = random.choice(TOPICS_LIST)
        topic_id = topic['TOPIC_ID']
        topic_name = topic['TOPIC_NAME']

        print(f"[{i}/{count}] Selecting topic: {topic_name} (ID: {topic_id})")

        # Step 1: Quick Exam API
        quick_url = "https://mujib.chorcha.net/exam/quick"
        try:
            res = session.post(quick_url, json={"topics": [topic_id], "type": "BATTLE"}, headers={"Content-Type": "application/json"})
            if res.status_code != 200:
                print(f"    [-] Quick Exam API failed with status {res.status_code}")
                continue
            druto_id = res.json().get('data', {}).get('druto_id')
            if not druto_id:
                print(f"    [-] druto_id not found in response: {res.text}")
                continue
            
            # Step 2: Battle Create API
            create_url = "https://mujib.chorcha.net/battle/create"
            res = session.post(create_url, json={
                "druto_id": druto_id,
                "topic_id": topic_id,
                "challenge_type": "friends",
                "topic_name": topic_name
            }, headers={"Content-Type": "application/json"})
            
            if res.status_code != 200:
                print(f"    [-] Battle Create API failed with status {res.status_code}")
                continue
            
            room_id = res.json().get('data', {}).get('room_id')
            if not room_id:
                print(f"    [-] room_id not found in response: {res.text}")
                continue

            battle_url = f"https://chorcha.net/battle/{room_id}?topic={urllib.parse.quote(topic_name)}&druto_id={druto_id}"
            print(f"    [+] Created battle room: {battle_url}")
            urls.append(battle_url)
            
            # Delay to avoid rate limiting
            time.sleep(2)
        except Exception as e:
            print(f"    [-] Exception creating battle room: {e}")
    return urls

def fetch_and_decode_answers(session, druto_id):
    config_url = "https://mujib.chorcha.net/battle/exam-config"
    headers = {
        'Content-Type': 'application/json'
    }
    try:
        res = session.post(config_url, json={"druto_id": druto_id}, headers=headers)
        if res.status_code != 200:
            print(f"[-] Failed to fetch battle answers config: HTTP {res.status_code}")
            return None
        
        data = res.json()
        
        # Extract questions from raw plaintext response
        questions = (
            data.get('data', {}).get('questions') or 
            data.get('data', {}).get('exam_questions') or 
            data.get('questions') or 
            []
        )
        
        answers_map = {}
        for idx, q in enumerate(questions):
            ans_val = q.get('answer')
            correct_idx = q.get('correct_answer')
            
            if correct_idx is not None:
                answers_map[idx + 1] = int(correct_idx)
            elif ans_val is not None:
                ans_str = str(ans_val).upper().strip()
                mapping = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
                if ans_str in mapping:
                    answers_map[idx + 1] = mapping[ans_str]
                else:
                    try:
                        answers_map[idx + 1] = int(ans_str)
                    except ValueError:
                        answers_map[idx + 1] = ans_str
        
        return answers_map
    except Exception as e:
        print(f"[-] Exception fetching answers: {e}")
        return None

async def play_battle(context, url_idx, url, session):
    print(f"\n========================================")
    print(f"[*] [{url_idx}] Starting Battle URL: {url}")
    print(f"========================================")
    
    # Extract druto_id
    match = re.search(r'BATTLE_[a-zA-Z0-9_\-]+', url)
    if not match:
        print(f"[-] [{url_idx}] Could not extract druto_id from URL. Skipping.")
        return
    druto_id = match.group(0)
    
    # Fetch answers (non-blocking via executor)
    loop = asyncio.get_event_loop()
    answers_map = await loop.run_in_executor(None, fetch_and_decode_answers, session, druto_id)
    if not answers_map:
        print(f"[-] [{url_idx}] Could not fetch answers. Skipping.")
        return
    print(f"[+] [{url_idx}] Loaded {len(answers_map)} answers.")
    
    page = await context.new_page()
    await page.goto(url)
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    
    # Click "ব্যাটেল শুরু করো"
    try:
        start_btn = page.locator("button:has-text('ব্যাটেল শুরু করো')")
        await start_btn.wait_for(state="visible", timeout=10000)
        await start_btn.click()
        print(f"[+] [{url_idx}] Clicked 'ব্যাটেল শুরু করো'")
    except Exception as e:
        print(f"[-] [{url_idx}] Start button not found or click failed (maybe already started): {e}")
    
    # Wait for battle to start (when 4 non-empty option buttons appear)
    print(f"[*] [{url_idx}] Waiting for opponent to join and battle to start...")
    start_wait_time = time.time()
    last_log_time = time.time()
    
    while True:
        try:
            # Find all buttons
            buttons = await page.locator("button.custom-scrollbar, button.flex.w-full.gap-2.rounded-lg").all()
            non_empty_buttons = []
            for btn in buttons:
                try:
                    txt = (await btn.inner_text()).strip()
                    if txt:
                        non_empty_buttons.append(btn)
                except Exception:
                    pass
            
            if len(non_empty_buttons) >= 4:
                print(f"[+] [{url_idx}] Opponent joined! Battle started after {int(time.time() - start_wait_time)}s.")
                break
        except Exception as e:
            print(f"[-] [{url_idx}] Error checking battle start status: {e}")
            break
        
        # Log status every 5 seconds
        if time.time() - last_log_time >= 5:
            elapsed = int(time.time() - start_wait_time)
            print(f"[*] [{url_idx}] Still waiting for opponent... ({elapsed}s elapsed)")
            last_log_time = time.time()
        
        await page.wait_for_timeout(1000)
    
    # Answering loop
    last_signature = ""
    answered_count = 0
    total_questions = len(answers_map)
    consecutive_misses = 0
    
    while answered_count < total_questions:
        # Find current options
        buttons = await page.locator("button.custom-scrollbar, button.flex.w-full.gap-2.rounded-lg").all()
        if len(buttons) < 4:
            await page.wait_for_timeout(500)
            consecutive_misses += 1
            if consecutive_misses > 120: # 60 seconds of no options during active battle
                print(f"[-] [{url_idx}] Timeout waiting for question options. Ending battle loop.")
                break
            continue
        
        consecutive_misses = 0
        
        # Check if already answered (highlighted options)
        has_been_answered = False
        for btn in buttons:
            class_name = await btn.get_attribute("class") or ""
            if any(highlight in class_name for highlight in [
                'bg-[#1899181a]', 'bg-[#1899181A]', 'border-[#189918]', 
                'bg-[#FFF1F1]', 'border-[#AF5454]', 'bg-[#ef444430]', 'bg-[#EF444430]'
            ]):
                has_been_answered = True
                break
        
        if has_been_answered:
            await page.wait_for_timeout(500)
            continue
        
        # Build question signature
        options_texts = []
        for btn in buttons:
            try:
                options_texts.append((await btn.inner_text()).strip())
            except Exception:
                options_texts.append("")
        
        # Retrieve question text via page.evaluate
        try:
            question_text = await page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button.custom-scrollbar, button.flex.w-full.gap-2.rounded-lg')).filter(b => b.innerText.trim() !== "");
                if (btns.length === 0) return "";
                const firstBtn = btns[0];
                const parent = firstBtn.parentElement;
                if (parent) {
                    const prev = parent.previousElementSibling;
                    if (prev && prev.innerText.trim()) return prev.innerText.trim();
                    const grandparent = parent.parentElement;
                    if (grandparent) {
                        const gpPrev = grandparent.previousElementSibling;
                        if (gpPrev && gpPrev.innerText.trim()) return gpPrev.innerText.trim();
                    }
                }
                return "";
            }""")
        except Exception:
            question_text = ""
        
        current_signature = f"{question_text}||{'|'.join(options_texts)}"
        if current_signature == last_signature:
            # Still waiting for a new question transition
            await page.wait_for_timeout(200)
            continue
        
        # Wait 0.5 to 2 seconds before answering to mimic human behavior
        await page.wait_for_timeout(random.randint(500, 2000))
        
        # Answer question
        q_num = answered_count + 1
        correct_idx = answers_map.get(q_num)
        
        if correct_idx is None:
            print(f"[-] [{url_idx}] No answer mapped for Q{q_num}. Choosing default index 0.")
            correct_idx = 0
        
        if isinstance(correct_idx, str):
            mapping = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
            correct_idx = mapping.get(correct_idx.upper(), 0)
        
        # Force one wrong answer (specifically the 15th question) to mimic human mistake
        if q_num == 15:
            print(f"[*] [{url_idx}] Applying noise injection to make Q{q_num} wrong for human emulation.")
            num_options = len(buttons) if len(buttons) > 0 else 4
            correct_idx = (correct_idx + 1) % num_options
            
        print(f"[+] [{url_idx}] Q{q_num}/{total_questions}: Answering with Option {correct_idx + 1}...")
        
        try:
            await buttons[correct_idx].click()
            last_signature = current_signature
            answered_count += 1
        except Exception as e:
            print(f"[-] [{url_idx}] Failed to click option button: {e}")
            await page.wait_for_timeout(500)
    
    print(f"[+] [{url_idx}] All questions answered. Waiting 3.5 seconds to load scoreboard...")
    await page.wait_for_timeout(6000)
    
    # Take screenshot
    screenshot_path = f"battle_result_{url_idx}.png"
    try:
        await page.screenshot(path=screenshot_path)
        print(f"[+] [{url_idx}] Screenshot captured: {screenshot_path}")
    except Exception as e:
        print(f"[-] [{url_idx}] Failed to capture screenshot: {e}")
        screenshot_path = None
    
    # Send telegram report
    if screenshot_path:
        env = await loop.run_in_executor(None, load_env)
        # Parse topic name from URL or config
        topic_name = "Unknown Topic"
        match_topic = re.search(r'topic=([^&]+)', url)
        if match_topic:
            topic_name = urllib.parse.unquote(match_topic.group(1))
        
        await loop.run_in_executor(
            None,
            send_telegram_report,
            env,
            topic_name,
            url,
            answered_count,
            total_questions,
            screenshot_path
        )
    
    await page.close()
    print(f"[+] [{url_idx}] Finished Battle.")

async def run_battle_automation(urls, cookies_list, session):
    formatted_cookies = format_cookies_for_playwright(cookies_list)
    
    async with async_playwright() as p:
        # Run headless dynamically if in a CI environment (like GitHub Actions)
        is_headless = os.environ.get('GITHUB_ACTIONS') == 'true' or os.environ.get('HEADLESS') == 'true'
        browser = await p.chromium.launch(headless=is_headless)
        context = await browser.new_context()
        await context.add_cookies(formatted_cookies)
        
        print("[*] Playwright browser launched and cookies injected.")
        
        # Start all battles in parallel
        tasks = []
        for url_idx, url in enumerate(urls, 1):
            tasks.append(play_battle(context, url_idx, url, session))
        
        await asyncio.gather(*tasks)
        await context.close()
        await browser.close()
    print("\n[*] All automation runs completed successfully!")

def test_session_validity(session):
    test_url = "https://mujib.chorcha.net/exam/quick"
    if not TOPICS_LIST:
        return False
    topic_id = TOPICS_LIST[0]['TOPIC_ID']
    try:
        res = session.post(test_url, json={"topics": [topic_id], "type": "BATTLE"}, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get('status') != 'error' and data.get('data', {}).get('druto_id'):
                return True
    except Exception as e:
        print(f"[-] Session test request failed: {e}")
    return False

def main():
    # Load environment variables
    env = load_env()
    
    # Load cookies
    cookies_list = load_cookies_for_requests()
    
    # Initialize request session
    session = requests.Session()
    # Configure user-agent and headers to avoid request block issues
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json"
    })
    for cookie in cookies_list:
        session.cookies.set(
            name=cookie['name'],
            value=cookie['value'],
            domain=cookie.get('domain', '.chorcha.net'),
            path=cookie.get('path', '/')
        )
        
    print("[*] Verifying session validity via API...")
    if not test_session_validity(session):
        print("[-] Stored session is invalid or expired. Attempting automatic login...")
        try:
            cookies_list = asyncio.run(ensure_authenticated(env, force_login=True))
        except Exception as e:
            print(f"[-] Authentication check failed: {e}")
            sys.exit(1)
            
        # Re-initialize request session with new cookies
        session.cookies.clear()
        for cookie in cookies_list:
            session.cookies.set(
                name=cookie['name'],
                value=cookie['value'],
                domain=cookie.get('domain', '.chorcha.net'),
                path=cookie.get('path', '/')
            )
            
        # Verify again
        if not test_session_validity(session):
            print("[-] Automatic login completed but session is still invalid.")
            sys.exit(1)
        print("[+] Automatic login successful and verified.")
    else:
        print("[+] Session is valid. No login required.")
    
    # Check command-line arguments first, fallback to default or prompt
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        count = int(sys.argv[1])
    else:
        try:
            count_input = input("How many battle rooms do you want to create? (default 5): ").strip()
            if count_input.isdigit():
                count = int(count_input)
            else:
                count = 8
        except (IOError, EOFError):
            print("[*] Non-interactive environment detected. Defaulting to 1 room.")
            count = 1
        
    # Step 1 & 2: Create battle rooms
    urls = create_battle_rooms(session, count)
    if not urls:
        print("[-] No battle rooms were created. Exiting.")
        return
        
    # Run Playwright automation to solve the battles
    asyncio.run(run_battle_automation(urls, cookies_list, session))

if __name__ == "__main__":
    main()
