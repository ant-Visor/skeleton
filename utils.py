"""
Utility functions for modules
"""

from pathlib import Path
from telethon.tl.types import Message


def get_module_dir(module_file: str) -> Path:
  """
  Get path to module's directory.
  
  Usage in module:
    from ... import utils
    module_dir = utils.get_module_dir(__file__)
    # ub/modules/mymodule/
    
    db_path = module_dir / "data.db"
  """
  return Path(module_file).parent


def get_args(message: Message) -> str:
  """
  Get command arguments from message
  
  Example:
    .cmd arg1 arg2 -> "arg1 arg2"
  """
  text = message.text or ""
  parts = text.split(maxsplit=1)
  return parts[1] if len(parts) > 1 else ""


def get_args_list(message: Message) -> list:
  """
  Get command arguments as list
  
  Example:
    .cmd arg1 arg2 -> ["arg1", "arg2"]
  """
  args = get_args(message)
  return args.split() if args else []


async def answer(message: Message, text: str, **kwargs):
  """
  Reply to or edit message with text
  
  If outgoing message - edits it
  If incoming message - replies to it
  """
  if message.out:
    await message.edit(text, **kwargs)
  else:
    await message.reply(text, **kwargs)
