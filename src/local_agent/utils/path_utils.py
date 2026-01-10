"""
Path utility class - Provides different path acquisition functions based on environment type

Provides path acquisition logic for development and production environments, ensuring consistency and correctness of path acquisition.
"""

import sys
from pathlib import Path
from typing import Optional

from ..logger import get_logger
from .environment import is_development, is_production

logger = get_logger(__name__)


class PathUtils:
    """Path utility class, provides environment-related path acquisition functionality"""
    
    @staticmethod
    def get_current_executable_path() -> Optional[Path]:
        """
        Get current executable file path
        
        Returns None for development environment
        Returns current executing exe path for production environment
        
        Returns:
            Optional[Path]: Executable file path, returns None for development environment
        """
        try:
            if is_development():
                logger.debug("Development environment: current executable path returns None")
                return None
            
            # Production environment: return current executable file path
            if getattr(sys, 'frozen', False):
                exe_path = Path(sys.executable)
                logger.debug(f"Production environment: detected packaged environment, returning executable path: {exe_path}")
                return exe_path
            else:
                # Although is_production() returns True, but not in packaged environment
                # This situation may be production environment but not packaged, return Python interpreter path
                python_path = Path(sys.executable)
                logger.debug(f"Production environment (unpackaged): returning Python interpreter path: {python_path}")
                return python_path
                
        except Exception as e:
            logger.error(f"Failed to obtain current executable path: {e}")
            return None
    
    @staticmethod
    def get_root_path() -> Path:
        """
        Get root path of current execution environment
        
        If development environment, returns current project's root path
        If production environment, returns exe's root path
        
        Returns:
            Path: Root path
        """
        try:
            if is_development():
                # Development environment: return project root directory
                # Find project root directory by backtracking path
                current_file_path = Path(__file__).resolve()
                project_root = current_file_path.parent.parent.parent.parent  # Backtrack to project root directory
                
                # Validate project root directory has necessary directory structure
                if (project_root / "src").exists() and (project_root / "src" / "local_agent").exists():
                    logger.debug(f"Development environment: returning project root path: {project_root}")
                    return project_root
                else:
                    # If standard path doesn't exist, try other method
                    # Search upward from current working directory
                    cwd = Path.cwd()
                    if (cwd / "src" / "local_agent").exists():
                        logger.debug(f"Development environment: returning root path from working directory: {cwd}")
                        return cwd
                    else:
                        # Finally fallback to root path of current file's directory
                        fallback_root = current_file_path.parent.parent.parent
                        logger.warning(f"Development environment: using fallback root path: {fallback_root}")
                        return fallback_root
            else:
                # Production environment: return exe's root path
                if getattr(sys, 'frozen', False):
                    # Packaged environment: exe's directory is root directory
                    exe_dir = Path(sys.executable).parent
                    logger.debug(f"Production environment (packaged): returning exe root path: {exe_dir}")
                    return exe_dir
                else:
                    # Production environment but not packaged: return current working directory or Python interpreter directory
                    # Priority use current working directory
                    cwd = Path.cwd()
                    if (cwd / "scripts").exists() or (cwd / "dist").exists():
                        logger.debug(f"Production environment (unpackaged): returning working directory root path: {cwd}")
                        return cwd
                    else:
                        # Fallback to Python interpreter directory
                        python_dir = Path(sys.executable).parent
                        logger.debug(f"Production environment (unpackaged): returning Python directory root path: {python_dir}")
                        return python_dir
                        
        except Exception as e:
            logger.error(f"Failed to obtain root path: {e}")
            # When exception occurs, return current working directory as fallback
            return Path.cwd()
    
    @staticmethod
    def get_scripts_directory() -> Path:
        """
        Get scripts directory path
        
        Development environment: scripts directory under project root
        Production environment: scripts directory under exe directory
        
        Returns:
            Path: Scripts directory path
        """
        root_path = PathUtils.get_root_path()
        scripts_dir = root_path / "scripts"
        
        # Ensure directory exists
        scripts_dir.mkdir(exist_ok=True)
        
        logger.debug(f"Scripts directory path: {scripts_dir}")
        return scripts_dir
    
    @staticmethod
    def get_src_directory() -> Optional[Path]:
        """
        Get source code directory path
        
        Development environment: returns src directory path
        Production environment: returns None (no source code in production)
        
        Returns:
            Optional[Path]: Source code directory path, returns None in production
        """
        if is_development():
            root_path = PathUtils.get_root_path()
            src_dir = root_path / "src"
            
            if src_dir.exists():
                logger.debug(f"Development environment: returning source code directory path: {src_dir}")
                return src_dir
            else:
                logger.warning(f"Development environment: source code directory does not exist: {src_dir}")
                return None
        else:
            logger.debug("Production environment: source code directory returns None")
            return None
    
    @staticmethod
    def get_temp_directory() -> Path:
        """
        Get temporary directory path
        
        Development environment: temp directory under project root
        Production environment: temp directory under exe directory
        
        Returns:
            Path: Temporary directory path
        """
        root_path = PathUtils.get_root_path()
        temp_dir = root_path / "temp"
        
        # Ensure directory exists
        temp_dir.mkdir(exist_ok=True)
        
        logger.debug(f"Temporary directory path: {temp_dir}")
        return temp_dir
    
    @staticmethod
    def get_logs_directory() -> Path:
        """
        Get logs directory path
        
        Development environment: logs directory under project root
        Production environment: logs directory under exe directory
        
        Returns:
            Path: Logs directory path
        """
        root_path = PathUtils.get_root_path()
        logs_dir = root_path / "logs"
        
        # Ensure directory exists
        logs_dir.mkdir(exist_ok=True)
        
        logger.debug(f"Logs directory path: {logs_dir}")
        return logs_dir
    
    @staticmethod
    def get_backup_directory() -> Path:
        """
        Get backup directory path
        
        Development environment: backup directory under project root
        Production environment: backup directory under exe directory
        
        Returns:
            Path: Backup directory path
        """
        root_path = PathUtils.get_root_path()
        backup_dir = root_path / "backup"
        
        # Ensure directory exists
        backup_dir.mkdir(exist_ok=True)
        
        logger.debug(f"Backup directory path: {backup_dir}")
        return backup_dir
    
    @staticmethod
    def get_updates_directory() -> Path:
        """
        Get updates directory path
        
        Development environment: updates directory under project root
        Production environment: updates directory under exe directory
        
        Returns:
            Path: Updates directory path
        """
        root_path = PathUtils.get_root_path()
        updates_dir = root_path / "updates"
        
        # Ensure directory exists
        updates_dir.mkdir(exist_ok=True)
        
        logger.debug(f"Updates directory path: {updates_dir}")
        return updates_dir
    
    @staticmethod
    def get_config_file_path() -> Path:
        """
        Get config file path
        
        Development environment: config.ini under project root
        Production environment: config.ini under exe directory
        
        Returns:
            Path: Config file path
        """
        root_path = PathUtils.get_root_path()
        config_file = root_path / "config.ini"
        
        logger.debug(f"Config file path: {config_file}")
        return config_file


