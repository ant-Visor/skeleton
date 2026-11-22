"""
Main entry point for the userbot

Usage:
  python -m ub
"""


# if True: # DEBUG
#   import faulthandler
#   import os
#   import threading

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from telethon import TelegramClient
# from telethon.enums import ParseMode
from telethon.errors import (
  SessionPasswordNeededError,
  PhoneCodeInvalidError,
  PhoneCodeExpiredError,
  FloodWaitError,
  PasswordHashInvalidError,
)

from .loader import ModuleLoader

# Setup logging
logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)
# faulthandler.enable(file=sys.stderr, all_threads=True) # DEBUG

if True: # Config path
  BASE_DIR = Path(__file__).parent
  DATA_DIR = BASE_DIR / "data"
  CONFIG_FILE = DATA_DIR / "config.json"
  SESSION_FILE = DATA_DIR / "session"


def load_config() -> dict:
  """Load configuration from file"""
  if CONFIG_FILE.exists():
    with open(CONFIG_FILE, "r") as f:
      return json.load(f)
  return {}


def save_config(config: dict):
  """Save configuration to file"""
  DATA_DIR.mkdir(exist_ok=True)
  with open(CONFIG_FILE, "w") as f:
    json.dump(config, f, indent=2)


def get_credentials() -> tuple:
  """Get API credentials interactively"""
  config = load_config()
  
  api_id = config.get("api_id")
  api_hash = config.get("api_hash")
  
  if not api_id or not api_hash:
    if os.getenv("UB_NONINTERACTIVE") == "1":
      raise RuntimeError(f"Missing Telegram API credentials in {CONFIG_FILE}; check the worker data mount")
    print("\n" + "=" * 50)
    print("First time setup - enter your Telegram API credentials")
    print("Get them at https://my.telegram.org")
    print("=" * 50 + "\n")
    
    while True:
      try:
        api_id = int(input("API ID: ").strip())
        break
      except ValueError:
        print("API ID must be a number. Try again.")
    
    api_hash = input("API Hash: ").strip()
    
    config["api_id"] = api_id
    config["api_hash"] = api_hash
    save_config(config)
    
    print("\nCredentials saved!\n")
  
  return int(config["api_id"]), config["api_hash"]


async def authorize(client: TelegramClient) -> bool:
  """
  Handle full authorization flow:
  - Phone number input
  - Code verification
  - 2FA password (if enabled)
  """
  if await client.is_user_authorized():
    return True
  if os.getenv("UB_NONINTERACTIVE") == "1":
    logger.error("Saved Telegram session is not authorized; check the worker data mount and registration")
    return False
  # await client.start()
  
  print("\n" + "=" * 30)
  print("Authorization required")
  print("=" * 30 + "\n")
  
  # Get phone number
  while True:
    phone = input("Phone number (with country code, e.g. +79001234567): ").strip()
    if phone: break
    print("Phone number cannot be empty.")
  
  try:
    # Send code request
    print("\nSending code request...")
    await client.send_code_request(phone)
    
    # Get code from user
    while True:
      code = input("\nEnter the code from Telegram: ").strip()
      if code: break
      print("Code cannot be empty.")
    
    try:
      # Try to sign in with code
      await client.sign_in(phone, code)
      print("\nAuthorization successful!")
      return True
      
    except SessionPasswordNeededError:
      # 2FA is enabled
      print("\nTwo-factor authentication is enabled.")
      
      while True:
        password = input("Enter your 2FA password: ").strip()
        if password:
          break
        print("Password cannot be empty.")
      
      try:
        await client.sign_in(password=password)
        print("\nAuthorization successful!")
        return True
      except PasswordHashInvalidError:
        print("\nError: Invalid 2FA password.")
        return False
        
    except PhoneCodeInvalidError:
      print("\nError: Invalid code. Please try again.")
      return False
      
    except PhoneCodeExpiredError:
      print("\nError: Code expired. Please restart and try again.")
      return False
      
  except FloodWaitError as e:
    print(f"\nError: Too many attempts. Please wait {e.seconds} seconds.")
    return False
    
  except Exception as e:
    print(f"\nError during authorization: {e}")
    return False


#def log_thread_diagnostics(stage, dump_stacks=False):
#  threads = threading.enumerate()
#  logger.error(
#    "Thread snapshot [%s]: pid=%s count=%s",
#    stage,
#    os.getpid(),
#    len(threads),
#  )

  for thread in threads:
    logger.error(
      "Thread [%s]: name=%r ident=%s native_id=%s daemon=%s alive=%s",
      stage,
      thread.name,
      thread.ident,
      thread.native_id,
      thread.daemon,
      thread.is_alive(),
    )

  if dump_stacks:
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)


async def main():
  """Main entry point"""
  logger.info("Starting userbot...")
  # logger.info("Runtime: pid=%s entry=%s", os.getpid(), Path(__file__).resolve(),) # DEBUG
  # Get credentials
  api_id, api_hash = get_credentials()
  if os.getenv("UB_NONINTERACTIVE") == "1" and not SESSION_FILE.with_suffix(".session").is_file():
    raise RuntimeError(f"Missing Telegram session at {SESSION_FILE}.session; check the worker data mount")
  
  # Create client
  client = TelegramClient(
    str(SESSION_FILE),
    api_id,
    api_hash,
    device_model="Userbot",
    system_version="1.0",
    app_version="1.0"
  )
  
  # Set global parse mode
  client.parse_mode = "HTML"
  
  # Connect
  await client.connect()
  
  # Authorize if needed
  if not await authorize(client):
    logger.error("Authorization failed. Exiting.")
    await client.disconnect()
    sys.exit(1)
  
  me = await client.get_me()
  logger.info(f"Logged in as: {me.first_name} (@{me.username})")
  
  # Load modules
  loader = ModuleLoader(client)
  client._loader = loader
  ready_file = os.getenv("UB_READY_FILE")
  required_modules = {
    name.strip()
    for name in os.getenv("UB_REQUIRED_MODULES", "").split(",")
    if name.strip()
  }
  try:
    await loader.load_all(required_modules=required_modules)
    logger.info(f"Loaded {len(loader.modules)} module(s)")
    logger.info(f"Commands: {', '.join(loader.get_commands())}")
    logger.info("Userbot is running! Press Ctrl+C to stop.")
    if ready_file:
      Path(ready_file).touch()
    await client.run_until_disconnected()
  finally:
    if ready_file:
      Path(ready_file).unlink(missing_ok=True)
    for name in reversed(list(loader.modules)):
      try:
        await loader.unload_module(name)
      except Exception:
        logger.exception("Failed to unload module %s", name)

    try:
      await client.disconnect()
    except Exception:
      logger.exception("Failed to disconnect Telegram client")
    # Run until disconnected
 


if __name__ == "__main__":
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    logger.info("Userbot stopped.")
    
  #except Exception as e: # DEBUG
  #  logger.exception("Fatal error: %s", e)
  #  log_thread_diagnostics("fatal", dump_stacks=True)
  #
  #  faulthandler.dump_traceback_later(
  #    10,
  #    repeat=True,
  #    file=sys.stderr,
  #  )
  #  logger.critical("Reached sys.exit(1)")
  #  sys.exit(1)
  except Exception as e:
    logger.error(f"Fatal error: {e}")
    sys.exit(1)
