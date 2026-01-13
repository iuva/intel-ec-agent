"""
System tray related APIs
"""
import requests

api_host = "http://127.0.0.1:8001"

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
        self.logger.error(f"Unified username recognition failed: {e}")
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

