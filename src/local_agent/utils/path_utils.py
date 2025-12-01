"""
路径工具类 - 根据环境类型提供不同的路径获取功能

提供开发环境和生产环境下的路径获取逻辑，确保路径获取的一致性和正确性。
"""

import sys
from pathlib import Path
from typing import Optional

from ..logger import get_logger
from .environment import is_development, is_production

logger = get_logger(__name__)


class PathUtils:
    """路径工具类，提供环境相关的路径获取功能"""
    
    @staticmethod
    def get_current_executable_path() -> Optional[Path]:
        """
        获取当前可执行文件路径
        
        如果是开发环境，返回 None
        如果是生产环境，返回当前正在执行的exe路径
        
        Returns:
            Optional[Path]: 可执行文件路径，开发环境下返回None
        """
        try:
            if is_development():
                logger.debug("开发环境：当前可执行文件路径返回None")
                return None
            
            # 生产环境：返回当前可执行文件路径
            if getattr(sys, 'frozen', False):
                exe_path = Path(sys.executable)
                logger.debug(f"生产环境：检测到打包环境，返回可执行文件路径: {exe_path}")
                return exe_path
            else:
                # 虽然is_production()返回True，但不是打包环境的情况
                # 这种情况可能是生产环境但未打包，返回Python解释器路径
                python_path = Path(sys.executable)
                logger.debug(f"生产环境（未打包）：返回Python解释器路径: {python_path}")
                return python_path
                
        except Exception as e:
            logger.error(f"获取当前可执行文件路径失败: {e}")
            return None
    
    @staticmethod
    def get_root_path() -> Path:
        """
        获取当前执行环境的根路径
        
        如果是开发环境，返回当前项目的根路径
        如果是生产环境，返回exe所在根路径
        
        Returns:
            Path: 根路径
        """
        try:
            if is_development():
                # 开发环境：返回项目根目录
                # 通过回溯路径找到项目根目录
                current_file_path = Path(__file__).resolve()
                project_root = current_file_path.parent.parent.parent.parent  # 回溯到项目根目录
                
                # 验证项目根目录是否存在必要的目录结构
                if (project_root / "src").exists() and (project_root / "src" / "local_agent").exists():
                    logger.debug(f"开发环境：返回项目根路径: {project_root}")
                    return project_root
                else:
                    # 如果标准路径不存在，尝试其他方法
                    # 从当前工作目录向上查找
                    cwd = Path.cwd()
                    if (cwd / "src" / "local_agent").exists():
                        logger.debug(f"开发环境：从工作目录返回根路径: {cwd}")
                        return cwd
                    else:
                        # 最后回退到当前文件所在目录的根路径
                        fallback_root = current_file_path.parent.parent.parent
                        logger.warning(f"开发环境：使用备用根路径: {fallback_root}")
                        return fallback_root
            else:
                # 生产环境：返回exe所在根路径
                if getattr(sys, 'frozen', False):
                    # 打包环境：exe所在目录即为根目录
                    exe_dir = Path(sys.executable).parent
                    logger.debug(f"生产环境（打包）：返回exe所在根路径: {exe_dir}")
                    return exe_dir
                else:
                    # 生产环境但未打包：返回当前工作目录或Python解释器所在目录
                    # 优先使用当前工作目录
                    cwd = Path.cwd()
                    if (cwd / "scripts").exists() or (cwd / "dist").exists():
                        logger.debug(f"生产环境（未打包）：返回工作目录根路径: {cwd}")
                        return cwd
                    else:
                        # 回退到Python解释器所在目录
                        python_dir = Path(sys.executable).parent
                        logger.debug(f"生产环境（未打包）：返回Python目录根路径: {python_dir}")
                        return python_dir
                        
        except Exception as e:
            logger.error(f"获取根路径失败: {e}")
            # 发生异常时返回当前工作目录作为备用
            return Path.cwd()
    
    @staticmethod
    def get_scripts_directory() -> Path:
        """
        获取脚本目录路径
        
        开发环境：项目根目录下的scripts目录
        生产环境：exe所在目录下的scripts目录
        
        Returns:
            Path: 脚本目录路径
        """
        root_path = PathUtils.get_root_path()
        scripts_dir = root_path / "scripts"
        
        # 确保目录存在
        scripts_dir.mkdir(exist_ok=True)
        
        logger.debug(f"脚本目录路径: {scripts_dir}")
        return scripts_dir
    
    @staticmethod
    def get_src_directory() -> Optional[Path]:
        """
        获取源码目录路径
        
        开发环境：返回src目录路径
        生产环境：返回None（生产环境没有源码）
        
        Returns:
            Optional[Path]: 源码目录路径，生产环境下返回None
        """
        if is_development():
            root_path = PathUtils.get_root_path()
            src_dir = root_path / "src"
            
            if src_dir.exists():
                logger.debug(f"开发环境：返回源码目录路径: {src_dir}")
                return src_dir
            else:
                logger.warning(f"开发环境：源码目录不存在: {src_dir}")
                return None
        else:
            logger.debug("生产环境：源码目录返回None")
            return None
    
    @staticmethod
    def get_temp_directory() -> Path:
        """
        获取临时目录路径
        
        开发环境：项目根目录下的temp目录
        生产环境：exe所在目录下的temp目录
        
        Returns:
            Path: 临时目录路径
        """
        root_path = PathUtils.get_root_path()
        temp_dir = root_path / "temp"
        
        # 确保目录存在
        temp_dir.mkdir(exist_ok=True)
        
        logger.debug(f"临时目录路径: {temp_dir}")
        return temp_dir
    
    @staticmethod
    def get_logs_directory() -> Path:
        """
        获取日志目录路径
        
        开发环境：项目根目录下的logs目录
        生产环境：exe所在目录下的logs目录
        
        Returns:
            Path: 日志目录路径
        """
        root_path = PathUtils.get_root_path()
        logs_dir = root_path / "logs"
        
        # 确保目录存在
        logs_dir.mkdir(exist_ok=True)
        
        logger.debug(f"日志目录路径: {logs_dir}")
        return logs_dir
    
    @staticmethod
    def get_backup_directory() -> Path:
        """
        获取备份目录路径
        
        开发环境：项目根目录下的backup目录
        生产环境：exe所在目录下的backup目录
        
        Returns:
            Path: 备份目录路径
        """
        root_path = PathUtils.get_root_path()
        backup_dir = root_path / "backup"
        
        # 确保目录存在
        backup_dir.mkdir(exist_ok=True)
        
        logger.debug(f"备份目录路径: {backup_dir}")
        return backup_dir
    
    @staticmethod
    def get_updates_directory() -> Path:
        """
        获取更新文件目录路径
        
        开发环境：项目根目录下的updates目录
        生产环境：exe所在目录下的updates目录
        
        Returns:
            Path: 更新文件目录路径
        """
        root_path = PathUtils.get_root_path()
        updates_dir = root_path / "updates"
        
        # 确保目录存在
        updates_dir.mkdir(exist_ok=True)
        
        logger.debug(f"更新文件目录路径: {updates_dir}")
        return updates_dir
    
    @staticmethod
    def get_config_file_path() -> Path:
        """
        获取配置文件路径
        
        开发环境：项目根目录下的config.ini
        生产环境：exe所在目录下的config.ini
        
        Returns:
            Path: 配置文件路径
        """
        root_path = PathUtils.get_root_path()
        config_file = root_path / "config.ini"
        
        logger.debug(f"配置文件路径: {config_file}")
        return config_file