# Convenience functions
def get_current_executable_path() -> Optional[Path]:
    """Convenience function: get current executable file path"""
    return PathUtils.get_current_executable_path()


def get_root_path() -> Path:
    """Convenience function: get root path of current execution environment"""
    return PathUtils.get_root_path()


def get_scripts_directory() -> Path:
    """Convenience function: get scripts directory path"""
    return PathUtils.get_scripts_directory()


def get_src_directory() -> Optional[Path]:
    """Convenience function: get source code directory path"""
    return PathUtils.get_src_directory()


def get_temp_directory() -> Path:
    """Convenience function: get temporary directory path"""
    return PathUtils.get_temp_directory()


def get_logs_directory() -> Path:
    """Convenience function: get logs directory path"""
    return PathUtils.get_logs_directory()


def get_backup_directory() -> Path:
    """Convenience function: get backup directory path"""
    return PathUtils.get_backup_directory()


def get_updates_directory() -> Path:
    """Convenience function: get updates directory path"""
    return PathUtils.get_updates_directory()


def get_config_file_path() -> Path:
    """Convenience function: get config file path"""
    return PathUtils.get_config_file_path()


if __name__ == "__main__":
    """Test code"""
    print("=== Path Utils Test ===")
    
    # Test environment detection
    print(f"Development environment: {is_development()}")
    print(f"Production environment: {is_production()}")
    
    print(f"\nCurrent executable path: {get_current_executable_path()}")
    print(f"Root path: {get_root_path()}")
    print(f"Scripts directory: {get_scripts_directory()}")
    print(f"Source code directory: {get_src_directory()}")
    print(f"Temporary directory: {get_temp_directory()}")
    print(f"Logs directory: {get_logs_directory()}")
    print(f"Backup directory: {get_backup_directory()}")
    print(f"Updates directory: {get_updates_directory()}")
    print(f"Config file path: {get_config_file_path()}")