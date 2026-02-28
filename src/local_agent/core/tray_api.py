"""
System tray related APIs
"""
import requests
from ..logger import get_logger
from ..config import get_config

logger = get_logger()

api_host = get_config().get('message_api_url')

def get_username() -> str:
    """Get current username"""
    try:
        # Method 1: Check if running in service mode
        import os
        import getpass
        import requests
        
        # Check environment variables and command line parameters to determine service mode
        user_domain = os.environ.get('USERDOMAIN')
        response = requests.get(f"{api_host}/username", timeout=30)
        user_name = response.text.strip().replace('"', '')

        return f"{user_domain.lower()}\\{user_name}"

    except Exception as e:
        logger.error(f"Unified username recognition failed: {e}")
        # Fall back to default method on failure
        import getpass
        return getpass.getuser()

def agent_update(cmd: str) -> bool:
    """Agent update"""
    response = requests.get(
        f"{api_host}/agent_update?cmd={cmd}", 
        timeout=10000
        )
    return response.json()

