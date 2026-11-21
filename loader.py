"""
Module loader - finds and loads modules from ub/modules/
"""

import asyncio
import importlib
import inspect
import logging
import os
from pathlib import Path
from typing import Callable, Dict, List

from telethon import TelegramClient
from telethon.events import NewMessage

logger = logging.getLogger(__name__)


class Module:
  """Base class for all modules"""
  
  name: str = "Unknown"
  description: str = ""
  
  def __init__(self, client: TelegramClient):
    self._client = client
    self._handlers: List[tuple] = []
  
  async def on_load(self):
    """Called when module is loaded"""
    pass
  
  async def on_unload(self):
    """Called when module is unloaded"""
    pass


def command(pattern: str = None, outgoing: bool = True, incoming: bool = False):
  """
  Decorator to mark a method as command handler
  
  Usage:
    @command(pattern="ping")
    async def ping_cmd(self, message):
      await message.edit("Pong!")
  """
  def decorator(func: Callable):
    func._is_command = True
    func._pattern = pattern or func.__name__
    func._outgoing = outgoing
    func._incoming = incoming
    return func
  return decorator


class ModuleLoader:
  """Loads and manages modules"""
  
  def __init__(self, client: TelegramClient, modules_dir: str = None):
    self.client = client
    self.modules_dir = modules_dir or str(Path(__file__).parent / "modules")
    self.modules: Dict[str, Module] = {}
    self.prefix = "."
  
  async def load_all(self, required_modules: set[str] | None = None):
    """Load all modules from modules directory"""
    if not os.path.exists(self.modules_dir):
      logger.warning(f"Modules directory not found: {self.modules_dir}")
      if required_modules:
        raise RuntimeError(f"Required modules directory not found: {self.modules_dir}")
      return
    
    for name in os.listdir(self.modules_dir):
      module_dir = os.path.join(self.modules_dir, name)
      # Only load directories with __init__.py
      if os.path.isdir(module_dir) and not name.startswith("_"):
        init_file = os.path.join(module_dir, "__init__.py")
        if os.path.exists(init_file):
          try:
            await self.load_module(name)
          except Exception as e:
            logger.error(f"Failed to load module {name}: {e}")

    if required_modules:
      loaded = {name.casefold() for name in self.modules}
      missing = {name for name in required_modules if name.casefold() not in loaded}
      if missing:
        raise RuntimeError(f"Required module(s) failed to load: {', '.join(sorted(missing))}")
  
  def _find_module_folder(self, name: str) -> str | None:
    """Find module folder case-insensitively"""
    name_lower = name.lower()
    for folder in os.listdir(self.modules_dir):
      folder_path = os.path.join(self.modules_dir, folder)
      if os.path.isdir(folder_path) and folder.lower() == name_lower:
        if os.path.exists(os.path.join(folder_path, "__init__.py")):
          return folder
    return None
  
  async def load_module(self, name: str) -> bool:
    """Load a single module by name"""
    # Find actual folder name (case-insensitive)
    actual_name = self._find_module_folder(name)
    if not actual_name:
      logger.error(f"Module not found: {name}")
      return False
    
    name = actual_name
    module_dir = os.path.join(self.modules_dir, name)
    init_file = os.path.join(module_dir, "__init__.py")
    
    # Import module using package-aware import
    full_module_name = f"ub.modules.{name}"
    py_module = importlib.import_module(full_module_name)
    
    # Find Module subclass in the loaded module
    module_class = None
    for item_name in dir(py_module):
      item = getattr(py_module, item_name)
      if (
        inspect.isclass(item) 
        and issubclass(item, Module) 
        and item is not Module
      ):
        module_class = item
        break
    
    if module_class is None:
      logger.warning(f"No Module subclass found in {name}")
      return False
    
    # Instantiate module
    module_instance = module_class(self.client)
    
    # Register command handlers
    for method_name in dir(module_instance):
      method = getattr(module_instance, method_name)
      if callable(method) and getattr(method, "_is_command", False):
        pattern = getattr(method, "_pattern", method_name)
        outgoing = getattr(method, "_outgoing", True)
        incoming = getattr(method, "_incoming", False)
        
        # Create event handler
        full_pattern = f"^\\{self.prefix}{pattern}(?: |$)(.*)"
        
        @self.client.on(NewMessage(pattern=full_pattern, outgoing=outgoing, incoming=incoming))
        async def handler(event, method=method):
          try:
            await method(event)
          except Exception as e:
            logger.error(f"Error in {method.__name__}: {e}")
        
        module_instance._handlers.append((pattern, handler))
        logger.info(f"Registered command: {self.prefix}{pattern}")
    
    try:
      await module_instance.on_load()
    except (Exception, asyncio.CancelledError):
      try:
        await self._cleanup_module(module_instance)
      except Exception:
        logger.exception("Failed to clean up partially loaded module %s", name)
      raise
    
    self.modules[name] = module_instance
    logger.info(f"Loaded module: {name}")
    return True
  
  async def unload_module(self, name: str) -> bool:
    """Unload a module by name"""
    if name not in self.modules:
      return False
    
    module = self.modules[name]
    
    try:
      await self._cleanup_module(module)
    finally:
      del self.modules[name]
    logger.info(f"Unloaded module: {name}")
    return True

  async def _cleanup_module(self, module: Module):
    try:
      await module.on_unload()
    finally:
      for pattern, handler in module._handlers:
        try:
          self.client.remove_event_handler(handler)
        except Exception as e:
          logger.warning(f"Failed to remove handler {pattern}: {e}")
  
  async def reload_module(self, name: str) -> bool:
    """Reload a module (unload + load)"""
    # Find actual folder name (case-insensitive)
    actual_name = self._find_module_folder(name)
    if not actual_name:
      logger.error(f"Module not found: {name}")
      return False
    
    name = actual_name
    
    # Unload if loaded
    if name in self.modules:
      await self.unload_module(name)
    
    # Remove from sys.modules to force reimport
    import sys
    full_module_name = f"ub.modules.{name}"
    modules_to_remove = [key for key in sys.modules if key.startswith(full_module_name)]
    for key in modules_to_remove:
      del sys.modules[key]
    
    # Load again
    return await self.load_module(name)
  
  def get_commands(self) -> List[str]:
    """Get list of all registered commands"""
    commands = []
    for module in self.modules.values():
      for method_name in dir(module):
        method = getattr(module, method_name)
        if callable(method) and getattr(method, "_is_command", False):
          pattern = getattr(method, "_pattern", method_name)
          commands.append(f"{self.prefix}{pattern}")
    return commands
