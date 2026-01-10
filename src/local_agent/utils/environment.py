"""
Environment utility class - Used to determine current runtime environment

Provides development and production environment judgment functions, based on different runtime modes for environment detection.
"""

import sys
import os
from pathlib import Path

from ..logger import get_logger

logger = get_logger(__name__)


class Environment:
    """Environment utility class, provides environment judgment functionality"""
    
    @staticmethod
    def is_development() -> bool:
        """
        Determine if currently in development environment
        
        Development environment judgment criteria:
        1. Not a PyInstaller packaged executable file
        2. Source code directory structure exists
        3. Python source code files are accessible
        
        Returns:
            bool: Returns True if in development environment, otherwise False
        """
        try:
            # Check if it's a PyInstaller packaged executable file
            if getattr(sys, 'frozen', False):
                logger.debug("Detected PyInstaller packaged environment, determined as production environment")
                return False
            
            # Check if source code directory structure exists
            current_file_path = Path(__file__).resolve()
            project_root = current_file_path.parent.parent.parent.parent  # Backtrack to project root directory
            
            # Check if src directory and local_agent package exist
            src_dir = project_root / "src"
            local_agent_dir = src_dir / "local_agent"
            
            if local_agent_dir.exists() and local_agent_dir.is_dir():
                # Check if __init__.py file exists (Python package identifier)
                init_file = local_agent_dir / "__init__.py"
                if init_file.exists():
                    logger.debug("Detected source code directory structure, determined as development environment")
                    return True
            
            # Check if setup.py or requirements.txt exist (development environment indicators)
            setup_file = project_root / "setup.py"
            requirements_file = project_root / "requirements.txt"
            
            if setup_file.exists() or requirements_file.exists():
                logger.debug("Detected development configuration files, determined as development environment")
                return True
                
            logger.debug("No development environment features detected, determined as production environment")
            return False
            
        except Exception as e:
            logger.warning(f"Environment detection exception, defaulting to production environment: {e}")
            return False
    
    @staticmethod
    def is_production() -> bool:
        """
        Determine if currently in production environment
        
        Production environment judgment criteria:
        1. Is a PyInstaller packaged executable file
        2. Source code directory structure does not exist
        3. Running in packaged environment
        
        Returns:
            bool: Returns True if in production environment, otherwise False
        """
        return not Environment.is_development()
    
    @staticmethod
    def get_environment_info() -> dict:
        """
        Get detailed information about the current environment
        
        Returns:
            dict: Dictionary containing environment information
        """
        info = {
            "is_development": Environment.is_development(),
            "is_production": Environment.is_production(),
            "is_frozen": getattr(sys, 'frozen', False),
            "executable": sys.executable,
            "python_version": sys.version,
            "platform": sys.platform,
            "current_file": __file__ if '__file__' in globals() else "Unknown"
        }
        
        # Add project path information
        try:
            current_path = Path(__file__).resolve()
            info["current_path"] = str(current_path)
            
            # Try to find project root directory
            if Environment.is_development():
                project_root = current_path.parent.parent.parent.parent
                info["project_root"] = str(project_root)
                info["has_src_dir"] = (project_root / "src").exists()
                info["has_local_agent"] = (project_root / "src" / "local_agent").exists()
            else:
                # In production environment, try to get executable file directory
                if getattr(sys, 'frozen', False):
                    info["executable_dir"] = str(Path(sys.executable).parent)
        except Exception as e:
            info["path_error"] = str(e)
        
        return info


# Convenience functions
def is_development() -> bool:
    """Convenience function: Determine if in development environment"""
    return Environment.is_development()


def is_production() -> bool:
    """Convenience function: Determine if in production environment"""
    return Environment.is_production()


def get_environment_info() -> dict:
    """Convenience function: Get environment information"""
    return Environment.get_environment_info()


if __name__ == "__main__":
    """Test code"""
    print("=== Environment Detection Test ===")
    
    # Test environment judgment
    print(f"Development environment: {is_development()}")
    print(f"Production environment: {is_production()}")
    
    # Show detailed environment information
    info = get_environment_info()
    print("\n=== Detailed Environment Information ===")
    for key, value in info.items():
        print(f"{key}: {value}")