# 便捷函数
def get_current_executable_path() -> Optional[Path]:
    """便捷函数：获取当前可执行文件路径"""
    return PathUtils.get_current_executable_path()


def get_root_path() -> Path:
    """便捷函数：获取当前执行环境的根路径"""
    return PathUtils.get_root_path()


def get_scripts_directory() -> Path:
    """便捷函数：获取脚本目录路径"""
    return PathUtils.get_scripts_directory()


def get_src_directory() -> Optional[Path]:
    """便捷函数：获取源码目录路径"""
    return PathUtils.get_src_directory()


def get_temp_directory() -> Path:
    """便捷函数：获取临时目录路径"""
    return PathUtils.get_temp_directory()


def get_logs_directory() -> Path:
    """便捷函数：获取日志目录路径"""
    return PathUtils.get_logs_directory()


def get_backup_directory() -> Path:
    """便捷函数：获取备份目录路径"""
    return PathUtils.get_backup_directory()


def get_updates_directory() -> Path:
    """便捷函数：获取更新文件目录路径"""
    return PathUtils.get_updates_directory()


def get_config_file_path() -> Path:
    """便捷函数：获取配置文件路径"""
    return PathUtils.get_config_file_path()


if __name__ == "__main__":
    """测试代码"""
    print("=== 路径工具类测试 ===")
    
    # 测试环境判断
    print(f"开发环境: {is_development()}")
    print(f"生产环境: {is_production()}")
    
    # 测试主要功能
    print(f"\n当前可执行文件路径: {get_current_executable_path()}")
    print(f"根路径: {get_root_path()}")
    print(f"脚本目录: {get_scripts_directory()}")
    print(f"源码目录: {get_src_directory()}")
    print(f"临时目录: {get_temp_directory()}")
    print(f"日志目录: {get_logs_directory()}")
    print(f"备份目录: {get_backup_directory()}")
    print(f"更新目录: {get_updates_directory()}")
    print(f"配置文件路径: {get_config_file_path()}")